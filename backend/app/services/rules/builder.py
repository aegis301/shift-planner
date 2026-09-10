import math
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    PlanningCell,
    PlanningDayStatusDefinition,
    PlanningPeriod,
    PlanningPeriodShiftGroupMember,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroupShiftTemplate,
    TeamMember,
    TeamMemberPlanningPattern,
    TeamMemberPropertyValue,
)
from app.services.rules.registry import max_lookback, resolve_active_rules
from app.services.rules.state import (
    PlanState,
    empty_indexed_state,
    frozen_mapping,
    index_assignments_by_member,
    index_slots_by_date,
)


def _lookback_calendar_days(lookback: timedelta) -> int:
    seconds = lookback.total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)


def _load_bounds(start_date: date, end_date: date, lookback: timedelta) -> tuple[date, date]:
    return start_date - timedelta(days=_lookback_calendar_days(lookback)), end_date


def _year_months(start: date, end: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def _load_members(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    shift_group_id: int | None,
) -> list[TeamMember]:
    if shift_group_id is None:
        stmt = select(TeamMember).where(TeamMember.organization_id == organization_id)
        return list(db.scalars(stmt))

    months = _year_months(load_start, load_end)
    if not months:
        return []
    month_filters = [
        (PlanningPeriod.year == year) & (PlanningPeriod.month == month) for year, month in months
    ]
    stmt = (
        select(TeamMember)
        .join(
            PlanningPeriodShiftGroupMember,
            PlanningPeriodShiftGroupMember.team_member_id == TeamMember.id,
        )
        .join(PlanningPeriod, PlanningPeriod.id == PlanningPeriodShiftGroupMember.planning_period_id)
        .where(
            TeamMember.organization_id == organization_id,
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriodShiftGroupMember.shift_group_id == shift_group_id,
            or_(*month_filters),
        )
    )
    return list(db.scalars(stmt).unique())


def _template_ids_for_group(db: Session, shift_group_id: int | None) -> set[int] | None:
    if shift_group_id is None:
        return None
    rows = db.scalars(
        select(ShiftGroupShiftTemplate.shift_template_id).where(
            ShiftGroupShiftTemplate.shift_group_id == shift_group_id
        )
    ).all()
    return set(rows)


def _load_slots(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    template_ids: set[int] | None,
) -> list[RosterSlot]:
    stmt = (
        select(RosterSlot)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.shift_variant))
        .where(
            PlanningPeriod.organization_id == organization_id,
            RosterSlot.slot_date >= load_start,
            RosterSlot.slot_date <= load_end,
        )
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.id)
    )
    if template_ids is not None:
        stmt = stmt.where(RosterSlot.shift_template_id.in_(template_ids))
    return list(db.scalars(stmt).unique())


def _load_assignments(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    template_ids: set[int] | None,
) -> list[RosterSlotAssignment]:
    stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .options(
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_template),
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlotAssignment.team_member),
        )
        .where(
            PlanningPeriod.organization_id == organization_id,
            RosterSlot.slot_date >= load_start,
            RosterSlot.slot_date <= load_end,
        )
        .order_by(RosterSlotAssignment.id)
    )
    if template_ids is not None:
        stmt = stmt.where(RosterSlot.shift_template_id.in_(template_ids))
    return list(db.scalars(stmt).unique())


def _load_cells(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    shift_group_id: int | None,
) -> list[PlanningCell]:
    stmt = (
        select(PlanningCell)
        .join(PlanningPeriod, PlanningPeriod.id == PlanningCell.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            PlanningCell.cell_date >= load_start,
            PlanningCell.cell_date <= load_end,
        )
    )
    if shift_group_id is not None:
        stmt = stmt.where(PlanningCell.shift_group_id == shift_group_id)
    return list(db.scalars(stmt))


def _load_day_statuses(db: Session, *, organization_id: int) -> list[PlanningDayStatusDefinition]:
    return list(
        db.scalars(
            select(PlanningDayStatusDefinition).where(
                PlanningDayStatusDefinition.organization_id == organization_id
            )
        )
    )


def _load_patterns(
    db: Session, *, organization_id: int, team_member_ids: set[int]
) -> list[TeamMemberPlanningPattern]:
    if not team_member_ids:
        return []
    return list(
        db.scalars(
            select(TeamMemberPlanningPattern).where(
                TeamMemberPlanningPattern.organization_id == organization_id,
                TeamMemberPlanningPattern.team_member_id.in_(team_member_ids),
            )
        )
    )


def _load_property_values(
    db: Session, *, organization_id: int, team_member_ids: set[int]
) -> list[TeamMemberPropertyValue]:
    if not team_member_ids:
        return []
    return list(
        db.scalars(
            select(TeamMemberPropertyValue).where(
                TeamMemberPropertyValue.organization_id == organization_id,
                TeamMemberPropertyValue.team_member_id.in_(team_member_ids),
            )
        )
    )


def build_plan_state(
    db: Session,
    *,
    organization_id: int,
    start_date: date,
    end_date: date,
    shift_group_id: int | None = None,
) -> PlanState:
    rules = resolve_active_rules(organization_id, start_date, end_date)
    lookback = max_lookback(rules)
    load_start, load_end = _load_bounds(start_date, end_date, lookback)

    if end_date < start_date:
        return empty_indexed_state(
            organization_id=organization_id,
            start_date=start_date,
            end_date=end_date,
            load_start=load_start,
            load_end=load_end,
            shift_group_id=shift_group_id,
        )

    members = _load_members(
        db,
        organization_id=organization_id,
        load_start=load_start,
        load_end=load_end,
        shift_group_id=shift_group_id,
    )
    template_ids = _template_ids_for_group(db, shift_group_id)
    slots = _load_slots(
        db,
        organization_id=organization_id,
        load_start=load_start,
        load_end=load_end,
        template_ids=template_ids,
    )
    assignments = _load_assignments(
        db,
        organization_id=organization_id,
        load_start=load_start,
        load_end=load_end,
        template_ids=template_ids,
    )
    cells = _load_cells(
        db,
        organization_id=organization_id,
        load_start=load_start,
        load_end=load_end,
        shift_group_id=shift_group_id,
    )
    day_statuses = _load_day_statuses(db, organization_id=organization_id)
    member_ids = {member.id for member in members}
    patterns = _load_patterns(db, organization_id=organization_id, team_member_ids=member_ids)
    property_values = _load_property_values(
        db, organization_id=organization_id, team_member_ids=member_ids
    )

    patterns_grouped: dict[int, list[TeamMemberPlanningPattern]] = {}
    for pattern in patterns:
        patterns_grouped.setdefault(pattern.team_member_id, []).append(pattern)

    property_maps: dict[int, dict[int, object]] = {}
    for row in property_values:
        property_maps.setdefault(row.team_member_id, {})[row.property_definition_id] = row.value

    return PlanState(
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
        load_start=load_start,
        load_end=load_end,
        shift_group_id=shift_group_id,
        members_by_id=frozen_mapping({member.id: member for member in members}),
        slots_by_id=frozen_mapping({slot.id: slot for slot in slots}),
        slots_by_date=index_slots_by_date(slots),
        assignments_by_id=frozen_mapping({row.id: row for row in assignments}),
        assignments_by_slot_id=frozen_mapping({row.roster_slot_id: row for row in assignments}),
        assignments_by_member_id=index_assignments_by_member(assignments),
        cells_by_member_date_group=frozen_mapping(
            {(cell.team_member_id, cell.cell_date, cell.shift_group_id): cell for cell in cells}
        ),
        day_status_by_code=frozen_mapping({row.code: row for row in day_statuses}),
        patterns_by_member_id=frozen_mapping(
            {member_id: tuple(rows) for member_id, rows in patterns_grouped.items()}
        ),
        property_values_by_member_id=frozen_mapping(
            {member_id: frozen_mapping(values) for member_id, values in property_maps.items()}
        ),
        time_entries_by_member_id=frozen_mapping({}),
        employment_periods_by_member_id=frozen_mapping({}),
    )
