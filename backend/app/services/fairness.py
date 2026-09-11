from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EmploymentPeriod,
    Organization,
    TeamMember,
    TimeAccountOpening,
)
from app.schemas import (
    FairnessAccountsRead,
    FairnessDayFilter,
    FairnessDimension,
    FairnessDimensionValue,
    FairnessMemberAccount,
    FairnessPolicy,
    FairnessPolicyUpdate,
    FairnessWindow,
)
from app.services.audit import record_audit
from app.services.contract_group_defaults import DEFAULT_WEEKLY_HOURS_AT_100
from app.services.holidays import classify_day
from app.services.rules import build_plan_state
from app.services.rules.state import EMPTY_DUTY_COUNTS, DutyDayCounts, PlanState
from app.services.shift_groups import _stint_active_on, require_shift_group
from app.services.team_members import team_member_planning_display_name
from app.services.tenancy import require_planning_period_in_org

STATUTORY_HOURS_DIMENSION_ID = "statutory_hours"


def default_fairness_policy() -> FairnessPolicy:
    return FairnessPolicy(
        window_months=12,
        dimensions=[
            FairnessDimension(id="duties", metric="duty_count", day_filter="any", night=False),
            FairnessDimension(
                id="weekend_holiday",
                metric="duty_count",
                day_filter="weekend_holiday",
                night=False,
            ),
            FairnessDimension(id="night", metric="duty_count", day_filter="any", night=True),
            FairnessDimension(
                id="statutory_hours",
                metric="statutory_minutes",
                day_filter="any",
                night=False,
            ),
        ],
    )


def read_fairness_policy(organization: Organization) -> FairnessPolicy:
    raw = organization.fairness_policy or {}
    parsed = FairnessPolicy.model_validate(raw)
    if not parsed.dimensions:
        return default_fairness_policy().model_copy(update={"window_months": parsed.window_months})
    return parsed


def update_fairness_policy(
    db: Session,
    organization: Organization,
    payload: FairnessPolicyUpdate,
    *,
    actor: str,
    source: str,
) -> FairnessPolicy:
    current = read_fairness_policy(organization)
    data = current.model_dump()
    data.update(payload.model_dump(exclude_unset=True))
    normalized = FairnessPolicy.model_validate(data)
    if not normalized.dimensions:
        raise ValueError("At least one fairness dimension is required")
    organization.fairness_policy = normalized.model_dump()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="fairness_policy",
        entity_id=organization.id,
        details={"window_months": normalized.window_months, "dimension_ids": [row.id for row in normalized.dimensions]},
    )
    db.commit()
    db.refresh(organization)
    return read_fairness_policy(organization)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _iter_months(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        year, month = _shift_month(year, month, 1)
    return months


def _iter_days(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _employment_on(periods: tuple[object, ...], on_date: date) -> EmploymentPeriod | None:
    for period in periods:
        if isinstance(period, EmploymentPeriod) and _stint_active_on(period, on_date):
            return period
    return None


def _weight_on(periods: tuple[object, ...], on_date: date) -> Decimal:
    period = _employment_on(periods, on_date)
    if period is None:
        return Decimal(DEFAULT_WEEKLY_HOURS_AT_100)
    hours = (
        period.contract_group.weekly_hours_at_100
        if period.contract_group is not None
        else Decimal(DEFAULT_WEEKLY_HOURS_AT_100)
    )
    return (Decimal(period.employment_percentage) / Decimal(100)) * Decimal(hours)


def _pool_for_month(
    state: PlanState,
    *,
    year: int,
    month: int,
    shift_group_id: int | None,
) -> set[int]:
    if shift_group_id is not None:
        return set(state.period_roster_member_ids.get((year, month, shift_group_id), frozenset()))
    members: set[int] = set()
    for (row_year, row_month, _group_id), ids in state.period_roster_member_ids.items():
        if row_year == year and row_month == month:
            members.update(ids)
    return members


def _day_matches_filter(day: date, day_filter: FairnessDayFilter, night: bool, is_night: bool) -> bool:
    if night and not is_night:
        return False
    return not (day_filter == "weekend_holiday" and classify_day(day) not in ("weekend", "holiday"))


def _duty_value(counts: DutyDayCounts, dimension: FairnessDimension) -> float:
    category = dimension.category
    if dimension.night:
        if category:
            return float(counts.night_by_category.get(category, 0))
        return float(counts.night)
    if dimension.day_filter == "weekend_holiday":
        if category:
            return float(counts.weekend_holiday_by_category.get(category, 0))
        return float(counts.weekend_holiday)
    if category:
        return float(counts.by_category.get(category, 0))
    return float(counts.total)


def _dimension_actual_for_month(
    state: PlanState,
    *,
    member_id: int,
    year: int,
    month: int,
    dimension: FairnessDimension,
) -> float:
    start = _month_start(year, month)
    end = _month_end(year, month)
    total = 0.0
    if dimension.metric == "statutory_minutes":
        for day in _iter_days(start, end):
            if not _day_matches_filter(day, dimension.day_filter, dimension.night, False):
                continue
            stored = state.statutory_minutes_by_member_date.get((member_id, day))
            if stored is not None:
                total += float(stored)
                continue
            for entry in state.time_entries_by_member_id.get(member_id, ()):
                if getattr(entry, "entry_date", None) == day:
                    total += float(getattr(entry, "statutory_minutes", 0) or 0)
        return total
    for day in _iter_days(start, end):
        counts = state.duty_counts_by_member_date.get((member_id, day), EMPTY_DUTY_COUNTS)
        total += _duty_value(counts, dimension)
    return total


def _opening_for_dimension(
    opening: TimeAccountOpening | None,
    dimension: FairnessDimension,
    *,
    window_end: date,
) -> float:
    if opening is None or opening.as_of_date > window_end:
        return 0.0
    balances = opening.fairness_balances or {}
    if dimension.id in balances:
        return float(balances[dimension.id])
    if dimension.id == STATUTORY_HOURS_DIMENSION_ID and dimension.metric == "statutory_minutes":
        return float(opening.overtime_minutes)
    return 0.0


def _normalized_deviation(actual: float, expected: float) -> float:
    if expected > 0:
        return (actual - expected) / expected
    if actual > 0:
        return 1.0
    return 0.0


def _subject_member_ids(
    state: PlanState,
    *,
    year: int,
    month: int,
    shift_group_id: int | None,
) -> list[int]:
    pool = _pool_for_month(state, year=year, month=month, shift_group_id=shift_group_id)
    if pool:
        return sorted(member_id for member_id in pool if member_id in state.members_by_id)
    return sorted(state.members_by_id)


def build_fairness_accounts(
    db: Session,
    planning_period_id: int,
    *,
    organization_id: int,
    shift_group_id: int | None = None,
) -> FairnessAccountsRead:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
    org = db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    policy = read_fairness_policy(org)
    end_year, end_month = period.year, period.month
    start_year, start_month = _shift_month(end_year, end_month, 1 - policy.window_months)
    window_start = _month_start(start_year, start_month)
    window_end = _month_end(end_year, end_month)
    start_date = _month_start(end_year, end_month)
    end_date = window_end
    state = build_plan_state(
        db,
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
        shift_group_id=shift_group_id,
        history_start=window_start,
    )
    months = _iter_months(start_year, start_month, end_year, end_month)
    subject_ids = _subject_member_ids(
        state, year=end_year, month=end_month, shift_group_id=shift_group_id
    )
    openings: dict[int, TimeAccountOpening] = {}
    if subject_ids:
        openings = {
            row.team_member_id: row
            for row in db.scalars(
                select(TimeAccountOpening).where(TimeAccountOpening.team_member_id.in_(subject_ids))
            ).all()
        }
    member_rows: list[FairnessMemberAccount] = []
    for member_id in subject_ids:
        member = state.members_by_id.get(member_id)
        if member is None:
            loaded = db.get(TeamMember, member_id)
            display_name = team_member_planning_display_name(loaded) if loaded is not None else str(member_id)
        else:
            display_name = team_member_planning_display_name(member)
        opening = openings.get(member_id)
        values: list[FairnessDimensionValue] = []
        for dimension in policy.dimensions:
            actual = _opening_for_dimension(opening, dimension, window_end=window_end)
            expected = 0.0
            for year, month in months:
                pool = _pool_for_month(state, year=year, month=month, shift_group_id=shift_group_id)
                if member_id not in pool:
                    continue
                weights = {
                    other_id: _weight_on(
                        state.employment_periods_by_member_id.get(other_id, ()),
                        _month_start(year, month),
                    )
                    for other_id in pool
                }
                weight_sum = sum(weights.values(), Decimal("0"))
                month_actuals = {
                    other_id: _dimension_actual_for_month(
                        state,
                        member_id=other_id,
                        year=year,
                        month=month,
                        dimension=dimension,
                    )
                    for other_id in pool
                }
                month_total = sum(month_actuals.values())
                member_weight = weights.get(member_id, Decimal("0"))
                if weight_sum > 0:
                    expected += float(Decimal(str(month_total)) * member_weight / weight_sum)
                actual += month_actuals.get(member_id, 0.0)
            absolute = actual - expected
            values.append(
                FairnessDimensionValue(
                    dimension_id=dimension.id,
                    actual=actual,
                    expected=expected,
                    deviation_absolute=absolute,
                    deviation_normalized=_normalized_deviation(actual, expected),
                )
            )
        member_rows.append(
            FairnessMemberAccount(
                team_member_id=member_id,
                display_name=display_name,
                dimensions=values,
            )
        )
    member_rows.sort(
        key=lambda row: (
            -max((item.deviation_normalized for item in row.dimensions), default=0.0),
            -max((item.deviation_absolute for item in row.dimensions), default=0.0),
            row.display_name,
            row.team_member_id,
        )
    )
    return FairnessAccountsRead(
        planning_period_id=period.id,
        year=period.year,
        month=period.month,
        shift_group_id=shift_group_id,
        window=FairnessWindow(
            start_year=start_year,
            start_month=start_month,
            end_year=end_year,
            end_month=end_month,
            months=policy.window_months,
        ),
        dimensions=list(policy.dimensions),
        members=member_rows,
    )
