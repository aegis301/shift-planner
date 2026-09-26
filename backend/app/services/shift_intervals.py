from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import RosterSlot, ShiftVariant
from app.services.org_time import as_utc, local_dates_spanned, slot_bounds, timezone_for_slot

ISO_WEEK_EPOCH_YEAR = 2000
ISO_WEEK_EPOCH_WEEK = 1


def resolve_slot_interval(db: Session, slot: RosterSlot) -> tuple[datetime, datetime] | None:
    if slot.starts_at is not None and slot.ends_at is not None:
        return as_utc(slot.starts_at), as_utc(slot.ends_at)
    variant: ShiftVariant | None = slot.shift_variant
    if variant is None and slot.shift_variant_id is not None:
        variant = db.get(ShiftVariant, slot.shift_variant_id)
    if variant is None:
        return None
    return slot_bounds(
        slot.slot_date,
        variant.starts_at,
        variant.ends_at,
        variant.end_day_offset,
        timezone_for_slot(db, slot),
    )


def overlap_calendar_days(db: Session, slot: RosterSlot) -> list[date]:
    interval = resolve_slot_interval(db, slot)
    if interval is None:
        return [slot.slot_date]
    shift_start, shift_end = interval
    return local_dates_spanned(shift_start, shift_end, timezone_for_slot(db, slot))


def iso_week_ordinal(iso_year: int, iso_week: int) -> int:
    epoch = date.fromisocalendar(ISO_WEEK_EPOCH_YEAR, ISO_WEEK_EPOCH_WEEK, 1)
    target = date.fromisocalendar(iso_year, iso_week, 1)
    return (target - epoch).days // 7


def iso_week_cycle_position(
    *,
    cell_date: date,
    anchor_iso_year: int,
    anchor_iso_week: int,
    cycle_weeks: int,
) -> int:
    iso_year, iso_week, _ = cell_date.isocalendar()
    anchor_ordinal = iso_week_ordinal(anchor_iso_year, anchor_iso_week)
    current_ordinal = iso_week_ordinal(iso_year, iso_week)
    delta = current_ordinal - anchor_ordinal
    return delta % cycle_weeks


def is_iso_week_cycle_on_week(
    *,
    cell_date: date,
    anchor_iso_year: int,
    anchor_iso_week: int,
    cycle_weeks: int,
    on_weeks: int,
) -> bool:
    return iso_week_cycle_position(
        cell_date=cell_date,
        anchor_iso_year=anchor_iso_year,
        anchor_iso_week=anchor_iso_week,
        cycle_weeks=cycle_weeks,
    ) < on_weeks
