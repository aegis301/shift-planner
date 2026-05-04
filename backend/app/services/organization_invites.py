from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Account, Organization, OrganizationMembershipInvite, ShiftGroup, TeamMember, User, UserShiftGroup
from app.schemas import (
    OrganizationBrief,
    OrganizationInviteAcceptInput,
    OrganizationInviteCreate,
    OrganizationMembershipInvitePendingRead,
    OrganizationMembershipInviteRead,
    ShiftGroupInviteOption,
    TeamMemberCreate,
    TeamMemberUpdate,
)
from app.services.audit import record_audit
from app.services.authz import ROLE_PLANNER, ROLE_TEAM_MEMBER, is_admin
from app.services.org_limits import assert_org_allows_team_member_user_link
from app.services.team_members import create_team_member, delete_team_member, update_team_member
from app.services.tenancy import get_organization
from app.services.users import get_account_by_email, get_user_in_organization


INVITE_PENDING = "pending"
INVITE_ACCEPTED = "accepted"
INVITE_DECLINED = "declined"
INVITE_REVOKED = "revoked"


def _locale_for_account(db: Session, account_id: int) -> str:
    loc = db.scalar(select(User.locale).where(User.account_id == account_id).limit(1))
    return loc if loc else "de"


def _assert_shift_groups_in_org(db: Session, *, organization_id: int, group_ids: list[int]) -> None:
    if not group_ids:
        raise ValueError("At least one shift group is required")
    for gid in set(group_ids):
        g = db.get(ShiftGroup, gid)
        if g is None or g.organization_id != organization_id:
            raise ValueError(f"Shift group not found in organization: {gid}")


def _team_member_invite_complete_on_row(row: OrganizationMembershipInvite) -> bool:
    return bool(
        (row.first_name or "").strip()
        and (row.last_name or "").strip()
        and (row.team_member_shift_group_ids or [])
    )


def invite_to_read(db: Session, row: OrganizationMembershipInvite) -> OrganizationMembershipInviteRead:
    acc = db.get(Account, row.invitee_account_id)
    email = acc.email if acc else ""
    tm_ids = list(row.team_member_shift_group_ids or [])
    pl_ids = list(row.planner_shift_group_ids or [])
    return OrganizationMembershipInviteRead(
        id=row.id,
        organization_id=row.organization_id,
        invitee_email=email,
        role=row.role,
        status=row.status,
        message=row.message,
        first_name=row.first_name,
        last_name=row.last_name,
        employment_percentage=row.employment_percentage,
        shift_group_ids=tm_ids,
        planner_shift_group_ids=pl_ids,
        has_precreated_team_member=row.precreated_team_member_id is not None,
        created_at=row.created_at,
    )


def invite_pending_to_read(db: Session, row: OrganizationMembershipInvite) -> OrganizationMembershipInvitePendingRead:
    org = db.get(Organization, row.organization_id)
    if org is None:
        ob = OrganizationBrief(id=row.organization_id, name="", slug="", plan_tier="team")
    else:
        ob = OrganizationBrief.model_validate(org)
    needs_profile = (
        row.role == ROLE_TEAM_MEMBER
        and row.precreated_team_member_id is None
        and not _team_member_invite_complete_on_row(row)
    )
    accept_options: list[ShiftGroupInviteOption] = []
    if needs_profile:
        sg_rows = db.scalars(
            select(ShiftGroup)
            .where(ShiftGroup.organization_id == row.organization_id)
            .order_by(ShiftGroup.display_order, ShiftGroup.code)
        ).all()
        accept_options = [ShiftGroupInviteOption.model_validate(g) for g in sg_rows]
    return OrganizationMembershipInvitePendingRead(
        id=row.id,
        organization=ob,
        role=row.role,
        message=row.message,
        first_name=row.first_name,
        last_name=row.last_name,
        needs_profile_on_accept=needs_profile,
        has_precreated_team_member=row.precreated_team_member_id is not None,
        accept_shift_groups=accept_options,
        created_at=row.created_at,
    )


def list_membership_invites_for_org(db: Session, *, organization_id: int) -> list[OrganizationMembershipInvite]:
    stmt = (
        select(OrganizationMembershipInvite)
        .where(OrganizationMembershipInvite.organization_id == organization_id)
        .order_by(OrganizationMembershipInvite.created_at.desc())
    )
    return list(db.scalars(stmt).unique().all())


def list_pending_invites_for_account(db: Session, *, account_id: int) -> list[OrganizationMembershipInvite]:
    stmt = (
        select(OrganizationMembershipInvite)
        .where(
            OrganizationMembershipInvite.invitee_account_id == account_id,
            OrganizationMembershipInvite.status == INVITE_PENDING,
        )
        .options(joinedload(OrganizationMembershipInvite.organization))
        .order_by(OrganizationMembershipInvite.created_at.desc())
    )
    return list(db.scalars(stmt).unique().all())


def create_membership_invite(db: Session, *, actor: User, payload: OrganizationInviteCreate) -> OrganizationMembershipInvite:
    if not is_admin(actor):
        raise ValueError("Admin only")
    org_id = actor.organization_id
    email = str(payload.invitee_email).strip().lower()
    account = get_account_by_email(db, email)
    if account is None:
        raise ValueError("No account exists for this email")
    if get_user_in_organization(db, email, org_id) is not None:
        raise ValueError("This account already has a membership in the organization")
    existing_pending = db.scalar(
        select(OrganizationMembershipInvite).where(
            OrganizationMembershipInvite.organization_id == org_id,
            OrganizationMembershipInvite.invitee_account_id == account.id,
            OrganizationMembershipInvite.status == INVITE_PENDING,
        )
    )
    if existing_pending is not None:
        raise ValueError("A pending invite already exists for this email")
    precreated_id: int | None = None
    stored_fn: str | None = None
    stored_ln: str | None = None
    stored_emp: int | None = None
    stored_notes: str | None = None
    stored_tm_group_ids: list[int] | None = None
    stored_planner_ids: list[int] | None = None

    if payload.role == ROLE_PLANNER:
        _assert_shift_groups_in_org(db, organization_id=org_id, group_ids=payload.planner_shift_group_ids)
        stored_planner_ids = list(payload.planner_shift_group_ids)
    elif payload.role == ROLE_TEAM_MEMBER and payload.prepare_team_member_profile:
        _assert_shift_groups_in_org(db, organization_id=org_id, group_ids=payload.shift_group_ids)
        org = get_organization(db, org_id)
        if org is not None:
            assert_org_allows_team_member_user_link(db, org)
        dup = db.scalar(
            select(TeamMember).where(TeamMember.organization_id == org_id, TeamMember.email == email)
        )
        if dup is not None:
            raise ValueError("A team member profile with this email already exists in the organization")
        tm_create = TeamMemberCreate(
            first_name=(payload.first_name or "").strip(),
            last_name=(payload.last_name or "").strip(),
            email=email,
            employment_percentage=payload.employment_percentage,
            notes=payload.notes.strip() if payload.notes else None,
            shift_group_ids=list(payload.shift_group_ids),
            user_id=None,
        )
        created = create_team_member(
            db, tm_create, organization_id=org_id, actor=actor.email, source="rest", transactional=False
        )
        precreated_id = created.id
        stored_fn = tm_create.first_name
        stored_ln = tm_create.last_name
        stored_emp = tm_create.employment_percentage
        stored_notes = tm_create.notes
        stored_tm_group_ids = list(payload.shift_group_ids)

    row = OrganizationMembershipInvite(
        organization_id=org_id,
        invitee_account_id=account.id,
        invited_by_user_id=actor.id,
        role=payload.role,
        first_name=stored_fn,
        last_name=stored_ln,
        employment_percentage=stored_emp,
        notes=stored_notes,
        team_member_shift_group_ids=stored_tm_group_ids,
        planner_shift_group_ids=stored_planner_ids,
        precreated_team_member_id=precreated_id,
        message=payload.message.strip() if payload.message else None,
        status=INVITE_PENDING,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor.email,
        source="rest",
        action="create_organization_invite",
        entity_type="organization_membership_invite",
        entity_id=row.id,
        details={"organization_id": org_id, "invitee_email": email, "role": payload.role},
    )
    db.commit()
    db.refresh(row)
    return row


def revoke_membership_invite(db: Session, *, actor: User, invite_id: int) -> OrganizationMembershipInvite:
    if not is_admin(actor):
        raise ValueError("Admin only")
    row = db.get(OrganizationMembershipInvite, invite_id)
    if row is None or row.organization_id != actor.organization_id:
        raise ValueError("Invite not found")
    if row.status != INVITE_PENDING:
        raise ValueError("Only pending invites can be revoked")
    org_id = row.organization_id
    tid = row.precreated_team_member_id
    row.precreated_team_member_id = None
    row.status = INVITE_REVOKED
    row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=actor.email,
        source="rest",
        action="revoke_organization_invite",
        entity_type="organization_membership_invite",
        entity_id=row.id,
        details={"organization_id": row.organization_id},
    )
    db.commit()
    db.refresh(row)
    if tid is not None:
        tm = db.get(TeamMember, tid)
        if tm is not None and tm.organization_id == org_id and tm.user_id is None:
            delete_team_member(db, tid, organization_id=org_id, actor=actor.email, source="rest")
    return row


def decline_membership_invite(db: Session, *, user: User, invite_id: int) -> OrganizationMembershipInvite:
    row = db.get(OrganizationMembershipInvite, invite_id)
    if row is None:
        raise ValueError("Invite not found")
    if row.invitee_account_id != user.account_id:
        raise ValueError("Invite not found")
    if row.status != INVITE_PENDING:
        raise ValueError("Invite is not pending")
    org_id = row.organization_id
    tid = row.precreated_team_member_id
    row.precreated_team_member_id = None
    row.status = INVITE_DECLINED
    row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=user.email,
        source="rest",
        action="decline_organization_invite",
        entity_type="organization_membership_invite",
        entity_id=row.id,
        details={"organization_id": row.organization_id},
    )
    db.commit()
    db.refresh(row)
    if tid is not None:
        tm = db.get(TeamMember, tid)
        if tm is not None and tm.organization_id == org_id and tm.user_id is None:
            delete_team_member(db, tid, organization_id=org_id, actor=user.email, source="rest")
    return row


def accept_membership_invite(
    db: Session, *, user: User, invite_id: int, accept: OrganizationInviteAcceptInput | None = None
) -> User:
    accept_payload = accept or OrganizationInviteAcceptInput()
    row = db.get(OrganizationMembershipInvite, invite_id)
    if row is None:
        raise ValueError("Invite not found")
    if row.invitee_account_id != user.account_id:
        raise ValueError("Invite not found")
    if row.status != INVITE_PENDING:
        raise ValueError("Invite is not pending")
    org_id = row.organization_id
    if get_user_in_organization(db, user.email, org_id) is not None:
        raise ValueError("You already have a membership in this organization")
    locale = _locale_for_account(db, user.account_id)
    acc = db.get(Account, row.invitee_account_id)
    if acc is None:
        raise ValueError("Account not found")
    if row.role == ROLE_TEAM_MEMBER:
        if row.precreated_team_member_id is not None:
            tm = db.get(TeamMember, row.precreated_team_member_id)
            if tm is None or tm.organization_id != org_id or tm.user_id is not None:
                raise ValueError("Invalid team member profile for this invite")
            if (tm.email or "").strip().lower() != acc.email.lower():
                raise ValueError("Team profile email does not match the invited account")
            org = get_organization(db, org_id)
            if org is not None:
                assert_org_allows_team_member_user_link(db, org)
            new_user = User(
                account_id=acc.id,
                organization_id=org_id,
                role=ROLE_TEAM_MEMBER,
                locale=locale,
                is_active=True,
            )
            db.add(new_user)
            db.flush()
            linked = update_team_member(
                db,
                tm.id,
                TeamMemberUpdate(user_id=new_user.id),
                organization_id=org_id,
                actor=user.email,
                source="rest",
            )
            if linked is None:
                raise ValueError("Failed to link team member profile")
            inv = db.get(OrganizationMembershipInvite, invite_id)
            if inv is not None:
                inv.status = INVITE_ACCEPTED
                inv.updated_at = datetime.now(timezone.utc)
                record_audit(
                    db,
                    actor=user.email,
                    source="rest",
                    action="accept_organization_invite",
                    entity_type="organization_membership_invite",
                    entity_id=inv.id,
                    details={"organization_id": org_id, "role": ROLE_TEAM_MEMBER, "linked_team_member_id": tm.id},
                )
                db.commit()
            nu = db.get(User, new_user.id)
            if nu is None:
                raise ValueError("Failed to create membership")
            return nu

        complete_row = _team_member_invite_complete_on_row(row)
        if complete_row:
            first_name = (row.first_name or "").strip()
            last_name = (row.last_name or "").strip()
            tm_ids = list(row.team_member_shift_group_ids or [])
            emp = row.employment_percentage if row.employment_percentage is not None else 100
            notes = row.notes
        else:
            first_name = (accept_payload.first_name or "").strip()
            last_name = (accept_payload.last_name or "").strip()
            tm_ids = list(accept_payload.shift_group_ids or [])
            if not first_name or not last_name or not tm_ids:
                raise ValueError("first_name, last_name, and shift_group_ids are required to accept this invite")
            emp = accept_payload.employment_percentage if accept_payload.employment_percentage is not None else 100
            notes = accept_payload.notes
        _assert_shift_groups_in_org(db, organization_id=org_id, group_ids=tm_ids)
        org = get_organization(db, org_id)
        if org is not None:
            assert_org_allows_team_member_user_link(db, org)
        new_user = User(
            account_id=acc.id,
            organization_id=org_id,
            role=ROLE_TEAM_MEMBER,
            locale=locale,
            is_active=True,
        )
        db.add(new_user)
        db.flush()
        tm_payload = TeamMemberCreate(
            first_name=first_name,
            last_name=last_name,
            email=acc.email,
            employment_percentage=emp,
            notes=notes,
            shift_group_ids=tm_ids,
            user_id=new_user.id,
        )
        create_team_member(db, tm_payload, organization_id=org_id, actor=acc.email, source="rest")
        inv = db.get(OrganizationMembershipInvite, invite_id)
        if inv is not None:
            inv.status = INVITE_ACCEPTED
            inv.updated_at = datetime.now(timezone.utc)
            record_audit(
                db,
                actor=user.email,
                source="rest",
                action="accept_organization_invite",
                entity_type="organization_membership_invite",
                entity_id=inv.id,
                details={"organization_id": org_id, "role": ROLE_TEAM_MEMBER},
            )
            db.commit()
        nu = db.get(User, new_user.id)
        if nu is None:
            raise ValueError("Failed to create membership")
        return nu
    if row.role == ROLE_PLANNER:
        pl_ids = list(row.planner_shift_group_ids or [])
        _assert_shift_groups_in_org(db, organization_id=org_id, group_ids=pl_ids)
        new_user = User(
            account_id=acc.id,
            organization_id=org_id,
            role=ROLE_PLANNER,
            locale=locale,
            is_active=True,
        )
        db.add(new_user)
        db.flush()
        for gid in sorted(set(pl_ids)):
            db.add(UserShiftGroup(user_id=new_user.id, shift_group_id=gid))
        row.status = INVITE_ACCEPTED
        row.updated_at = datetime.now(timezone.utc)
        record_audit(
            db,
            actor=user.email,
            source="rest",
            action="accept_organization_invite",
            entity_type="organization_membership_invite",
            entity_id=row.id,
            details={"organization_id": org_id, "role": ROLE_PLANNER},
        )
        db.commit()
        db.refresh(new_user)
        return new_user
    raise ValueError("Unsupported invite role")
