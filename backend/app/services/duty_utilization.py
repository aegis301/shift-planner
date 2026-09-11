from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import PlanningPeriod, RosterSlot, RosterSlotAssignment, ShiftGroupShiftTemplate
from app.schemas import (
    DutyUtilizationAggregateRead,
    DutyUtilizationBandCode,
    DutyUtilizationCoverage,
    DutyUtilizationPeriodRead,
    DutyUtilizationSlotRead,
    WorkTimeRule,
    WorkTimeRuleDutyUtilizationBands,
)
from app.services.duty_activity import interval_minutes, list_duty_activity_for_slots, slot_span
from app.services.work_time_rule_sets import get_active_work_time_rule_set

_RULES_ADAPTER = TypeAdapter(list[WorkTimeRule])


def _ratio(worked_minutes: int, duty_minutes: int) -> Decimal:
    if duty_minutes <= 0:
        return Decimal("0")
    return (Decimal(worked_minutes) / Decimal(duty_minutes)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _percent(ratio: Decimal) -> Decimal:
    return (ratio * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def utilization_bands_from_rules(rules: list[WorkTimeRule] | None) -> WorkTimeRuleDutyUtilizationBands | None:
    for rule in rules or []:
        if isinstance(rule, WorkTimeRuleDutyUtilizationBands):
            return rule
    return None


def resolve_utilization_bands(db: Session, *, organization_id: int) -> WorkTimeRuleDutyUtilizationBands | None:
    row = get_active_work_time_rule_set(db, organization_id=organization_id)
    if row is None:
        return None
    return utilization_bands_from_rules(_RULES_ADAPTER.validate_python(row.rules or []))


def classify_utilization(
    utilization_percent: Decimal, bands: WorkTimeRuleDutyUtilizationBands | None
) -> tuple[DutyUtilizationBandCode | None, bool]:
    if bands is None:
        return None, False
    if utilization_percent <= bands.stufe_i_max_percent:
        return "stufe_i", False
    if utilization_percent <= bands.on_call_max_percent:
        return "stufe_ii", False
    return "full_work", True


def _coverage(recorded_duty_count: int, duty_count: int) -> DutyUtilizationCoverage:
    coverage_ratio = Decimal("0")
    if duty_count > 0:
        coverage_ratio = (Decimal(recorded_duty_count) / Decimal(duty_count)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    return DutyUtilizationCoverage(
        recorded_duty_count=recorded_duty_count,
        duty_count=duty_count,
        coverage_ratio=coverage_ratio,
    )


def _aggregate(
    *,
    worked_minutes: int,
    duty_minutes: int,
    recorded_duty_count: int,
    duty_count: int,
    bands: WorkTimeRuleDutyUtilizationBands | None,
    shift_template_id: int | None = None,
) -> DutyUtilizationAggregateRead:
    ratio = _ratio(worked_minutes, duty_minutes)
    percent = _percent(ratio)
    band, exceeds = classify_utilization(percent, bands)
    return DutyUtilizationAggregateRead(
        shift_template_id=shift_template_id,
        worked_minutes=worked_minutes,
        duty_minutes=duty_minutes,
        utilization_ratio=ratio,
        utilization_percent=percent,
        band=band,
        exceeds_on_call_threshold=exceeds,
        coverage=_coverage(recorded_duty_count, duty_count),
    )


def slot_utilization(
    slot: RosterSlot,
    episodes: list,
    bands: WorkTimeRuleDutyUtilizationBands | None,
) -> DutyUtilizationSlotRead:
    try:
        start, end = slot_span(slot)
        duty_minutes = interval_minutes(start, end)
    except ValueError:
        duty_minutes = 0
    worked_minutes = 0
    for episode in episodes:
        worked_minutes += max(0, int(getattr(episode, "duration_minutes", 0) or 0))
    ratio = _ratio(worked_minutes, duty_minutes)
    percent = _percent(ratio)
    band, exceeds = classify_utilization(percent, bands)
    return DutyUtilizationSlotRead(
        roster_slot_id=slot.id,
        shift_template_id=slot.shift_template_id,
        slot_date=slot.slot_date,
        duty_minutes=duty_minutes,
        worked_minutes=worked_minutes,
        utilization_ratio=ratio,
        utilization_percent=percent,
        band=band,
        exceeds_on_call_threshold=exceeds,
        has_activity_record=bool(episodes),
    )


def period_utilization(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None = None,
    shift_template_id: int | None = None,
) -> DutyUtilizationPeriodRead:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    stmt = (
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_template))
        .join(RosterSlotAssignment, RosterSlotAssignment.roster_slot_id == RosterSlot.id)
        .where(RosterSlot.planning_period_id == planning_period_id)
    )
    if shift_template_id is not None:
        stmt = stmt.where(RosterSlot.shift_template_id == shift_template_id)
    if shift_group_id is not None:
        stmt = stmt.join(
            ShiftGroupShiftTemplate,
            ShiftGroupShiftTemplate.shift_template_id == RosterSlot.shift_template_id,
        ).where(ShiftGroupShiftTemplate.shift_group_id == shift_group_id)
    slots = list(db.scalars(stmt.order_by(RosterSlot.slot_date, RosterSlot.id)).unique())
    episodes_by_slot = list_duty_activity_for_slots(
        db,
        organization_id=organization_id,
        roster_slot_ids={slot.id for slot in slots},
    )
    bands = resolve_utilization_bands(db, organization_id=organization_id)
    slot_rows = [slot_utilization(slot, episodes_by_slot.get(slot.id, []), bands) for slot in slots]
    recorded = [row for row in slot_rows if row.has_activity_record]
    period_worked = sum(row.worked_minutes for row in recorded)
    period_duty = sum(row.duty_minutes for row in recorded)
    summary = _aggregate(
        worked_minutes=period_worked,
        duty_minutes=period_duty,
        recorded_duty_count=len(recorded),
        duty_count=len(slot_rows),
        bands=bands,
    )
    by_template: dict[int | None, list[DutyUtilizationSlotRead]] = defaultdict(list)
    for row in slot_rows:
        by_template[row.shift_template_id].append(row)
    templates = []
    for template_id, rows in sorted(by_template.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        recorded_rows = [row for row in rows if row.has_activity_record]
        templates.append(
            _aggregate(
                worked_minutes=sum(row.worked_minutes for row in recorded_rows),
                duty_minutes=sum(row.duty_minutes for row in recorded_rows),
                recorded_duty_count=len(recorded_rows),
                duty_count=len(rows),
                bands=bands,
                shift_template_id=template_id,
            )
        )
    return DutyUtilizationPeriodRead(
        planning_period_id=planning_period_id,
        shift_template_id=shift_template_id,
        worked_minutes=summary.worked_minutes,
        duty_minutes=summary.duty_minutes,
        utilization_ratio=summary.utilization_ratio,
        utilization_percent=summary.utilization_percent,
        band=summary.band,
        exceeds_on_call_threshold=summary.exceeds_on_call_threshold,
        coverage=summary.coverage,
        templates=templates,
        slots=slot_rows,
    )


def slot_utilization_for_assignee(
    db: Session,
    *,
    organization_id: int,
    roster_slot_id: int,
    team_member_id: int,
) -> DutyUtilizationSlotRead:
    slot = db.scalar(
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.planning_period))
        .where(RosterSlot.id == roster_slot_id)
    )
    if slot is None:
        raise ValueError("Roster slot not found")
    period = slot.planning_period or db.get(PlanningPeriod, slot.planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Roster slot not found")
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot.id)
    )
    if assignment is None or assignment.team_member_id != team_member_id:
        raise PermissionError("Team member is not assigned to this slot")
    episodes = list_duty_activity_for_slots(
        db,
        organization_id=organization_id,
        roster_slot_ids={slot.id},
    )
    bands = resolve_utilization_bands(db, organization_id=organization_id)
    return slot_utilization(slot, episodes.get(slot.id, []), bands)
