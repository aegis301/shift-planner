from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import TypeAdapter

from app.models import EmploymentPeriod, RosterSlot, RosterSlotAssignment
from app.schemas.domain import (
    ValidationWarning,
    WorkTimeRule,
    WorkTimeRuleDocumentationRequirement,
    WorkTimeRuleDutyUtilizationBands,
    WorkTimeRuleMaxConsecutiveWorkDays,
    WorkTimeRuleMaxDailyWorkingTime,
    WorkTimeRuleMaxDutiesPerPeriod,
    WorkTimeRuleMinRestPeriod,
    WorkTimeRuleOptOutWeeklyCap,
    WorkTimeRuleRestAfterLongDuty,
    WorkTimeRuleWeeklyAverageCap,
)
from app.services.rules.state import PlanState
from app.services.work_time_consents import applicable_weekly_cap
from app.services.work_time_rule_sets import get_active_work_time_rule_set
from app.services.work_time_valuation import statutory_work_minutes

_RULES_ADAPTER = TypeAdapter(list[WorkTimeRule])


def _hours_to_minutes(hours: Decimal) -> int:
    return int((hours * Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _subtract_months(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _reference_lookback(months: int) -> timedelta:
    return timedelta(days=max(1, months) * 31)


def _in_window(day: date, state: PlanState) -> bool:
    return state.start_date <= day <= state.end_date


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _slot_interval(slot: RosterSlot) -> tuple[datetime, datetime] | None:
    start = _as_utc(slot.starts_at)
    end = _as_utc(slot.ends_at)
    if start is None or end is None:
        return None
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def _employment_on(state: PlanState, member_id: int, on_date: date) -> EmploymentPeriod | None:
    periods = state.employment_periods_by_member_id.get(member_id, ())
    for period in periods:
        if period.start_date > on_date:
            continue
        if period.end_date is not None and period.end_date < on_date:
            continue
        return period
    return None


def _assignment_statutory_minutes(state: PlanState, assignment: RosterSlotAssignment) -> int:
    slot = assignment.roster_slot
    if slot is None:
        return 0
    for entry in state.time_entries_by_member_id.get(assignment.team_member_id, ()):
        if getattr(entry, "roster_slot_id", None) == slot.id:
            return int(entry.statutory_minutes or 0)
    employment = _employment_on(state, assignment.team_member_id, slot.slot_date)
    contract_group = employment.contract_group if employment is not None else None
    template = slot.shift_template
    return statutory_work_minutes(  # statutory_minutes / statutory_work_minutes only; never credited_minutes / tariff_credit_minutes.
        slot=slot,
        contract_group=contract_group,
        template=template,
        day_class=slot.day_class or "any",
        episodes=(),
    )


def _daily_statutory_minutes(state: PlanState, member_id: int, day: date) -> int:
    stored = state.statutory_minutes_by_member_date.get((member_id, day))
    if stored is not None:
        return stored
    from_entries = 0
    for entry in state.time_entries_by_member_id.get(member_id, ()):
        if getattr(entry, "entry_date", None) != day:
            continue
        from_entries += int(getattr(entry, "statutory_minutes", 0) or 0)
    if from_entries:
        return from_entries
    total = 0
    for assignment in state.assignments_by_member_id.get(member_id, ()):
        slot = assignment.roster_slot
        if slot is None or slot.slot_date != day:
            continue
        total += _assignment_statutory_minutes(state, assignment)
    return total


def _duty_minutes_on_day(state: PlanState, member_id: int, day: date) -> int:
    total = 0
    for assignment in state.assignments_by_member_id.get(member_id, ()):
        slot = assignment.roster_slot
        if slot is None:
            continue
        interval = _slot_interval(slot)
        if interval is None:
            if slot.slot_date == day:
                total += 24 * 60
            continue
        start, end = interval
        cursor = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        next_day = cursor + timedelta(days=1)
        overlap_start = max(start, cursor)
        overlap_end = min(end, next_day)
        if overlap_end > overlap_start:
            total += int((overlap_end - overlap_start).total_seconds() // 60)
    return total


def _warning(
    *,
    code: str,
    severity: str,
    message: str,
    team_member_id: int,
    on_date: date,
    details: dict[str, Any],
) -> ValidationWarning:
    return ValidationWarning(
        code=code,
        severity=severity,
        message=message,
        team_member_id=team_member_id,
        date=on_date,
        details=details,
    )


class MaxDailyWorkingTimeRule:
    def __init__(self, config: WorkTimeRuleMaxDailyWorkingTime) -> None:
        self.config = config
        self.code = "WORKTIME_MAX_DAILY"
        self.severity = config.severity
        self.lookback = timedelta(days=1)
        self.roster_lookback = timedelta(days=1)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        base = _hours_to_minutes(self.config.base_hours)
        extended = _hours_to_minutes(self.config.extended_hours)
        duty_needed = _hours_to_minutes(self.config.extension_requires_duty_hours)
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            day = state.start_date
            while day <= state.end_date:
                statutory = _daily_statutory_minutes(state, member_id, day)
                duty = _duty_minutes_on_day(state, member_id, day)
                limit = extended if duty >= duty_needed else base
                if statutory > limit:
                    slot_ids = [
                        assignment.roster_slot_id
                        for assignment in state.assignments_by_member_id.get(member_id, ())
                        if assignment.roster_slot is not None and assignment.roster_slot.slot_date == day
                    ]
                    warnings.append(
                        _warning(
                            code=self.code,
                            severity=self.severity,
                            message="Statutory working time exceeds the daily limit.",
                            team_member_id=member_id,
                            on_date=day,
                            details={
                                "statutory_minutes": statutory,
                                "limit_minutes": limit,
                                "duty_minutes": duty,
                                "roster_slot_id": slot_ids[0] if slot_ids else None,
                                "roster_slot_ids": slot_ids,
                            },
                        )
                    )
                day += timedelta(days=1)
        return warnings


def _occupancy_intervals(state: PlanState, member_id: int, *, call_out_handling: str) -> list[tuple[datetime, datetime, int | None]]:
    intervals: list[tuple[datetime, datetime, int | None]] = []
    ruf_slot_ids: set[int] = set()
    for assignment in state.assignments_by_member_id.get(member_id, ()):
        slot = assignment.roster_slot
        if slot is None:
            continue
        interval = _slot_interval(slot)
        if interval is None:
            continue
        template = slot.shift_template
        if template is not None and template.category == "rufdienst":
            ruf_slot_ids.add(slot.id)
            continue
        intervals.append((interval[0], interval[1], slot.id))
    if call_out_handling != "ignore":
        for entry in state.time_entries_by_member_id.get(member_id, ()):
            if getattr(entry, "kind", None) != "call_out":
                continue
            slot_id = getattr(entry, "roster_slot_id", None)
            if slot_id not in ruf_slot_ids:
                continue
            start = _as_utc(getattr(entry, "started_at", None))
            end = _as_utc(getattr(entry, "ended_at", None))
            if start is None or end is None or end <= start:
                continue
            intervals.append((start, end, slot_id))
    intervals.sort(key=lambda item: (item[0], item[1]))
    merged: list[tuple[datetime, datetime, int | None]] = []
    for start, end, slot_id in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end, slot_id))
            continue
        prev_start, prev_end, prev_slot = merged[-1]
        merged[-1] = (prev_start, max(prev_end, end), prev_slot if prev_end >= end else slot_id)
    return merged


class MinRestPeriodRule:
    def __init__(self, config: WorkTimeRuleMinRestPeriod) -> None:
        self.config = config
        self.code = "WORKTIME_MIN_REST"
        self.severity = config.severity
        extra_days = max(2, int(config.compensation_window_days))
        self.lookback = timedelta(days=extra_days)
        self.roster_lookback = timedelta(days=extra_days)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        required = timedelta(minutes=_hours_to_minutes(self.config.hours))
        reducible = None
        if self.config.reducible_to_hours is not None:
            reducible = timedelta(minutes=_hours_to_minutes(self.config.reducible_to_hours))
        window = timedelta(days=self.config.compensation_window_days)
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            intervals = _occupancy_intervals(
                state, member_id, call_out_handling=self.config.call_out_handling
            )
            for index in range(len(intervals) - 1):
                _start, prev_end, prev_slot = intervals[index]
                next_start, _next_end, next_slot = intervals[index + 1]
                gap = next_start - prev_end
                next_day = next_start.date()
                if gap >= required:
                    continue
                details = {
                    "rest_minutes": int(gap.total_seconds() // 60),
                    "required_minutes": int(required.total_seconds() // 60),
                    "roster_slot_id": next_slot,
                    "related_roster_slot_id": prev_slot,
                }
                if reducible is not None and gap >= reducible:
                    deficit = required - gap
                    compensated = timedelta(0)
                    for later_index in range(index + 1, len(intervals) - 1):
                        gap_start = intervals[later_index][1]
                        gap_end = intervals[later_index + 1][0]
                        if gap_start > next_start + window:
                            break
                        later_gap = gap_end - gap_start
                        if later_gap > required:
                            compensated += later_gap - required
                    if compensated >= deficit:
                        continue
                    window_end_date = (next_start + window).date()
                    if window_end_date > state.end_date:
                        if _in_window(next_day, state) or _in_window(prev_end.date(), state):
                            warnings.append(
                                _warning(
                                    code="WORKTIME_REST_COMPENSATION_PENDING",
                                    severity=self.severity,
                                    message="Reduced rest is not yet compensated inside the configured window.",
                                    team_member_id=member_id,
                                    on_date=next_day,
                                    details=details,
                                )
                            )
                        continue
                if not (_in_window(next_day, state) or _in_window(prev_end.date(), state)):
                    continue
                warnings.append(
                    _warning(
                        code=self.code,
                        severity=self.severity,
                        message="Minimum rest period between duties is not met.",
                        team_member_id=member_id,
                        on_date=next_day,
                        details=details,
                    )
                )
        return warnings


class RestAfterLongDutyRule:
    def __init__(self, config: WorkTimeRuleRestAfterLongDuty) -> None:
        self.config = config
        self.code = "WORKTIME_REST_AFTER_LONG_DUTY"
        self.severity = config.severity
        self.lookback = timedelta(days=2)
        self.roster_lookback = timedelta(days=2)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        trigger = timedelta(minutes=_hours_to_minutes(self.config.trigger_hours))
        rest = timedelta(minutes=_hours_to_minutes(self.config.mandatory_rest_hours))
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            assignments = sorted(
                [row for row in state.assignments_by_member_id.get(member_id, ()) if row.roster_slot is not None],
                key=lambda row: _slot_interval(row.roster_slot) or (
                    datetime.combine(row.roster_slot.slot_date, datetime.min.time(), tzinfo=UTC),
                    datetime.combine(row.roster_slot.slot_date, datetime.min.time(), tzinfo=UTC),
                ),
            )
            for index, assignment in enumerate(assignments):
                interval = _slot_interval(assignment.roster_slot)
                if interval is None:
                    continue
                start, end = interval
                if end - start < trigger:
                    continue
                if index + 1 >= len(assignments):
                    continue
                nxt = assignments[index + 1]
                next_interval = _slot_interval(nxt.roster_slot)
                if next_interval is None:
                    continue
                next_start = next_interval[0]
                if next_start - end >= rest:
                    continue
                if not (_in_window(next_start.date(), state) or _in_window(end.date(), state)):
                    continue
                warnings.append(
                    _warning(
                        code=self.code,
                        severity=self.severity,
                        message="Mandatory rest after a long duty is not met.",
                        team_member_id=member_id,
                        on_date=next_start.date(),
                        details={
                            "roster_slot_id": nxt.roster_slot_id,
                            "related_roster_slot_id": assignment.roster_slot_id,
                            "duty_minutes": int((end - start).total_seconds() // 60),
                            "rest_minutes": int((next_start - end).total_seconds() // 60),
                        },
                    )
                )
        return warnings


def _weekly_average_minutes(state: PlanState, member_id: int, start: date, end: date) -> tuple[int, int, int]:
    total = 0
    day = start
    while day <= end:
        total += _daily_statutory_minutes(state, member_id, day)
        day += timedelta(days=1)
    days = (end - start).days + 1
    if days <= 0:
        return 0, 0, 0
    average = int((Decimal(total) * Decimal(7) / Decimal(days)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return total, days, average


class WeeklyAverageCapRule:
    def __init__(self, config: WorkTimeRuleWeeklyAverageCap) -> None:
        self.config = config
        self.code = "WORKTIME_WEEKLY_AVERAGE"
        self.severity = config.severity
        self.lookback = _reference_lookback(config.reference_period_months)
        self.roster_lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        cap = _hours_to_minutes(self.config.hours)
        period_start = _subtract_months(state.end_date, self.config.reference_period_months)
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            total, days, average = _weekly_average_minutes(state, member_id, period_start, state.end_date)
            if average <= cap:
                continue
            slot_ids = [
                assignment.roster_slot_id
                for assignment in state.assignments_by_member_id.get(member_id, ())
                if assignment.roster_slot is not None and _in_window(assignment.roster_slot.slot_date, state)
            ]
            warnings.append(
                _warning(
                    code=self.code,
                    severity=self.severity,
                    message="Rolling weekly average of statutory working time exceeds the cap.",
                    team_member_id=member_id,
                    on_date=state.end_date,
                    details={
                        "statutory_minutes": total,
                        "days": days,
                        "average_weekly_minutes": average,
                        "cap_minutes": cap,
                        "roster_slot_id": slot_ids[-1] if slot_ids else None,
                        "roster_slot_ids": slot_ids,
                    },
                )
            )
        return warnings


class OptOutWeeklyCapRule:
    def __init__(self, config: WorkTimeRuleOptOutWeeklyCap) -> None:
        self.config = config
        self.code = "WORKTIME_WEEKLY_AVERAGE_OPT_OUT"
        self.severity = config.severity
        self.lookback = _reference_lookback(config.reference_period_months)
        self.roster_lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        period_months = self.config.reference_period_months
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            consents = state.work_time_consents_by_member_id.get(member_id, ())
            day = state.start_date
            while day <= state.end_date:
                cap = _hours_to_minutes(applicable_weekly_cap(member_id, day, self.config, consents))
                period_start = _subtract_months(day, period_months)
                total, days, average = _weekly_average_minutes(state, member_id, period_start, day)
                if average > cap:
                    slot_ids = [
                        assignment.roster_slot_id
                        for assignment in state.assignments_by_member_id.get(member_id, ())
                        if assignment.roster_slot is not None and assignment.roster_slot.slot_date == day
                    ]
                    warnings.append(
                        _warning(
                            code=self.code,
                            severity=self.severity,
                            message="Rolling weekly average exceeds the applicable opt-out or base cap.",
                            team_member_id=member_id,
                            on_date=day,
                            details={
                                "statutory_minutes": total,
                                "days": days,
                                "average_weekly_minutes": average,
                                "cap_minutes": cap,
                                "roster_slot_id": slot_ids[-1] if slot_ids else None,
                                "roster_slot_ids": slot_ids,
                            },
                        )
                    )
                day += timedelta(days=1)
        return warnings


class MaxConsecutiveWorkDaysRule:
    def __init__(self, config: WorkTimeRuleMaxConsecutiveWorkDays) -> None:
        self.config = config
        self.code = "WORKTIME_CONSECUTIVE_DAYS"
        self.severity = config.severity
        self.lookback = timedelta(days=config.days + 1)
        self.roster_lookback = timedelta(days=config.days + 1)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        warnings: list[ValidationWarning] = []
        limit = self.config.days
        scan_start = state.start_date - timedelta(days=limit)
        for member_id in state.members_by_id:
            run = 0
            day = scan_start
            while day <= state.end_date:
                worked = _daily_statutory_minutes(state, member_id, day) > 0
                run = run + 1 if worked else 0
                if run > limit and _in_window(day, state):
                    warnings.append(
                        _warning(
                            code=self.code,
                            severity=self.severity,
                            message="Consecutive work days exceed the configured maximum.",
                            team_member_id=member_id,
                            on_date=day,
                            details={"consecutive_days": run, "limit_days": limit},
                        )
                    )
                day += timedelta(days=1)
        return warnings


def _period_start(day: date, period: str) -> date:
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return date(day.year, day.month, 1)
    if period == "quarter":
        month = ((day.month - 1) // 3) * 3 + 1
        return date(day.year, month, 1)
    return date(day.year, 1, 1)


class MaxDutiesPerPeriodRule:
    def __init__(self, config: WorkTimeRuleMaxDutiesPerPeriod) -> None:
        self.config = config
        self.code = "WORKTIME_MAX_DUTIES"
        self.severity = config.severity
        if config.period == "year":
            days = 366
        elif config.period == "quarter":
            days = 92
        elif config.period == "month":
            days = 31
        else:
            days = 7
        self.lookback = timedelta(days=days)
        self.roster_lookback = timedelta(days=days)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        allowed = self.config.count
        if self.config.period == "month":
            allowed += self.config.additional_allowance_per_quarter
        warnings: list[ValidationWarning] = []
        counted: dict[tuple[int, date], list[int]] = defaultdict(list)
        for assignment in state.assignments_by_id.values():
            slot = assignment.roster_slot
            if slot is None:
                continue
            period_start = _period_start(slot.slot_date, self.config.period)
            counted[(assignment.team_member_id, period_start)].append(slot.id)
        seen: set[tuple[int, date]] = set()
        for assignment in state.assignments_by_id.values():
            slot = assignment.roster_slot
            if slot is None or not _in_window(slot.slot_date, state):
                continue
            key = (assignment.team_member_id, _period_start(slot.slot_date, self.config.period))
            if key in seen:
                continue
            slot_ids = counted.get(key, [])
            if len(slot_ids) <= allowed:
                continue
            seen.add(key)
            warnings.append(
                _warning(
                    code=self.code,
                    severity=self.severity,
                    message="Duty count exceeds the configured period limit.",
                    team_member_id=assignment.team_member_id,
                    on_date=slot.slot_date,
                    details={
                        "count": len(slot_ids),
                        "allowed": allowed,
                        "period": self.config.period,
                        "roster_slot_id": slot.id,
                        "roster_slot_ids": slot_ids,
                    },
                )
            )
        return warnings


class DocumentationRequirementRule:
    def __init__(self, config: WorkTimeRuleDocumentationRequirement) -> None:
        self.config = config
        self.code = "WORKTIME_DOCUMENTATION_GAP"
        self.severity = config.severity
        self.lookback = timedelta(0)
        self.roster_lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        threshold = _hours_to_minutes(self.config.threshold_hours)
        warnings: list[ValidationWarning] = []
        for member_id in state.members_by_id:
            day = state.start_date
            while day <= state.end_date:
                statutory = _daily_statutory_minutes(state, member_id, day)
                if statutory <= threshold:
                    day += timedelta(days=1)
                    continue
                documented = any(
                    getattr(entry, "entry_date", None) == day
                    for entry in state.time_entries_by_member_id.get(member_id, ())
                )
                if documented:
                    day += timedelta(days=1)
                    continue
                slot_ids = [
                    assignment.roster_slot_id
                    for assignment in state.assignments_by_member_id.get(member_id, ())
                    if assignment.roster_slot is not None and assignment.roster_slot.slot_date == day
                ]
                warnings.append(
                    _warning(
                        code=self.code,
                        severity=self.severity,
                        message="Working time above the documentation threshold has no time-entry record.",
                        team_member_id=member_id,
                        on_date=day,
                        details={
                            "statutory_minutes": statutory,
                            "threshold_minutes": threshold,
                            "roster_slot_id": slot_ids[0] if slot_ids else None,
                            "roster_slot_ids": slot_ids,
                        },
                    )
                )
                day += timedelta(days=1)
        return warnings


def _rule_from_config(config: WorkTimeRule) -> Any | None:
    if isinstance(config, WorkTimeRuleDutyUtilizationBands):
        return None
    if isinstance(config, WorkTimeRuleMaxDailyWorkingTime):
        return MaxDailyWorkingTimeRule(config)
    if isinstance(config, WorkTimeRuleMinRestPeriod):
        return MinRestPeriodRule(config)
    if isinstance(config, WorkTimeRuleRestAfterLongDuty):
        return RestAfterLongDutyRule(config)
    if isinstance(config, WorkTimeRuleWeeklyAverageCap):
        return WeeklyAverageCapRule(config)
    if isinstance(config, WorkTimeRuleOptOutWeeklyCap):
        return OptOutWeeklyCapRule(config)
    if isinstance(config, WorkTimeRuleMaxConsecutiveWorkDays):
        return MaxConsecutiveWorkDaysRule(config)
    if isinstance(config, WorkTimeRuleMaxDutiesPerPeriod):
        return MaxDutiesPerPeriodRule(config)
    if isinstance(config, WorkTimeRuleDocumentationRequirement):
        return DocumentationRequirementRule(config)
    return None


def statutory_rules_for_org(db: Any, organization_id: int) -> tuple[Any, ...]:
    row = get_active_work_time_rule_set(db, organization_id=organization_id)
    if row is None:
        return ()
    return tuple(
        rule
        for config in _RULES_ADAPTER.validate_python(row.rules or [])
        if (rule := _rule_from_config(config)) is not None
    )
