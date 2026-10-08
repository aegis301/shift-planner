"""Re-plan existing rosters after an organization holiday was added, moved or removed.

Only the affected days are touched: each changed date plus the days before it whose overnight
variants end on it. On those days a slot is reused when the same template and position still
exist under another variant, so its assignment survives the switch (for example from the
weekday to the holiday variant). Slots without a counterpart are removed with their assignment,
and new positions are added empty. Templates of shift groups that are published in that month
are left alone and reported.

The caller owns the transaction: nothing here commits.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanningPeriod,
    PlanningPeriodShiftGroupStatus,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftGroupShiftTemplate,
)
from app.schemas import OrganizationHolidayRosterSyncRead, OrganizationHolidaySkippedGroup
from app.services.audit import record_audit
from app.services.roster_matrix import _apply_generated_to_slot
from app.services.shift_templates import (
    GeneratedSlot,
    generate_slots_for_month,
    list_shift_templates,
)
from app.services.time_entries import derive_entries


def _affected_slot_dates(db: Session, *, organization_id: int, changed_dates: Iterable[date]) -> set[date]:
    templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
    max_offset = max(
        (variant.end_day_offset for template in templates for variant in template.variants),
        default=0,
    )
    affected: set[date] = set()
    for changed in changed_dates:
        for back in range(max(0, max_offset) + 1):
            affected.add(changed - timedelta(days=back))
    return affected


def _published_templates(
    db: Session, period: PlanningPeriod
) -> tuple[set[int], list[tuple[ShiftGroup, set[int]]]]:
    rows = db.execute(
        select(ShiftGroup, PlanningPeriodShiftGroupStatus)
        .join(PlanningPeriodShiftGroupStatus, PlanningPeriodShiftGroupStatus.shift_group_id == ShiftGroup.id)
        .where(
            PlanningPeriodShiftGroupStatus.planning_period_id == period.id,
            PlanningPeriodShiftGroupStatus.status == "published",
        )
    ).all()
    protected: set[int] = set()
    groups: list[tuple[ShiftGroup, set[int]]] = []
    for group, _status in rows:
        template_ids = set(
            db.scalars(
                select(ShiftGroupShiftTemplate.shift_template_id).where(
                    ShiftGroupShiftTemplate.shift_group_id == group.id
                )
            )
        )
        protected |= template_ids
        groups.append((group, template_ids))
    return protected, groups


def _instant(value: datetime | None) -> datetime | None:
    # SQLite hands timestamps back without tzinfo; they are stored as UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _differs(slot: RosterSlot, generated: GeneratedSlot) -> bool:
    return (
        slot.label != generated.label
        or _instant(slot.starts_at) != _instant(generated.starts_at)
        or _instant(slot.ends_at) != _instant(generated.ends_at)
        or slot.day_class != generated.day_class
        or slot.shift_template_id != generated.template_id
        or slot.shift_variant_id != generated.variant_id
    )


def _sort_key(item: RosterSlot | GeneratedSlot) -> tuple:
    return (item.starts_at is None, _instant(item.starts_at))


def replan_rosters_for_holiday_change(
    db: Session,
    *,
    organization_id: int,
    changed_dates: Iterable[date],
    actor: str,
    source: str,
) -> OrganizationHolidayRosterSyncRead:
    """Bring existing planning months in line with the current organization holidays."""
    result = OrganizationHolidayRosterSyncRead()
    changed = set(changed_dates)
    if not changed:
        return result
    # The holiday write must be visible to slot generation and to derivation below.
    db.flush()
    affected = _affected_slot_dates(db, organization_id=organization_id, changed_dates=changed)
    by_month: dict[tuple[int, int], set[date]] = defaultdict(set)
    for day in affected:
        by_month[(day.year, day.month)].add(day)

    reclassified_slot_ids: set[int] = set()
    touched_member_ids: set[int] = set()
    touched_dates: set[date] = set()

    for (year, month), days in sorted(by_month.items()):
        period = db.scalar(
            select(PlanningPeriod).where(
                PlanningPeriod.organization_id == organization_id,
                PlanningPeriod.year == year,
                PlanningPeriod.month == month,
            )
        )
        if period is None:
            continue
        # A month whose roster was never generated picks the holiday up on first read.
        if db.scalar(select(RosterSlot.id).where(RosterSlot.planning_period_id == period.id).limit(1)) is None:
            continue
        protected, published_groups = _published_templates(db, period)
        before = result.model_copy()

        desired = [
            slot
            for slot in generate_slots_for_month(db, year=year, month=month, organization_id=organization_id)
            if slot.slot_date in days
        ]
        existing = [
            slot
            for slot in db.scalars(
                select(RosterSlot).where(
                    RosterSlot.planning_period_id == period.id,
                    RosterSlot.slot_date.in_(days),
                    RosterSlot.source == "template",
                )
            )
            if slot.shift_template_id is not None and slot.shift_variant_id is not None
        ]

        involved_templates = {slot.template_id for slot in desired} | {
            slot.shift_template_id for slot in existing
        }
        for group, template_ids in published_groups:
            if template_ids & involved_templates:
                result.skipped_published.append(
                    OrganizationHolidaySkippedGroup(
                        planning_period_id=period.id,
                        year=year,
                        month=month,
                        shift_group_id=group.id,
                        shift_group_name=group.name,
                    )
                )
        desired = [slot for slot in desired if slot.template_id not in protected]
        existing = [slot for slot in existing if slot.shift_template_id not in protected]

        # Pass 1: the same variant still applies; refresh times, label and day class.
        desired_by_key = {(slot.slot_date, slot.variant_id, slot.position): slot for slot in desired}
        unmatched_existing: list[RosterSlot] = []
        matched_keys: set[tuple[date, int, int]] = set()
        for slot in existing:
            key = (slot.slot_date, slot.shift_variant_id, slot.position)
            generated = desired_by_key.get(key)
            if generated is None:
                unmatched_existing.append(slot)
                continue
            matched_keys.add(key)
            if not _differs(slot, generated):
                continue
            if slot.day_class != generated.day_class:
                reclassified_slot_ids.add(slot.id)
            _apply_generated_to_slot(slot, generated)
            result.slots_updated += 1
        unmatched_desired = [
            slot for slot in desired if (slot.slot_date, slot.variant_id, slot.position) not in matched_keys
        ]

        # Pass 2: same template and position under another variant; reuse the slot so the
        # assignment stays. Several variants per position pair up in start-time order.
        existing_groups: dict[tuple[date, int, int], list[RosterSlot]] = defaultdict(list)
        for slot in unmatched_existing:
            existing_groups[(slot.slot_date, slot.shift_template_id, slot.position)].append(slot)
        desired_groups: dict[tuple[date, int, int], list[GeneratedSlot]] = defaultdict(list)
        for generated in unmatched_desired:
            desired_groups[(generated.slot_date, generated.template_id, generated.position)].append(generated)

        removed: list[RosterSlot] = []
        added: list[GeneratedSlot] = []
        for key in set(existing_groups) | set(desired_groups):
            olds = sorted(existing_groups.get(key, []), key=_sort_key)
            news = sorted(desired_groups.get(key, []), key=_sort_key)
            for old, new in zip(olds, news, strict=False):
                _apply_generated_to_slot(old, new)
                result.slots_updated += 1
                reclassified_slot_ids.add(old.id)
                assignment = db.scalar(
                    select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == old.id)
                )
                if assignment is not None:
                    result.assignments_kept += 1
                    touched_member_ids.add(assignment.team_member_id)
                    touched_dates.add(old.slot_date)
            removed.extend(olds[len(news) :])
            added.extend(news[len(olds) :])

        for slot in removed:
            assignment = db.scalar(
                select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot.id)
            )
            if assignment is not None:
                touched_member_ids.add(assignment.team_member_id)
                touched_dates.add(slot.slot_date)
                db.delete(assignment)
                result.assignments_cleared += 1
            db.delete(slot)
            result.slots_removed += 1
        for generated in added:
            db.add(
                RosterSlot(
                    planning_period_id=period.id,
                    shift_template_id=generated.template_id,
                    shift_variant_id=generated.variant_id,
                    slot_date=generated.slot_date,
                    position=generated.position,
                    label=generated.label,
                    starts_at=generated.starts_at,
                    ends_at=generated.ends_at,
                    day_class=generated.day_class,
                    source="template",
                )
            )
            result.slots_added += 1

        # Day-class-only changes on matched slots also move valuation.
        for slot in existing:
            if slot.id in reclassified_slot_ids:
                assignment = db.scalar(
                    select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot.id)
                )
                if assignment is not None:
                    touched_member_ids.add(assignment.team_member_id)
                    touched_dates.add(slot.slot_date)

        result.planning_period_ids.append(period.id)
        record_audit(
            db,
            actor=actor,
            source=source,
            action="holiday_replan",
            entity_type="planning_period_roster_slots",
            entity_id=period.id,
            details={
                "changed_dates": sorted(day.isoformat() for day in changed),
                "slots_updated": result.slots_updated - before.slots_updated,
                "slots_added": result.slots_added - before.slots_added,
                "slots_removed": result.slots_removed - before.slots_removed,
                "assignments_kept": result.assignments_kept - before.assignments_kept,
                "assignments_cleared": result.assignments_cleared - before.assignments_cleared,
                "skipped_shift_group_ids": [
                    item.shift_group_id for item in result.skipped_published if item.planning_period_id == period.id
                ],
            },
        )

    db.flush()
    if touched_member_ids and touched_dates:
        derive_entries(
            db,
            organization_id=organization_id,
            start_date=min(touched_dates),
            end_date=max(touched_dates),
            member_ids=sorted(touched_member_ids),
            commit=False,
            revalue_slot_ids=reclassified_slot_ids,
        )
    return result
