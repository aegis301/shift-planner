from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import PlanningCell, RosterSlotAssignment, TeamMember, TeamMemberPeriodNote, TeamMemberShiftGroup, User
from app.schemas import TeamMemberCreate, TeamMemberRead, TeamMemberSelfUpdate, TeamMemberUpdate
from app.services.audit import record_audit
from app.services.authz import roles_allowed_for_team_member_user_link
from app.services.org_limits import assert_org_allows_team_member_user_link
from app.services.shift_groups import replace_team_member_shift_groups
from app.services.tenancy import get_organization

_MISSING = object()


def list_team_members(db: Session, *, organization_id: int, active_only: bool = False) -> list[TeamMember]:
    stmt = (
        select(TeamMember)
        .options(joinedload(TeamMember.shift_group_links))
        .where(TeamMember.organization_id == organization_id)
        .order_by(TeamMember.last_name, TeamMember.first_name)
    )
    if active_only:
        stmt = stmt.where(TeamMember.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def list_team_members_for_planner(db: Session, user: User, *, active_only: bool = False) -> list[TeamMember]:
    from app.services.authz import is_admin, planner_shift_group_ids

    if is_admin(user):
        return list_team_members(db, organization_id=user.organization_id, active_only=active_only)
    gids = planner_shift_group_ids(db, user)
    if not gids:
        return []
    stmt = (
        select(TeamMember)
        .options(joinedload(TeamMember.shift_group_links))
        .where(TeamMember.organization_id == user.organization_id)
        .join(TeamMemberShiftGroup)
        .where(TeamMemberShiftGroup.shift_group_id.in_(gids))
        .distinct()
        .order_by(TeamMember.last_name, TeamMember.first_name)
    )
    if active_only:
        stmt = stmt.where(TeamMember.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def team_member_to_read(member: TeamMember) -> TeamMemberRead:
    link_ids = sorted({link.shift_group_id for link in member.shift_group_links})
    return TeamMemberRead(
        id=member.id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        employment_percentage=member.employment_percentage,
        notes=member.notes,
        shift_group_ids=link_ids,
        user_id=member.user_id,
        is_active=member.is_active,
        created_at=member.created_at,
    )


def _apply_team_member_user_id(db: Session, member: TeamMember, user_id: int | None) -> None:
    if user_id is None:
        member.user_id = None
        db.flush()
        return
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")
    if user.role not in roles_allowed_for_team_member_user_link():
        raise ValueError("User role cannot be linked to a team member profile")
    if user.organization_id != member.organization_id:
        raise ValueError("User must belong to the same organization as the team member")
    taken = db.scalar(select(TeamMember).where(TeamMember.user_id == user_id, TeamMember.id != member.id))
    if taken is not None:
        raise ValueError("User is already linked to another team member")
    if member.user_id is None and user_id is not None:
        org = get_organization(db, member.organization_id)
        if org is not None:
            assert_org_allows_team_member_user_link(db, org)
    member.user_id = user_id
    db.flush()


def create_team_member(
    db: Session, payload: TeamMemberCreate, *, organization_id: int, actor: str, source: str
) -> TeamMember:
    data = payload.model_dump(exclude={"shift_group_ids", "user_id"})
    member = TeamMember(**data, organization_id=organization_id)
    db.add(member)
    db.flush()
    try:
        if payload.user_id is not None:
            _apply_team_member_user_id(db, member, payload.user_id)
        record_audit(db, actor=actor, source=source, action="create", entity_type="team_member", entity_id=member.id)
        db.commit()
    except ValueError:
        db.rollback()
        raise
    db.refresh(member)
    if payload.shift_group_ids:
        replace_team_member_shift_groups(db, member.id, payload.shift_group_ids, actor=actor, source=source)
    db.refresh(member, attribute_names=["shift_group_links"])
    return member


def update_team_member(
    db: Session, team_member_id: int, payload: TeamMemberUpdate, *, organization_id: int, actor: str, source: str
) -> TeamMember | None:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        return None
    raw = payload.model_dump(exclude_unset=True)
    group_ids = raw.pop("shift_group_ids", None)
    user_id_raw = raw.pop("user_id", _MISSING)
    for key, value in raw.items():
        setattr(member, key, value)
    if user_id_raw is not _MISSING:
        try:
            _apply_team_member_user_id(db, member, user_id_raw)
        except ValueError:
            db.rollback()
            db.refresh(member)
            raise
    record_audit(db, actor=actor, source=source, action="update", entity_type="team_member", entity_id=member.id)
    db.commit()
    db.refresh(member)
    if group_ids is not None:
        replace_team_member_shift_groups(db, team_member_id, group_ids, actor=actor, source=source)
        db.refresh(member, attribute_names=["shift_group_links"])
    return member


def update_team_member_self(db: Session, member: TeamMember, payload: TeamMemberSelfUpdate, *, actor: str, source: str) -> TeamMember:
    raw = payload.model_dump(exclude_unset=True)
    if "email" in raw:
        other = db.scalar(
            select(TeamMember).where(
                TeamMember.email == raw["email"],
                TeamMember.id != member.id,
                TeamMember.organization_id == member.organization_id,
            )
        )
        if other is not None:
            raise ValueError("Email already in use")
    for key, value in raw.items():
        setattr(member, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="team_member_self", entity_id=member.id)
    db.commit()
    db.refresh(member)
    return member


def delete_team_member(db: Session, team_member_id: int, *, organization_id: int, actor: str, source: str) -> bool:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        return False
    assignment_ids = list(
        db.scalars(select(RosterSlotAssignment.id).where(RosterSlotAssignment.team_member_id == team_member_id))
    )
    for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.team_member_id == team_member_id)):
        db.delete(assignment)
    for cell in db.scalars(select(PlanningCell).where(PlanningCell.team_member_id == team_member_id)):
        db.delete(cell)
    for note in db.scalars(select(TeamMemberPeriodNote).where(TeamMemberPeriodNote.team_member_id == team_member_id)):
        db.delete(note)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="team_member",
        entity_id=member.id,
        details={"email": member.email, "cleared_assignment_count": len(assignment_ids)},
    )
    db.delete(member)
    db.commit()
    return True
