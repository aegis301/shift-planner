import calendar
from datetime import date

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ShiftGroup,
    ShiftGroupShiftTemplate,
    ShiftTemplate,
    TeamMember,
    TeamMemberShiftGroup,
    User,
)
from app.schemas import (
    ShiftGroupCreate,
    ShiftGroupMembershipRead,
    ShiftGroupMembershipWrite,
    ShiftGroupUpdate,
)
from app.services.audit import record_audit


def _stint_active_on(stint: TeamMemberShiftGroup, on_date: date) -> bool:
    if stint.start_date > on_date:
        return False
    return not (stint.end_date is not None and stint.end_date < on_date)


def _stint_overlaps_range(
    start_date: date,
    end_date: date | None,
    range_start: date,
    range_end: date,
) -> bool:
    stint_end = end_date if end_date is not None else date.max
    return start_date <= range_end and stint_end >= range_start


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _membership_read(link: TeamMemberShiftGroup) -> ShiftGroupMembershipRead:
    return ShiftGroupMembershipRead(
        id=link.id,
        team_member_id=link.team_member_id,
        shift_group_id=link.shift_group_id,
        start_date=link.start_date,
        end_date=link.end_date,
    )


def list_shift_template_ids_with_any_group(db: Session, organization_id: int) -> set[int]:
    rows = db.scalars(
        select(ShiftGroupShiftTemplate.shift_template_id)
        .join(ShiftGroup, ShiftGroup.id == ShiftGroupShiftTemplate.shift_group_id)
        .where(ShiftGroup.organization_id == organization_id)
        .distinct()
    ).all()
    return set(rows)


def shift_group_ids_for_template(db: Session, shift_template_id: int) -> set[int]:
    stmt = select(ShiftGroupShiftTemplate.shift_group_id).where(
        ShiftGroupShiftTemplate.shift_template_id == shift_template_id
    )
    return set(db.scalars(stmt).all())


def team_member_may_cover_template(
    db: Session, *, team_member_id: int, shift_template_id: int | None, on_date: date | None = None
) -> bool:
    member = db.get(TeamMember, team_member_id)
    if member is None:
        return False
    if shift_template_id is None:
        return True
    if shift_template_id not in list_shift_template_ids_with_any_group(db, member.organization_id):
        return True
    on = on_date or date.today()
    start_ok, end_ok = _active_stint_filter(on)
    stmt = (
        select(TeamMemberShiftGroup.id)
        .join(ShiftGroupShiftTemplate, ShiftGroupShiftTemplate.shift_group_id == TeamMemberShiftGroup.shift_group_id)
        .where(
            TeamMemberShiftGroup.team_member_id == team_member_id,
            ShiftGroupShiftTemplate.shift_template_id == shift_template_id,
            start_ok,
            end_ok,
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


def _active_stint_filter(on_date: date):
    return (
        TeamMemberShiftGroup.start_date <= on_date,
        or_(TeamMemberShiftGroup.end_date.is_(None), TeamMemberShiftGroup.end_date >= on_date),
    )


def team_member_ids_in_shift_group_for_date(
    db: Session, shift_group_id: int, on_date: date, *, active_members_only: bool = True
) -> set[int]:
    start_ok, end_ok = _active_stint_filter(on_date)
    stmt = (
        select(TeamMemberShiftGroup.team_member_id)
        .join(TeamMember, TeamMember.id == TeamMemberShiftGroup.team_member_id)
        .where(
            TeamMemberShiftGroup.shift_group_id == shift_group_id,
            start_ok,
            end_ok,
        )
    )
    if active_members_only:
        stmt = stmt.where(TeamMember.is_active.is_(True))
    return set(db.scalars(stmt).all())


def team_member_ids_in_shift_group_for_period(
    db: Session,
    shift_group_id: int,
    *,
    year: int,
    month: int,
    active_members_only: bool = True,
) -> set[int]:
    month_start, month_end = _month_bounds(year, month)
    stmt = (
        select(TeamMemberShiftGroup.team_member_id)
        .join(TeamMember, TeamMember.id == TeamMemberShiftGroup.team_member_id)
        .where(
            TeamMemberShiftGroup.shift_group_id == shift_group_id,
            TeamMemberShiftGroup.start_date <= month_end,
            or_(TeamMemberShiftGroup.end_date.is_(None), TeamMemberShiftGroup.end_date >= month_start),
        )
    )
    if active_members_only:
        stmt = stmt.where(TeamMember.is_active.is_(True))
    return set(db.scalars(stmt).all())


def active_team_member_ids_in_shift_group(db: Session, shift_group_id: int) -> set[int]:
    return team_member_ids_in_shift_group_for_date(db, shift_group_id, date.today())


def active_shift_group_ids_for_team_member(db: Session, team_member_id: int, on_date: date | None = None) -> set[int]:
    on = on_date or date.today()
    start_ok, end_ok = _active_stint_filter(on)
    stmt = select(TeamMemberShiftGroup.shift_group_id).where(
        TeamMemberShiftGroup.team_member_id == team_member_id,
        start_ok,
        end_ok,
    )
    return set(db.scalars(stmt).all())


def list_shift_group_memberships(
    db: Session, *, shift_group_id: int | None = None, team_member_id: int | None = None
) -> list[TeamMemberShiftGroup]:
    stmt = select(TeamMemberShiftGroup)
    if shift_group_id is not None:
        stmt = stmt.where(TeamMemberShiftGroup.shift_group_id == shift_group_id)
    if team_member_id is not None:
        stmt = stmt.where(TeamMemberShiftGroup.team_member_id == team_member_id)
    stmt = stmt.order_by(
        TeamMemberShiftGroup.shift_group_id,
        TeamMemberShiftGroup.team_member_id,
        TeamMemberShiftGroup.start_date,
    )
    return list(db.scalars(stmt))


def _assert_no_overlap(
    db: Session,
    *,
    team_member_id: int,
    shift_group_id: int,
    start_date: date,
    end_date: date | None,
    exclude_id: int | None = None,
) -> None:
    stmt = select(TeamMemberShiftGroup).where(
        TeamMemberShiftGroup.team_member_id == team_member_id,
        TeamMemberShiftGroup.shift_group_id == shift_group_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(TeamMemberShiftGroup.id != exclude_id)
    for existing in db.scalars(stmt):
        if _stint_overlaps_range(existing.start_date, existing.end_date, start_date, end_date or date.max):
            raise ValueError("Shift group membership stints overlap")


def add_team_member_shift_group_stint(
    db: Session,
    *,
    team_member_id: int,
    shift_group_id: int,
    start_date: date,
    end_date: date | None = None,
    actor: str,
    source: str,
    transactional: bool = True,
) -> TeamMemberShiftGroup:
    member = db.get(TeamMember, team_member_id)
    if member is None:
        raise ValueError("Team member not found")
    require_shift_group(db, shift_group_id, member.organization_id)
    if end_date is not None and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    _assert_no_overlap(
        db,
        team_member_id=team_member_id,
        shift_group_id=shift_group_id,
        start_date=start_date,
        end_date=end_date,
    )
    link = TeamMemberShiftGroup(
        team_member_id=team_member_id,
        shift_group_id=shift_group_id,
        start_date=start_date,
        end_date=end_date,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="team_member_shift_group_stint",
        entity_id=link.id,
        details={
            "team_member_id": team_member_id,
            "shift_group_id": shift_group_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat() if end_date else None,
        },
    )
    if transactional:
        db.commit()
    else:
        db.flush()
    return link


def end_team_member_shift_group_stint(
    db: Session,
    *,
    team_member_id: int,
    shift_group_id: int,
    end_date: date,
    actor: str,
    source: str,
    transactional: bool = True,
) -> TeamMemberShiftGroup | None:
    today = date.today()
    stmt = select(TeamMemberShiftGroup).where(
        TeamMemberShiftGroup.team_member_id == team_member_id,
        TeamMemberShiftGroup.shift_group_id == shift_group_id,
    )
    active: TeamMemberShiftGroup | None = None
    for stint in db.scalars(stmt):
        if _stint_active_on(stint, today):
            active = stint
            break
    if active is None:
        return None
    if end_date < active.start_date:
        raise ValueError("end_date must be on or after start_date")
    active.end_date = end_date
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="end_stint",
        entity_type="team_member_shift_group_stint",
        entity_id=active.id,
        details={
            "team_member_id": team_member_id,
            "shift_group_id": shift_group_id,
            "end_date": end_date.isoformat(),
        },
    )
    if transactional:
        db.commit()
    else:
        db.flush()
    return active


def replace_group_team_members(
    db: Session,
    shift_group_id: int,
    team_member_ids: list[int],
    *,
    organization_id: int,
    actor: str,
    source: str,
    effective_date: date | None = None,
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    on_date = effective_date or date.today()
    desired = set(team_member_ids)
    current = team_member_ids_in_shift_group_for_date(db, shift_group_id, on_date)
    for team_member_id in sorted(current - desired):
        end_team_member_shift_group_stint(
            db,
            team_member_id=team_member_id,
            shift_group_id=shift_group_id,
            end_date=on_date,
            actor=actor,
            source=source,
            transactional=False,
        )
    for team_member_id in sorted(desired - current):
        member = db.get(TeamMember, team_member_id)
        if member is None or member.organization_id != organization_id:
            raise ValueError(f"Team member not found: {team_member_id}")
        add_team_member_shift_group_stint(
            db,
            team_member_id=team_member_id,
            shift_group_id=shift_group_id,
            start_date=on_date,
            end_date=None,
            actor=actor,
            source=source,
            transactional=False,
        )
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="shift_group_team_members",
        entity_id=shift_group_id,
        details={"team_member_ids": sorted(desired), "effective_date": on_date.isoformat()},
    )
    db.commit()


def replace_group_team_member_memberships(
    db: Session,
    shift_group_id: int,
    memberships: list[ShiftGroupMembershipWrite],
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    for row in memberships:
        member = db.get(TeamMember, row.team_member_id)
        if member is None or member.organization_id != organization_id:
            raise ValueError(f"Team member not found: {row.team_member_id}")
        if row.end_date is not None and row.end_date < row.start_date:
            raise ValueError("end_date must be on or after start_date")

    by_member: dict[int, list[ShiftGroupMembershipWrite]] = {}
    for row in memberships:
        by_member.setdefault(row.team_member_id, []).append(row)
    for rows in by_member.values():
        ordered = sorted(rows, key=lambda item: item.start_date)
        for index, row in enumerate(ordered[1:], start=1):
            previous = ordered[index - 1]
            if _stint_overlaps_range(
                previous.start_date, previous.end_date, row.start_date, row.end_date or date.max
            ):
                raise ValueError("Shift group membership stints overlap")

    db.execute(delete(TeamMemberShiftGroup).where(TeamMemberShiftGroup.shift_group_id == shift_group_id))
    for row in sorted(memberships, key=lambda item: (item.team_member_id, item.start_date)):
        db.add(
            TeamMemberShiftGroup(
                team_member_id=row.team_member_id,
                shift_group_id=shift_group_id,
                start_date=row.start_date,
                end_date=row.end_date,
            )
        )
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_memberships",
        entity_type="shift_group_team_members",
        entity_id=shift_group_id,
        details={
            "memberships": [
                {
                    "team_member_id": row.team_member_id,
                    "start_date": row.start_date.isoformat(),
                    "end_date": row.end_date.isoformat() if row.end_date else None,
                }
                for row in sorted(memberships, key=lambda item: (item.team_member_id, item.start_date))
            ]
        },
    )
    db.commit()


def replace_team_member_shift_groups(
    db: Session,
    team_member_id: int,
    shift_group_ids: list[int],
    *,
    actor: str,
    source: str,
    transactional: bool = True,
    effective_date: date | None = None,
) -> None:
    member = db.get(TeamMember, team_member_id)
    if member is None:
        raise ValueError("Team member not found")
    on_date = effective_date or date.today()
    desired = set(shift_group_ids)
    for gid in desired:
        require_shift_group(db, gid, member.organization_id)
    current = active_shift_group_ids_for_team_member(db, team_member_id, on_date)
    for shift_group_id in sorted(current - desired):
        end_team_member_shift_group_stint(
            db,
            team_member_id=team_member_id,
            shift_group_id=shift_group_id,
            end_date=on_date,
            actor=actor,
            source=source,
            transactional=False,
        )
    for shift_group_id in sorted(desired - current):
        add_team_member_shift_group_stint(
            db,
            team_member_id=team_member_id,
            shift_group_id=shift_group_id,
            start_date=on_date,
            end_date=None,
            actor=actor,
            source=source,
            transactional=False,
        )
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="team_member_shift_groups",
        entity_id=team_member_id,
        details={"shift_group_ids": sorted(desired), "effective_date": on_date.isoformat()},
    )
    if transactional:
        db.commit()
    else:
        db.flush()


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
    from app.services.planning import ensure_shift_group_statuses_for_new_group

    ensure_shift_group_statuses_for_new_group(
        db, shift_group_id=group.id, organization_id=organization_id
    )
    db.commit()
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
