from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ContractGroup, TeamMember, TeamMemberShiftGroup, TimeEntry
from app.schemas import (
    HoursLedgerRead,
    HoursLedgerTotals,
    RegularWeekPatternDay,
    TimeAccountOpeningRead,
)
from app.services.contract_groups import list_contract_groups
from app.services.employment_periods import (
    employment_percentage_on,
    get_time_account_opening,
    time_account_opening_to_read,
)
from app.services.shift_groups import _stint_active_on
from app.services.time_entries import (
    KIND_ABSENCE,
    list_reconciliation,
    list_time_entries,
    time_entry_to_read,
)

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def member_in_shift_group(db: Session, *, team_member_id: int, shift_group_id: int, on_date: date | None = None) -> bool:
    check_date = on_date or date.today()
    stints = list(
        db.scalars(
            select(TeamMemberShiftGroup).where(
                TeamMemberShiftGroup.team_member_id == team_member_id,
                TeamMemberShiftGroup.shift_group_id == shift_group_id,
            )
        )
    )
    return any(_stint_active_on(stint, check_date) for stint in stints)


def pattern_minutes_for_date(pattern: list, on_date: date) -> int:
    code = _WEEKDAYS[on_date.weekday()]
    for raw in pattern or []:
        day = RegularWeekPatternDay.model_validate(raw)
        if day.weekday != code:
            continue
        start_at = datetime.combine(on_date, day.start)
        end_at = datetime.combine(on_date, day.end)
        if end_at <= start_at:
            end_at += timedelta(days=1)
        return max(0, int((end_at - start_at).total_seconds() // 60))
    return 0


def _contract_group_on(member: TeamMember, on_date: date, groups_by_id: dict[int, ContractGroup]) -> ContractGroup | None:
    for period in member.employment_periods:
        if _stint_active_on(period, on_date):
            return groups_by_id.get(period.contract_group_id)
    return None


def contract_target_minutes_for_window(
    member: TeamMember,
    *,
    start_date: date,
    end_date: date,
    groups_by_id: dict[int, ContractGroup],
) -> int:
    total = 0
    current = start_date
    while current <= end_date:
        group = _contract_group_on(member, current, groups_by_id)
        if group is not None:
            day_minutes = pattern_minutes_for_date(group.regular_week_pattern, current)
            pct = Decimal(employment_percentage_on(member, current)) / Decimal(100)
            total += int((Decimal(day_minutes) * pct).to_integral_value(rounding=ROUND_HALF_UP))
        current += timedelta(days=1)
    return total


def _vacation_days_consumed(entries: list[TimeEntry]) -> Decimal:
    total = Decimal("0")
    for row in entries:
        if row.kind == KIND_ABSENCE and row.consumes_vacation:
            total += Decimal("1")
    return total


def get_hours_ledger(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    start_date: date,
    end_date: date,
    include_reconciliation: bool = False,
) -> HoursLedgerRead:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    member = db.scalar(
        select(TeamMember)
        .options(joinedload(TeamMember.employment_periods))
        .where(TeamMember.id == team_member_id, TeamMember.organization_id == organization_id)
    )
    if member is None:
        raise ValueError("Team member not found")
    groups = {row.id: row for row in list_contract_groups(db, organization_id=organization_id)}
    entries = list_time_entries(
        db,
        organization_id=organization_id,
        team_member_id=team_member_id,
        start_date=start_date,
        end_date=end_date,
    )
    opening_row = get_time_account_opening(db, team_member_id, organization_id=organization_id)
    opening: TimeAccountOpeningRead | None = (
        time_account_opening_to_read(opening_row) if opening_row is not None else None
    )
    opening_overtime = opening.overtime_minutes if opening is not None else 0
    target = contract_target_minutes_for_window(
        member, start_date=start_date, end_date=end_date, groups_by_id=groups
    )
    statutory_total = sum(row.statutory_minutes for row in entries)
    credited_total = sum(row.credited_minutes for row in entries)
    credited_toward = sum(row.credited_minutes for row in entries if row.counts_toward_contract)
    absences = [row for row in entries if row.kind == KIND_ABSENCE]
    vacation_consumed = _vacation_days_consumed(entries)
    remaining = None
    if opening is not None:
        remaining = opening.vacation_days_remaining - vacation_consumed
    totals = HoursLedgerTotals(
        contract_target_minutes=target,
        statutory_minutes=statutory_total,
        credited_minutes=credited_total,
        credited_minutes_toward_contract=credited_toward,
        absence_count=len(absences),
        vacation_days_consumed=vacation_consumed,
        opening_overtime_minutes=opening_overtime,
        running_overtime_minutes=opening_overtime + credited_toward - target,
        vacation_days_remaining=remaining,
    )
    reconciliation = []
    if include_reconciliation:
        reconciliation = list_reconciliation(
            db,
            organization_id=organization_id,
            team_member_id=team_member_id,
            start_date=start_date,
            end_date=end_date,
        )
    return HoursLedgerRead(
        team_member_id=team_member_id,
        start_date=start_date,
        end_date=end_date,
        opening=opening,
        totals=totals,
        entries=[time_entry_to_read(row) for row in entries],
        reconciliation=reconciliation,
    )
