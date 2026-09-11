import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    PlanningCell,
    PlanningDayStatusDefinition,
    PlanningPeriod,
    PlanningPeriodShiftGroupMember,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroupShiftTemplate,
    TeamMember,
    TeamMemberPlanningPattern,
    TeamMemberPropertyDefinition,
    TeamMemberPropertyValue,
    TimeEntry,
)
from app.services.holidays import classify_day
from app.services.rules.registry import max_lookback, max_roster_lookback, resolve_active_rules
from app.services.rules.state import (
    DutyDayCounts,
    PlanState,
    empty_indexed_state,
    frozen_mapping,
    index_assignments_by_member,
    index_slots_by_date,
)
from app.services.time_entries import (
    SOURCE_ROSTER,
    load_employment_periods_for_members,
    load_time_entries_for_window,
)
from app.services.work_time_consents import load_work_time_consents_for_members

NIGHT_AFTER_HOUR = 21


def _lookback_calendar_days(lookback: timedelta) -> int:
    seconds = lookback.total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)


def _load_bounds(start_date: date, end_date: date, lookback: timedelta) -> tuple[date, date]:
    extra = timedelta(days=_lookback_calendar_days(lookback))
    return start_date - extra, end_date + extra


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


def _month_filters(months: list[tuple[int, int]]):
    return [(PlanningPeriod.year == year) & (PlanningPeriod.month == month) for year, month in months]


def _freeze_roster_index(
    roster: dict[tuple[int, int, int], set[int]],
) -> dict[tuple[int, int, int], frozenset[int]]:
    return {key: frozenset(member_ids) for key, member_ids in roster.items()}


def _fetch_period_roster_index(
    db: Session,
    *,
    organization_id: int,
    months: list[tuple[int, int]],
    shift_group_id: int | None,
) -> dict[tuple[int, int, int], frozenset[int]]:
    if not months:
        return {}
    stmt = (
        select(
            PlanningPeriod.year,
            PlanningPeriod.month,
            PlanningPeriodShiftGroupMember.shift_group_id,
            PlanningPeriodShiftGroupMember.team_member_id,
        )
        .join(PlanningPeriod, PlanningPeriod.id == PlanningPeriodShiftGroupMember.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            or_(*_month_filters(months)),
        )
    )
    if shift_group_id is not None:
        stmt = stmt.where(PlanningPeriodShiftGroupMember.shift_group_id == shift_group_id)
    roster: dict[tuple[int, int, int], set[int]] = defaultdict(set)
    for year, month, group_id, member_id in db.execute(stmt).all():
        roster[(int(year), int(month), int(group_id))].add(int(member_id))
    return _freeze_roster_index(roster)


def _load_members_and_period_roster(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    history_start: date,
    history_end: date,
    shift_group_id: int | None,
    load_history_roster: bool,
) -> tuple[list[TeamMember], dict[tuple[int, int, int], frozenset[int]]]:
    roster_months = set(_year_months(load_start, load_end))
    span_start = min(history_start, load_start)
    span_end = max(history_end, load_end)
    months = _year_months(span_start, span_end)
    if shift_group_id is None:
        members = list(
            db.scalars(select(TeamMember).where(TeamMember.organization_id == organization_id))
        )
        roster_index = (
            _fetch_period_roster_index(
                db, organization_id=organization_id, months=months, shift_group_id=None
            )
            if load_history_roster
            else {}
        )
        return members, roster_index

    if not months:
        return [], {}
    stmt = (
        select(
            TeamMember,
            PlanningPeriod.year,
            PlanningPeriod.month,
            PlanningPeriodShiftGroupMember.shift_group_id,
        )
        .join(
            PlanningPeriodShiftGroupMember,
            PlanningPeriodShiftGroupMember.team_member_id == TeamMember.id,
        )
        .join(PlanningPeriod, PlanningPeriod.id == PlanningPeriodShiftGroupMember.planning_period_id)
        .where(
            TeamMember.organization_id == organization_id,
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriodShiftGroupMember.shift_group_id == shift_group_id,
            or_(*_month_filters(months)),
        )
    )
    members_by_id: dict[int, TeamMember] = {}
    roster: dict[tuple[int, int, int], set[int]] = defaultdict(set)
    for member, year, month, group_id in db.execute(stmt).all():
        roster[(int(year), int(month), int(group_id))].add(member.id)
        if (int(year), int(month)) in roster_months:
            members_by_id[member.id] = member
    return list(members_by_id.values()), _freeze_roster_index(roster)


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


def _load_intents(
    db: Session,
    *,
    organization_id: int,
    load_start: date,
    load_end: date,
    shift_group_id: int | None,
) -> list[PlanningShiftIntent]:
    stmt = (
        select(PlanningShiftIntent)
        .join(PlanningPeriod, PlanningPeriod.id == PlanningShiftIntent.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            PlanningShiftIntent.cell_date >= load_start,
            PlanningShiftIntent.cell_date <= load_end,
        )
    )
    if shift_group_id is not None:
        stmt = stmt.where(PlanningShiftIntent.shift_group_id == shift_group_id)
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


def _load_statutory_minute_totals(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: set[int],
    start_date: date,
    end_date: date,
) -> dict[tuple[int, date], int]:
    if not team_member_ids or end_date < start_date:
        return {}
    rows = db.execute(
        select(
            TimeEntry.team_member_id,
            TimeEntry.entry_date,
            func.coalesce(func.sum(TimeEntry.statutory_minutes), 0),
        )
        .where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.team_member_id.in_(team_member_ids),
            TimeEntry.entry_date >= start_date,
            TimeEntry.entry_date <= end_date,
        )
        .group_by(TimeEntry.team_member_id, TimeEntry.entry_date)
    ).all()
    return {(int(member_id), entry_date): int(total) for member_id, entry_date, total in rows}


def _is_night_duty(entry_date: date, started_at: datetime | None, ended_at: datetime | None) -> bool:
    if ended_at is not None and ended_at.date() > entry_date:
        return True
    return started_at is not None and started_at.hour >= NIGHT_AFTER_HOUR


def _bump_category(counts: dict[str, int], category: str | None) -> None:
    if not category:
        return
    counts[category] = counts.get(category, 0) + 1


def _load_duty_count_totals(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: set[int],
    start_date: date,
    end_date: date,
) -> dict[tuple[int, date], DutyDayCounts]:
    if not team_member_ids or end_date < start_date:
        return {}
    rows = db.execute(
        select(
            TimeEntry.team_member_id,
            TimeEntry.entry_date,
            TimeEntry.shift_template_category,
            TimeEntry.started_at,
            TimeEntry.ended_at,
        ).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.team_member_id.in_(team_member_ids),
            TimeEntry.entry_date >= start_date,
            TimeEntry.entry_date <= end_date,
            TimeEntry.source == SOURCE_ROSTER,
            TimeEntry.shift_template_category.is_not(None),
        )
    ).all()
    totals: dict[tuple[int, date], dict[str, object]] = {}
    for member_id, entry_date, category, started_at, ended_at in rows:
        key = (int(member_id), entry_date)
        bucket = totals.get(key)
        if bucket is None:
            bucket = {
                "total": 0,
                "weekend_holiday": 0,
                "night": 0,
                "by_category": {},
                "weekend_holiday_by_category": {},
                "night_by_category": {},
            }
            totals[key] = bucket
        bucket["total"] = int(bucket["total"]) + 1
        cat = str(category) if category is not None else ""
        _bump_category(bucket["by_category"], cat or None)
        if classify_day(entry_date) in ("weekend", "holiday"):
            bucket["weekend_holiday"] = int(bucket["weekend_holiday"]) + 1
            _bump_category(bucket["weekend_holiday_by_category"], cat or None)
        if _is_night_duty(entry_date, started_at, ended_at):
            bucket["night"] = int(bucket["night"]) + 1
            _bump_category(bucket["night_by_category"], cat or None)
    return {
        key: DutyDayCounts(
            total=int(bucket["total"]),
            weekend_holiday=int(bucket["weekend_holiday"]),
            night=int(bucket["night"]),
            by_category=frozen_mapping(dict(bucket["by_category"])),
            weekend_holiday_by_category=frozen_mapping(dict(bucket["weekend_holiday_by_category"])),
            night_by_category=frozen_mapping(dict(bucket["night_by_category"])),
        )
        for key, bucket in totals.items()
    }


def build_plan_state(
    db: Session,
    *,
    organization_id: int,
    start_date: date,
    end_date: date,
    shift_group_id: int | None = None,
    history_start: date | None = None,
) -> PlanState:
    if end_date < start_date:
        return empty_indexed_state(
            organization_id=organization_id,
            start_date=start_date,
            end_date=end_date,
            load_start=start_date,
            load_end=end_date,
            shift_group_id=shift_group_id,
        )

    rules = resolve_active_rules(organization_id, start_date, end_date, db=db)
    roster_lookback = max_roster_lookback(rules)
    history_lookback = max_lookback(rules)
    load_start, load_end = _load_bounds(start_date, end_date, roster_lookback)
    rules_history_start, _history_end = _load_bounds(start_date, end_date, history_lookback)
    requested_history_start = history_start
    effective_history_start = rules_history_start
    if requested_history_start is not None:
        effective_history_start = min(effective_history_start, requested_history_start)
    history_end = end_date
    load_history_aggregates = (
        effective_history_start < load_start or requested_history_start is not None
    )
    employment_start = min(load_start, effective_history_start)

    members, period_roster_member_ids = _load_members_and_period_roster(
        db,
        organization_id=organization_id,
        load_start=load_start,
        load_end=load_end,
        history_start=effective_history_start,
        history_end=history_end,
        shift_group_id=shift_group_id,
        load_history_roster=requested_history_start is not None,
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
    intents = _load_intents(
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
    property_definitions = list(
        db.scalars(
            select(TeamMemberPropertyDefinition).where(
                TeamMemberPropertyDefinition.organization_id == organization_id
            )
        )
    )

    patterns_grouped: dict[int, list[TeamMemberPlanningPattern]] = {}
    for pattern in patterns:
        patterns_grouped.setdefault(pattern.team_member_id, []).append(pattern)
    for member_id, rows in patterns_grouped.items():
        patterns_grouped[member_id] = sorted(rows, key=lambda item: (item.display_order, item.id))

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
        property_definitions_by_id=frozen_mapping({row.id: row for row in property_definitions}),
        shift_intents=tuple(intents),
        time_entries_by_member_id=frozen_mapping(
            load_time_entries_for_window(
                db,
                organization_id=organization_id,
                team_member_ids=member_ids,
                start_date=load_start,
                end_date=load_end,
            )
        ),
        employment_periods_by_member_id=frozen_mapping(
            load_employment_periods_for_members(
                db,
                team_member_ids=member_ids,
                start_date=employment_start,
                end_date=end_date,
            )
        ),
        statutory_minutes_by_member_date=frozen_mapping(
            _load_statutory_minute_totals(
                db,
                organization_id=organization_id,
                team_member_ids=member_ids,
                start_date=effective_history_start,
                end_date=history_end,
            )
            if load_history_aggregates
            else {}
        ),
        duty_counts_by_member_date=frozen_mapping(
            _load_duty_count_totals(
                db,
                organization_id=organization_id,
                team_member_ids=member_ids,
                start_date=effective_history_start,
                end_date=history_end,
            )
            if load_history_aggregates
            else {}
        ),
        period_roster_member_ids=frozen_mapping(period_roster_member_ids),
        work_time_consents_by_member_id=frozen_mapping(
            load_work_time_consents_for_members(
                db,
                organization_id=organization_id,
                team_member_ids=member_ids,
            )
            if any(getattr(rule, "code", None) == "WORKTIME_WEEKLY_AVERAGE_OPT_OUT" for rule in rules)
            else {}
        ),
    )
