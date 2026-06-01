from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ShiftGroup,
    ShiftGroupShiftTemplate,
    ShiftTemplate,
    TeamMember,
    TeamMemberShiftGroup,
    User,
)
from app.schemas import ShiftGroupCreate, ShiftGroupUpdate
from app.services.audit import record_audit


def list_shift_template_ids_with_any_group(db: Session, organization_id: int) -> set[int]:
    rows = db.scalars(
        select(ShiftGroupShiftTemplate.shift_template_id)
        .join(ShiftGroup, ShiftGroup.id == ShiftGroupShiftTemplate.shift_group_id)
        .where(ShiftGroup.organization_id == organization_id)
        .distinct()
    ).all()
    return set(rows)


def team_member_may_cover_template(db: Session, *, team_member_id: int, shift_template_id: int | None) -> bool:
    member = db.get(TeamMember, team_member_id)
    if member is None:
        return False
    if shift_template_id is None:
        return True
    if shift_template_id not in list_shift_template_ids_with_any_group(db, member.organization_id):
        return True
    stmt = (
        select(TeamMemberShiftGroup.id)
        .join(ShiftGroupShiftTemplate, ShiftGroupShiftTemplate.shift_group_id == TeamMemberShiftGroup.shift_group_id)
        .where(
            TeamMemberShiftGroup.team_member_id == team_member_id,
            ShiftGroupShiftTemplate.shift_template_id == shift_template_id,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def get_shift_group_or_none(db: Session, shift_group_id: int) -> ShiftGroup | None:
    return db.get(ShiftGroup, shift_group_id)


def require_shift_group(db: Session, shift_group_id: int, organization_id: int | None = None) -> ShiftGroup:
    group = get_shift_group_or_none(db, shift_group_id)
    if group is None:
        raise ValueError("Shift group not found")
    if organization_id is not None and group.organization_id != organization_id:
        raise ValueError("Shift group not found")
    return group


def active_team_member_ids_in_shift_group(db: Session, shift_group_id: int) -> set[int]:
    stmt = (
        select(TeamMemberShiftGroup.team_member_id)
        .join(TeamMember, TeamMember.id == TeamMemberShiftGroup.team_member_id)
        .where(TeamMemberShiftGroup.shift_group_id == shift_group_id, TeamMember.is_active.is_(True))
    )
    return set(db.scalars(stmt).all())


def shift_template_ids_in_shift_group(db: Session, shift_group_id: int) -> set[int]:
    stmt = select(ShiftGroupShiftTemplate.shift_template_id).where(ShiftGroupShiftTemplate.shift_group_id == shift_group_id)
    return set(db.scalars(stmt).all())


def list_shift_groups(db: Session, *, organization_id: int, active_only: bool = False) -> list[ShiftGroup]:
    stmt = (
        select(ShiftGroup)
        .options(joinedload(ShiftGroup.team_member_links), joinedload(ShiftGroup.template_links))
        .where(ShiftGroup.organization_id == organization_id)
    )
    if active_only:
        stmt = stmt.where(ShiftGroup.is_active.is_(True))
    stmt = stmt.order_by(ShiftGroup.display_order, ShiftGroup.code)
    return list(db.scalars(stmt).unique())


def list_shift_groups_for_planner(db: Session, *, user: User, active_only: bool = False) -> list[ShiftGroup]:
    from app.services.authz import is_admin, planner_shift_group_ids

    if is_admin(user):
        return list_shift_groups(db, organization_id=user.organization_id, active_only=active_only)
    gids = planner_shift_group_ids(db, user)
    if not gids:
        return []
    stmt = (
        select(ShiftGroup)
        .options(joinedload(ShiftGroup.team_member_links), joinedload(ShiftGroup.template_links))
        .where(ShiftGroup.organization_id == user.organization_id, ShiftGroup.id.in_(gids))
    )
    if active_only:
        stmt = stmt.where(ShiftGroup.is_active.is_(True))
    stmt = stmt.order_by(ShiftGroup.display_order, ShiftGroup.code)
    return list(db.scalars(stmt).unique())


def create_shift_group(
    db: Session, payload: ShiftGroupCreate, *, organization_id: int, actor: str, source: str
) -> ShiftGroup:
    group = ShiftGroup(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name.strip(),
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(group)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="shift_group", entity_id=group.id)
    db.commit()
    db.refresh(group)
    return group


def update_shift_group(
    db: Session, shift_group_id: int, payload: ShiftGroupUpdate, *, organization_id: int, actor: str, source: str
) -> ShiftGroup | None:
    group = db.get(ShiftGroup, shift_group_id)
    if group is None or group.organization_id != organization_id:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="shift_group", entity_id=group.id)
    db.commit()
    db.refresh(group)
    return group


def delete_shift_group(db: Session, shift_group_id: int, *, organization_id: int, actor: str, source: str) -> bool:
    group = db.get(ShiftGroup, shift_group_id)
    if group is None or group.organization_id != organization_id:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="shift_group",
        entity_id=group.id,
        details={"code": group.code},
    )
    db.delete(group)
    db.commit()
    return True


def replace_group_team_members(
    db: Session, shift_group_id: int, team_member_ids: list[int], *, organization_id: int, actor: str, source: str
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    db.execute(delete(TeamMemberShiftGroup).where(TeamMemberShiftGroup.shift_group_id == shift_group_id))
    for team_member_id in sorted(set(team_member_ids)):
        db.add(TeamMemberShiftGroup(team_member_id=team_member_id, shift_group_id=shift_group_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="shift_group_team_members",
        entity_id=shift_group_id,
        details={"team_member_ids": sorted(set(team_member_ids))},
    )
    db.commit()


def replace_group_shift_templates(
    db: Session, shift_group_id: int, shift_template_ids: list[int], *, organization_id: int, actor: str, source: str
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    for tid in set(shift_template_ids):
        template = db.get(ShiftTemplate, tid)
        if template is None or template.organization_id != organization_id:
            raise ValueError(f"Shift template not found: {tid}")
    db.execute(delete(ShiftGroupShiftTemplate).where(ShiftGroupShiftTemplate.shift_group_id == shift_group_id))
    for template_id in sorted(set(shift_template_ids)):
        db.add(ShiftGroupShiftTemplate(shift_group_id=shift_group_id, shift_template_id=template_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="shift_group_templates",
        entity_id=shift_group_id,
        details={"shift_template_ids": sorted(set(shift_template_ids))},
    )
    db.commit()


def replace_team_member_shift_groups(
    db: Session, team_member_id: int, shift_group_ids: list[int], *, actor: str, source: str, transactional: bool = True
) -> None:
    member = db.get(TeamMember, team_member_id)
    if member is None:
        raise ValueError("Team member not found")
    for gid in set(shift_group_ids):
        require_shift_group(db, gid, member.organization_id)
    db.execute(delete(TeamMemberShiftGroup).where(TeamMemberShiftGroup.team_member_id == team_member_id))
    for shift_group_id in sorted(set(shift_group_ids)):
        db.add(TeamMemberShiftGroup(team_member_id=team_member_id, shift_group_id=shift_group_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="team_member_shift_groups",
        entity_id=team_member_id,
        details={"shift_group_ids": sorted(set(shift_group_ids))},
    )
    if transactional:
        db.commit()
    else:
        db.flush()
