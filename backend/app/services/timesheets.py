from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    EmploymentPeriod,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TimeAccountOpening,
    TimeEntry,
    WorkerGroup,
)
from app.schemas import (
    TimeEntryCreate,
    TimesheetDayPlanInterval,
    TimesheetDayRead,
    TimesheetRead,
    TimesheetSummaryRead,
)
from app.services.employment_periods import employment_on_date, list_employment_periods
from app.services.shift_intervals import resolve_slot_interval
from app.services.team_members import team_member_planning_display_name
from app.services.time_entries import (
    category_rule_for,
    create_time_entry,
    expected_minutes_for_day,
    list_time_entries,
    list_time_entries_for_members,
    minutes_from_interval,
    pattern_minutes,
    status_mapping_for,
    time_entry_to_read,
)
from app.services.worker_groups import get_worker_group_or_none


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _groups_by_id(db: Session, organization_id: int) -> dict[int, WorkerGroup]:
    rows = db.scalars(select(WorkerGroup).where(WorkerGroup.organization_id == organization_id)).all()
    return {row.id: row for row in rows}


def _load_roster_plan(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: list[int],
    from_date: date,
    to_date: date,
) -> dict[tuple[int, date], list[TimesheetDayPlanInterval]]:
    if not team_member_ids:
        return {}
    stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .options(
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_template),
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_variant),
        )
        .where(
            RosterSlotAssignment.team_member_id.in_(team_member_ids),
            RosterSlot.slot_date >= from_date,
            RosterSlot.slot_date <= to_date,
            PlanningPeriod.organization_id == organization_id,
        )
    )
    out: dict[tuple[int, date], list[TimesheetDayPlanInterval]] = {}
    for assignment in db.scalars(stmt).unique():
        slot = assignment.roster_slot
        if slot is None:
            continue
        template = slot.shift_template
        if template is not None and template.organization_id != organization_id:
            continue
        interval = resolve_slot_interval(db, slot)
        duration = minutes_from_interval(interval[0], interval[1]) if interval is not None else 0
        category = template.category if template is not None else None
        key = (assignment.team_member_id, slot.slot_date)
        out.setdefault(key, []).append(
            TimesheetDayPlanInterval(
                started_at=interval[0] if interval is not None else slot.starts_at,
                ended_at=interval[1] if interval is not None else slot.ends_at,
                duration_minutes=duration,
                category=category,
                roster_slot_id=slot.id,
                counts_toward_contract=True,
            )
        )
    return out


def _opening_map(db: Session, *, organization_id: int, team_member_ids: list[int]) -> dict[int, TimeAccountOpening]:
    if not team_member_ids:
        return {}
    rows = db.scalars(
        select(TimeAccountOpening).where(
            TimeAccountOpening.organization_id == organization_id,
            TimeAccountOpening.team_member_id.in_(team_member_ids),
        )
    )
    return {row.team_member_id: row for row in rows}


def _periods_map(db: Session, *, organization_id: int, team_member_ids: list[int]) -> dict[int, list[EmploymentPeriod]]:
    if not team_member_ids:
        return {}
    rows = db.scalars(
        select(EmploymentPeriod)
        .options(joinedload(EmploymentPeriod.worker_group))
        .where(
            EmploymentPeriod.organization_id == organization_id,
            EmploymentPeriod.team_member_id.in_(team_member_ids),
        )
    ).unique()
    out: dict[int, list[EmploymentPeriod]] = {member_id: [] for member_id in team_member_ids}
    for row in rows:
        out.setdefault(row.team_member_id, []).append(row)
    for member_id in out:
        out[member_id].sort(key=lambda item: (item.start_date, item.id))
    return out


def _year_entitlement(group: WorkerGroup | None, percentage: int) -> float:
    if group is None:
        return 0.0
    return float(group.vacation_days_at_100) * percentage / 100


def compute_member_timesheet(
    db: Session,
    *,
    member: TeamMember,
    organization_id: int,
    from_date: date,
    to_date: date,
    periods: list[EmploymentPeriod] | None = None,
    entries: list[TimeEntry] | None = None,
    opening: TimeAccountOpening | None = None,
    roster_plan: dict[date, list[TimesheetDayPlanInterval]] | None = None,
    groups: dict[int, WorkerGroup] | None = None,
) -> TimesheetRead:
    if from_date > to_date:
        raise ValueError("from_date must be on or before to_date")
    periods = periods if periods is not None else list_employment_periods(
        db, team_member_id=member.id, organization_id=organization_id
    )
    entries = entries if entries is not None else list_time_entries(
        db,
        team_member_id=member.id,
        organization_id=organization_id,
        from_date=from_date,
        to_date=to_date,
    )
    if groups is None:
        groups = _groups_by_id(db, organization_id)
    year_start = date(from_date.year, 1, 1)
    ledger_start = year_start
    overtime = 0
    vacation_remaining = 0.0
    year_emp = employment_on_date(periods, year_start) or (periods[0] if periods else None)
    if year_emp is not None:
        vacation_remaining = _year_entitlement(groups.get(year_emp.worker_group_id), year_emp.employment_percentage)
    if opening is not None:
        overtime = opening.overtime_minutes
        vacation_remaining = float(opening.vacation_days_remaining)
        ledger_start = opening.as_of_date + timedelta(days=1)

    history_start = min(ledger_start, from_date)
    history_end = to_date
    if history_start <= history_end:
        history_entries = list_time_entries(
            db,
            team_member_id=member.id,
            organization_id=organization_id,
            from_date=history_start,
            to_date=history_end,
        )
    else:
        history_entries = entries
    entries_by_day: dict[date, list[TimeEntry]] = {}
    for item in history_entries:
        entries_by_day.setdefault(item.entry_date, []).append(item)

    range_entries_by_day: dict[date, list[TimeEntry]] = {}
    for item in entries:
        range_entries_by_day.setdefault(item.entry_date, []).append(item)

    days: list[TimesheetDayRead] = []
    expected_total = 0
    contract_total = 0
    extra_total = 0
    vacation_days = 0.0
    sick_days = 0.0
    overtime_at_end = overtime
    vacation_at_end = vacation_remaining
    active_name: str | None = None
    active_pct: int | None = None

    for on_date in iter_dates(history_start, to_date):
        emp = employment_on_date(periods, on_date)
        group = groups.get(emp.worker_group_id) if emp is not None else None
        expected = expected_minutes_for_day(
            group=group,
            employment_percentage=emp.employment_percentage if emp is not None else 0,
            on_date=on_date,
        )
        day_entries = entries_by_day.get(on_date, [])
        contract_min = 0
        extra_min = 0
        absence_kind: str | None = None
        vac = 0.0
        sick = 0.0
        for entry in day_entries:
            if entry.kind == "work":
                if entry.counts_toward_contract:
                    contract_min += entry.duration_minutes
                else:
                    extra_min += entry.duration_minutes
            elif entry.kind == "absence":
                mapping = status_mapping_for(group, entry.planning_day_status_code)
                kind = mapping.get("absence_kind") if mapping else "other"
                absence_kind = str(kind)
                if mapping and mapping.get("consumes_vacation"):
                    vac += 1.0
                if kind == "sick":
                    sick += 1.0
                if mapping and mapping.get("counts_as_work_day"):
                    contract_min += expected
        covered = min(contract_min, expected)
        delta = covered + max(0, contract_min - expected) - expected
        if on_date >= ledger_start:
            overtime_at_end += delta
            vacation_at_end -= vac
        if from_date <= on_date <= to_date:
            plan_rows = list(roster_plan.get(on_date, []) if roster_plan is not None else [])
            if emp is not None:
                for plan in plan_rows:
                    rule = category_rule_for(group, plan.category)
                    plan.counts_toward_contract = bool(rule.get("counts_toward_contract", True))
                    if rule.get("credit_mode") == "none":
                        plan.duration_minutes = 0
            plan_minutes = sum(row.duration_minutes for row in plan_rows)
            days.append(
                TimesheetDayRead(
                    date=on_date,
                    expected_minutes=expected,
                    worked_contract_minutes=contract_min,
                    worked_extra_minutes=extra_min,
                    absence_kind=absence_kind,
                    vacation_days=vac,
                    sick_days=sick,
                    roster_plan_minutes=plan_minutes,
                    delta_minutes=delta,
                    entries=[time_entry_to_read(item) for item in range_entries_by_day.get(on_date, [])],
                    roster_plan=plan_rows,
                )
            )
            expected_total += expected
            contract_total += contract_min
            extra_total += extra_min
            vacation_days += vac
            sick_days += sick
            if emp is not None:
                active_name = group.name if group is not None else None
                active_pct = emp.employment_percentage

    return TimesheetRead(
        team_member_id=member.id,
        name=team_member_planning_display_name(member),
        from_date=from_date,
        to_date=to_date,
        worker_group_name=active_name,
        employment_percentage=active_pct,
        expected_minutes=expected_total,
        worked_contract_minutes=contract_total,
        worked_extra_minutes=extra_total,
        overtime_minutes=overtime_at_end,
        vacation_days=vacation_days,
        sick_days=sick_days,
        vacation_days_remaining=round(vacation_at_end, 2),
        days=days,
    )


def timesheet_to_summary(sheet: TimesheetRead) -> TimesheetSummaryRead:
    return TimesheetSummaryRead(
        team_member_id=sheet.team_member_id,
        name=sheet.name,
        worker_group_name=sheet.worker_group_name,
        employment_percentage=sheet.employment_percentage,
        expected_minutes=sheet.expected_minutes,
        worked_contract_minutes=sheet.worked_contract_minutes,
        worked_extra_minutes=sheet.worked_extra_minutes,
        overtime_minutes=sheet.overtime_minutes,
        vacation_days=sheet.vacation_days,
        sick_days=sheet.sick_days,
        vacation_days_remaining=sheet.vacation_days_remaining,
        roster_plan_minutes=sum(day.roster_plan_minutes for day in sheet.days),
    )


def get_timesheet(
    db: Session, *, team_member_id: int, organization_id: int, from_date: date, to_date: date
) -> TimesheetRead:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    roster = _load_roster_plan(
        db,
        organization_id=organization_id,
        team_member_ids=[team_member_id],
        from_date=from_date,
        to_date=to_date,
    )
    by_day = {key[1]: value for key, value in roster.items() if key[0] == team_member_id}
    opening = db.scalar(
        select(TimeAccountOpening).where(
            TimeAccountOpening.team_member_id == team_member_id,
            TimeAccountOpening.organization_id == organization_id,
        )
    )
    return compute_member_timesheet(
        db,
        member=member,
        organization_id=organization_id,
        from_date=from_date,
        to_date=to_date,
        opening=opening,
        roster_plan=by_day,
    )


def list_timesheet_summaries(
    db: Session,
    *,
    organization_id: int,
    members: list[TeamMember],
    from_date: date,
    to_date: date,
) -> list[TimesheetSummaryRead]:
    ids = [member.id for member in members]
    groups = _groups_by_id(db, organization_id)
    periods_map = _periods_map(db, organization_id=organization_id, team_member_ids=ids)
    openings = _opening_map(db, organization_id=organization_id, team_member_ids=ids)
    entries = list_time_entries_for_members(
        db, organization_id=organization_id, team_member_ids=ids, from_date=from_date, to_date=to_date
    )
    entries_by_member: dict[int, list[TimeEntry]] = {member_id: [] for member_id in ids}
    for entry in entries:
        entries_by_member.setdefault(entry.team_member_id, []).append(entry)
    roster = _load_roster_plan(
        db, organization_id=organization_id, team_member_ids=ids, from_date=from_date, to_date=to_date
    )
    rows: list[TimesheetSummaryRead] = []
    for member in members:
        by_day = {key[1]: value for key, value in roster.items() if key[0] == member.id}
        sheet = compute_member_timesheet(
            db,
            member=member,
            organization_id=organization_id,
            from_date=from_date,
            to_date=to_date,
            periods=periods_map.get(member.id, []),
            entries=entries_by_member.get(member.id, []),
            opening=openings.get(member.id),
            roster_plan=by_day,
            groups=groups,
        )
        rows.append(timesheet_to_summary(sheet))
    rows.sort(key=lambda row: row.name.lower())
    return rows


def export_timesheet_csv(sheet: TimesheetRead) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "date",
            "expected_minutes",
            "worked_contract_minutes",
            "worked_extra_minutes",
            "roster_plan_minutes",
            "delta_minutes",
            "absence_kind",
            "vacation_days",
            "sick_days",
        ]
    )
    for day in sheet.days:
        writer.writerow(
            [
                day.date.isoformat(),
                day.expected_minutes,
                day.worked_contract_minutes,
                day.worked_extra_minutes,
                day.roster_plan_minutes,
                day.delta_minutes,
                day.absence_kind or "",
                day.vacation_days,
                day.sick_days,
            ]
        )
    return buffer.getvalue()


def fill_from_roster(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    from_date: date,
    to_date: date,
    actor: str,
    source: str,
) -> int:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    existing = list_time_entries(
        db, team_member_id=team_member_id, organization_id=organization_id, from_date=from_date, to_date=to_date
    )
    manual_dates = {row.entry_date for row in existing if row.source == "manual"}
    existing_slot_ids = {row.roster_slot_id for row in existing if row.roster_slot_id is not None}
    roster = _load_roster_plan(
        db,
        organization_id=organization_id,
        team_member_ids=[team_member_id],
        from_date=from_date,
        to_date=to_date,
    )
    periods = list_employment_periods(db, team_member_id=team_member_id, organization_id=organization_id)
    created = 0
    for (member_id, slot_date), plans in roster.items():
        if member_id != team_member_id or slot_date in manual_dates:
            continue
        emp = employment_on_date(periods, slot_date)
        group = get_worker_group_or_none(db, emp.worker_group_id, organization_id=organization_id) if emp else None
        for plan in plans:
            if plan.roster_slot_id in existing_slot_ids:
                continue
            rule = category_rule_for(group, plan.category)
            duration = 0 if rule.get("credit_mode") == "none" else plan.duration_minutes
            create_time_entry(
                db,
                TimeEntryCreate(
                    entry_date=slot_date,
                    kind="work",
                    source="roster_fill",
                    all_day=False,
                    started_at=plan.started_at,
                    ended_at=plan.ended_at,
                    duration_minutes=duration,
                    counts_toward_contract=bool(rule.get("counts_toward_contract", True)),
                    shift_template_category=plan.category if plan.category in {"bereitschaftsdienst", "rufdienst", "spaetdienst", "other"} else None,
                    roster_slot_id=plan.roster_slot_id,
                ),
                team_member_id=team_member_id,
                organization_id=organization_id,
                actor=actor,
                source=source,
            )
            created += 1
            existing_slot_ids.add(plan.roster_slot_id)
    return created


def fill_regular_week(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    from_date: date,
    to_date: date,
    actor: str,
    source: str,
) -> int:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    existing = list_time_entries(
        db, team_member_id=team_member_id, organization_id=organization_id, from_date=from_date, to_date=to_date
    )
    occupied = {row.entry_date for row in existing}
    periods = list_employment_periods(db, team_member_id=team_member_id, organization_id=organization_id)
    created = 0
    for on_date in iter_dates(from_date, to_date):
        if on_date in occupied:
            continue
        emp = employment_on_date(periods, on_date)
        if emp is None:
            continue
        group = get_worker_group_or_none(db, emp.worker_group_id, organization_id=organization_id)
        if group is None:
            continue
        weekday = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[on_date.weekday()]
        match = next((item for item in (group.regular_week_pattern or []) if item.get("weekday") == weekday), None)
        if match is None:
            if on_date.weekday() >= 5:
                continue
            weekly = float(group.weekly_hours_at_100) * 60 * emp.employment_percentage / 100
            duration = round(weekly / 5)
            started = datetime.combine(on_date, datetime.strptime("08:00", "%H:%M").time())
            ended = started + timedelta(minutes=duration)
        else:
            duration = round(pattern_minutes(match["starts_at"], match["ends_at"]) * emp.employment_percentage / 100)
            start_t = datetime.strptime(match["starts_at"][:5], "%H:%M").time()
            started = datetime.combine(on_date, start_t)
            ended = started + timedelta(minutes=duration)
        if duration <= 0:
            continue
        create_time_entry(
            db,
            TimeEntryCreate(
                entry_date=on_date,
                kind="work",
                source="regular_hours",
                started_at=started,
                ended_at=ended,
                duration_minutes=duration,
                counts_toward_contract=True,
            ),
            team_member_id=team_member_id,
            organization_id=organization_id,
            actor=actor,
            source=source,
        )
        created += 1
        occupied.add(on_date)
    return created
