from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Account, Organization, ShiftGroup, TeamMember, User, UserShiftGroup
from app.schemas import (
    AccountSessionRead,
    MembershipSummary,
    OrganizationBrief,
    OrganizationUserRead,
    TeamMemberSelfUpdate,
    UserCapabilities,
    UserRead,
    UserShiftGroupBrief,
)
from app.services.audit import record_audit
from app.services.authz import (
    ROLE_ADMIN,
    ROLE_PLANNER,
    ROLE_TEAM_MEMBER,
    can_use_planning_ui,
    get_linked_team_member,
    is_admin,
    list_shift_groups_for_team_member,
)
from app.services.shift_groups import list_shift_groups
from app.services.organizations import get_organization_by_slug
from app.services.tenancy import ensure_default_organization


def get_account_by_email(db: Session, email: str) -> Account | None:
    return db.scalar(select(Account).where(Account.email == email.lower()))


def get_user_in_organization(db: Session, email: str, organization_id: int) -> User | None:
    return db.scalar(
        select(User)
        .join(Account, Account.id == User.account_id)
        .where(Account.email == email.lower(), User.organization_id == organization_id)
    )


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


LoginAuthResult = Literal["invalid"] | tuple[Literal["user"], User] | tuple[Literal["account"], Account]


def authenticate_login(db: Session, *, email: str, password: str) -> LoginAuthResult:
    normalized_email = email.lower()
    account = get_account_by_email(db, normalized_email)
    if account is None:
        return "invalid"
    if not verify_password(password, account.hashed_password):
        return "invalid"
    stmt = select(User).where(User.account_id == account.id, User.is_active.is_(True))
    matches = list(db.scalars(stmt).all())
    if len(matches) == 0:
        return ("account", account)
    rows: list[tuple[User, Organization | None]] = []
    for m in matches:
        o = db.get(Organization, m.organization_id)
        rows.append((m, o))
    rows.sort(key=lambda t: ((t[1].slug if t[1] is not None else ""), t[0].id))
    return ("user", rows[0][0])


def build_account_session_read(account: Account) -> AccountSessionRead:
    return AccountSessionRead(
        auth_kind="account",
        email=account.email,
        locale=account.locale,
        memberships=[],
    )


def switch_membership_by_organization_slug(db: Session, *, current: User, organization_slug: str) -> User | None:
    slug = organization_slug.strip().lower()
    org = get_organization_by_slug(db, slug)
    if org is None:
        return None
    return db.scalar(
        select(User).where(
            User.account_id == current.account_id,
            User.organization_id == org.id,
            User.is_active.is_(True),
        )
    )


def ensure_admin_user(db: Session, *, email: str, password: str) -> User:
    org = ensure_default_organization(db)
    existing = get_user_in_organization(db, email, org.id)
    if existing:
        existing.account.hashed_password = hash_password(password)
        db.commit()
        db.refresh(existing)
        return existing
    acc = Account(email=email.lower(), hashed_password=hash_password(password), locale="de")
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org.id, role="admin", locale="de")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _membership_summaries(db: Session, account_id: int) -> list[MembershipSummary]:
    rows = list(
        db.scalars(
            select(User).where(User.account_id == account_id, User.is_active.is_(True)).order_by(User.organization_id)
        ).all()
    )
    out: list[MembershipSummary] = []
    for m in rows:
        org = db.get(Organization, m.organization_id)
        if org is None:
            ob = OrganizationBrief(id=m.organization_id, name="", slug="", plan_tier="team")
        else:
            ob = OrganizationBrief.model_validate(org)
        doc = get_linked_team_member(db, m)
        out.append(
            MembershipSummary(
                membership_id=m.id,
                organization=ob,
                role=m.role,
                team_member_id=doc.id if doc is not None else None,
            )
        )
    out.sort(key=lambda s: (s.organization.slug, s.membership_id))
    return out


def build_user_read(db: Session, user: User) -> UserRead:
    linked = get_linked_team_member(db, user)
    team_member_id = linked.id if linked else None
    groups: list[UserShiftGroupBrief] = []
    if linked:
        for g in list_shift_groups_for_team_member(db, linked.id):
            groups.append(UserShiftGroupBrief.model_validate(g))
    planner_groups: list[UserShiftGroupBrief] = []
    if user.role == ROLE_PLANNER:
        stmt = (
            select(ShiftGroup)
            .join(UserShiftGroup, UserShiftGroup.shift_group_id == ShiftGroup.id)
            .where(UserShiftGroup.user_id == user.id, ShiftGroup.organization_id == user.organization_id)
            .order_by(ShiftGroup.display_order, ShiftGroup.code)
        )
        for g in db.scalars(stmt):
            planner_groups.append(UserShiftGroupBrief.model_validate(g))
    org_wide_shift_groups: list[UserShiftGroupBrief] = []
    if is_admin(user):
        for g in list_shift_groups(db, organization_id=user.organization_id, active_only=False):
            org_wide_shift_groups.append(UserShiftGroupBrief.model_validate(g))
    caps = UserCapabilities(
        admin=is_admin(user),
        planning=can_use_planning_ui(user),
        team_member_portal=team_member_id is not None,
    )
    org = db.get(Organization, user.organization_id)
    if org is None:
        org_brief = OrganizationBrief(
            id=user.organization_id,
            name="",
            slug="",
            plan_tier="team",
        )
    else:
        org_brief = OrganizationBrief.model_validate(org)
    memberships = _membership_summaries(db, user.account_id)
    return UserRead(
        auth_kind="user",
        id=user.id,
        email=user.email,
        role=user.role,
        locale=user.locale,
        organization_id=user.organization_id,
        organization=org_brief,
        team_member_id=team_member_id,
        shift_groups=groups,
        planner_shift_groups=planner_groups,
        organization_shift_groups=org_wide_shift_groups,
        capabilities=caps,
        memberships=memberships,
    )


def update_self_team_member_profile(db: Session, user: User, payload: TeamMemberSelfUpdate) -> TeamMember | None:
    from app.services.team_members import update_team_member_self

    member = get_linked_team_member(db, user)
    if member is None:
        return None
    return update_team_member_self(db, member, payload, actor=user.email, source="rest")


def list_organization_users(db: Session, *, organization_id: int) -> list[OrganizationUserRead]:
    stmt = (
        select(User, TeamMember)
        .join(Account, Account.id == User.account_id)
        .outerjoin(TeamMember, TeamMember.user_id == User.id)
        .where(User.organization_id == organization_id)
        .order_by(Account.email)
    )
    out: list[OrganizationUserRead] = []
    for row in db.execute(stmt).all():
        u, d = row[0], row[1]
        label = f"{d.last_name}, {d.first_name}" if d is not None else None
        out.append(
            OrganizationUserRead(
                id=u.id,
                email=u.email,
                role=u.role,
                locale=u.locale,
                is_active=u.is_active,
                linked_team_member_id=d.id if d is not None else None,
                linked_team_member_label=label,
            )
        )
    return out


def get_organization_user_read(db: Session, *, user_id: int, organization_id: int) -> OrganizationUserRead | None:
    stmt = (
        select(User, TeamMember)
        .outerjoin(TeamMember, TeamMember.user_id == User.id)
        .where(User.id == user_id, User.organization_id == organization_id)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    u, d = row[0], row[1]
    label = f"{d.last_name}, {d.first_name}" if d is not None else None
    return OrganizationUserRead(
        id=u.id,
        email=u.email,
        role=u.role,
        locale=u.locale,
        is_active=u.is_active,
        linked_team_member_id=d.id if d is not None else None,
        linked_team_member_label=label,
    )


_ASSIGNABLE_ROLES = frozenset({ROLE_ADMIN, ROLE_PLANNER, ROLE_TEAM_MEMBER})


def admin_set_organization_user_role(db: Session, *, actor: User, target_user_id: int, role: str) -> OrganizationUserRead:
    if not is_admin(actor):
        raise ValueError("Admin only")
    if role not in _ASSIGNABLE_ROLES:
        raise ValueError("Invalid role")
    target = db.get(User, target_user_id)
    if target is None:
        raise ValueError("User not found")
    if target.organization_id != actor.organization_id:
        raise ValueError("User not in this organization")
    if target.role == ROLE_ADMIN and role != ROLE_ADMIN:
        admin_count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == actor.organization_id, User.role == ROLE_ADMIN)
        )
        if admin_count is not None and admin_count <= 1:
            raise ValueError("Cannot demote the only administrator for this organization")
    previous_role = target.role
    target.role = role
    if role != ROLE_PLANNER:
        db.execute(delete(UserShiftGroup).where(UserShiftGroup.user_id == target.id))
    record_audit(
        db,
        actor=actor.email,
        source="rest",
        action="admin_set_user_role",
        entity_type="user",
        entity_id=target.id,
        details={
            "organization_id": target.organization_id,
            "target_email": target.email,
            "previous_role": previous_role,
            "new_role": role,
        },
    )
    db.commit()
    db.refresh(target)
    out = get_organization_user_read(db, user_id=target.id, organization_id=actor.organization_id)
    if out is None:
        raise ValueError("User not found")
    return out


def admin_reset_account_password(
    db: Session, *, actor: User, target_user_id: int, new_password: str
) -> None:
    if not is_admin(actor):
        raise ValueError("Admin only")
    target = db.get(User, target_user_id)
    if target is None:
        raise ValueError("User not found")
    if target.organization_id != actor.organization_id:
        raise ValueError("User not in this organization")
    if target.id == actor.id:
        raise ValueError("Cannot reset your own password here; use account settings")
    if not target.is_active:
        raise ValueError("User is not active")
    account = target.account
    account.hashed_password = hash_password(new_password)
    record_audit(
        db,
        actor=actor.email,
        source="rest",
        action="admin_reset_user_password",
        entity_type="user",
        entity_id=target.id,
        details={
            "organization_id": target.organization_id,
            "target_email": target.email,
            "account_id": account.id,
        },
    )
    db.commit()


def change_own_account_password(
    db: Session, *, account: Account, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, account.hashed_password):
        raise ValueError("Invalid password")
    if current_password == new_password:
        raise ValueError("New password must differ from current password")
    account.hashed_password = hash_password(new_password)
    record_audit(
        db,
        actor=account.email,
        source="rest",
        action="change_account_password",
        entity_type="account",
        entity_id=str(account.id),
        details={},
    )
    db.commit()


def admin_delete_organization_user(db: Session, *, actor: User, target_user_id: int) -> None:
    if not is_admin(actor):
        raise ValueError("Admin only")
    target = db.get(User, target_user_id)
    if target is None:
        raise ValueError("User not found")
    if target.organization_id != actor.organization_id:
        raise ValueError("User not in this organization")
    if target.id == actor.id:
        raise ValueError("Cannot remove your own account here; use account settings")
    if target.role == ROLE_ADMIN:
        admin_count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == actor.organization_id, User.role == ROLE_ADMIN)
        )
        if admin_count is not None and admin_count <= 1:
            raise ValueError("Cannot remove the only administrator for this organization")
    record_audit(
        db,
        actor=actor.email,
        source="rest",
        action="admin_delete_organization_user",
        entity_type="user",
        entity_id=target.id,
        details={"organization_id": target.organization_id, "target_email": target.email},
    )
    account_id = target.account_id
    db.delete(target)
    db.flush()
    remaining = db.scalar(select(func.count()).select_from(User).where(User.account_id == account_id))
    if remaining == 0:
        acc = db.get(Account, account_id)
        if acc is not None:
            db.delete(acc)
    db.commit()


def delete_own_account(db: Session, account: Account, *, password: str) -> None:
    if not verify_password(password, account.hashed_password):
        raise ValueError("Invalid password")
    memberships = list(db.scalars(select(User).where(User.account_id == account.id)).all())
    for m in memberships:
        if is_admin(m):
            admin_count = db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.organization_id == m.organization_id, User.role == ROLE_ADMIN)
            )
            if admin_count is not None and admin_count <= 1:
                raise ValueError("Cannot delete the only administrator for this organization")
    actor_email = account.email
    record_audit(
        db,
        actor=actor_email,
        source="rest",
        action="delete_account",
        entity_type="account",
        entity_id=str(account.id),
        details={"membership_ids": [m.id for m in memberships]},
    )
    db.delete(account)
    db.commit()


def delete_own_account_from_user(db: Session, user: User, *, password: str) -> None:
    delete_own_account(db, account=user.account, password=password)
