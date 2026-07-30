from datetime import date, datetime

from app.services.shift_intervals import (
    is_iso_week_cycle_on_week,
    iso_week_cycle_position,
    iso_week_ordinal,
    overlap_calendar_days,
)


class _FakeVariant:
    starts_at = datetime.strptime("20:00", "%H:%M").time()
    ends_at = datetime.strptime("06:00", "%H:%M").time()
    end_day_offset = 1


class _FakeSlot:
    def __init__(self, slot_date: date, *, starts_at=None, ends_at=None):
        self.slot_date = slot_date
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.shift_variant = _FakeVariant()
        self.shift_variant_id = 1


class _FakeDb:
    def get(self, _model, _id):
        return _FakeVariant()


def test_overlap_calendar_days_overnight():
    slot = _FakeSlot(date(2026, 7, 1))
    days = overlap_calendar_days(_FakeDb(), slot)
    assert days == [date(2026, 7, 1), date(2026, 7, 2)]


def test_iso_week_ordinal_monotonic():
    a = iso_week_ordinal(2025, 52)
    b = iso_week_ordinal(2026, 1)
    assert b > a


def test_iso_week_cycle_three_on_one_off():
    anchor_year = 2026
    anchor_week = 1
    on_week = date.fromisocalendar(2026, 2, 3)
    off_week = date.fromisocalendar(2026, 4, 3)
    assert is_iso_week_cycle_on_week(
        cell_date=on_week,
        anchor_iso_year=anchor_year,
        anchor_iso_week=anchor_week,
        cycle_weeks=4,
        on_weeks=3,
    )
    assert not is_iso_week_cycle_on_week(
        cell_date=off_week,
        anchor_iso_year=anchor_year,
        anchor_iso_week=anchor_week,
        cycle_weeks=4,
        on_weeks=3,
    )


def test_iso_week_cycle_position_wraps_year_boundary():
    pos = iso_week_cycle_position(
        cell_date=date.fromisocalendar(2026, 2, 1),
        anchor_iso_year=2025,
        anchor_iso_week=50,
        cycle_weeks=4,
    )
    assert 0 <= pos < 4
