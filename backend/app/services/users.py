from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Doctor, Organization, ShiftGroup, User, UserShiftGroup
from app.schemas import (
    DoctorSelfUpdate,
    OrganizationBrief,
    OrganizationUserRead,
    UserCapabilities,
    UserRead,
    UserShiftGroupBrief,
)
from app.services.audit import record_audit
from app.services.authz import (
    ROLE_ADMIN,
    ROLE_PLANNER,
    can_use_planning_ui,
    get_linked_doctor,
    is_admin,
    list_shift_groups_for_doctor,
)
from app.services.organizations import get_organization_by_slug
from app.services.tenancy import ensure_default_organization


def get_user_in_organization(db: Session, email: str, organization_id: int) -> User | None:
    return db.scalar(
        select(User).where(User.email == email.lower(), User.organization_id == organization_id)
    )


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def authenticate_user(db: Session, email: str, password: str, organization_slug: str) -> User | None:
    org = get_organization_by_slug(db, organization_slug)
    if org is None:
        return None
    user = get_user_in_organization(db, email, org.id)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def ensure_admin_user(db: Session, *, email: str, password: str) -> User:
    org = ensure_default_organization(db)
    existing = get_user_in_organization(db, email, org.id)
    if existing:
        return existing
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role="admin",
        locale="de",
        organization_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def build_user_read(db: Session, user: User) -> UserRead:
    linked = get_linked_doctor(db, user.id)
    doctor_id = linked.id if linked else None
    groups: list[UserShiftGroupBrief] = []
    if linked:
        for g in list_shift_groups_for_doctor(db, linked.id):
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
    caps = UserCapabilities(
        admin=is_admin(user),
        planning=can_use_planning_ui(user),
        doctor_portal=doctor_id is not None,
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
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        locale=user.locale,
        organization_id=user.organization_id,
        organization=org_brief,
        doctor_id=doctor_id,
        shift_groups=groups,
        planner_shift_groups=planner_groups,
        capabilities=caps,
    )


def update_self_doctor_profile(db: Session, user: User, payload: DoctorSelfUpdate) -> Doctor | None:
    from app.services.doctors import update_doctor_self

    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        return None
    return update_doctor_self(db, doctor, payload, actor=user.email, source="rest")


def list_organization_users(db: Session, *, organization_id: int) -> list[OrganizationUserRead]:
    stmt = (
        select(User, Doctor)
        .outerjoin(Doctor, Doctor.user_id == User.id)
        .where(User.organization_id == organization_id)
        .order_by(User.email)
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
                linked_doctor_id=d.id if d is not None else None,
                linked_doctor_label=label,
            )
        )
    return out


def delete_own_account(db: Session, user: User, *, password: str) -> None:
    if not verify_password(password, user.hashed_password):
        raise ValueError("Invalid password")
    if is_admin(user):
        admin_count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == user.organization_id, User.role == ROLE_ADMIN)
        )
        if admin_count is not None and admin_count <= 1:
            raise ValueError("Cannot delete the only administrator for this organization")
    actor_email = user.email
    user_id = user.id
    record_audit(
        db,
        actor=actor_email,
        source="rest",
        action="delete_account",
        entity_type="user",
        entity_id=user_id,
        details={"organization_id": user.organization_id},
    )
    db.delete(user)
    db.commit()
