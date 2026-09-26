from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    ContractGroup,
    EmploymentPeriod,
    Organization,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
)
from app.models.base import Base
from app.schemas import DutyActivityCreate
from app.services.duty_activity import record_duty_activity
from app.services.ics_export import _resolve_event_times
from app.services.rules.builder import _is_night_duty
from app.services.shift_swaps import _slot_is_night_duty
from app.services.shift_templates import generate_slots_for_month
from app.services.work_time_valuation import statutory_work_minutes


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return session_factory()


def _overnight_template(db, *, starts: time, ends: time, end_day_offset: int) -> ShiftVariant:
    template = ShiftTemplate(
        organization_id=1,
        code="BD",
        name="Bereitschaft",
        category="bereitschaftsdienst",
        constraints=[],
    )
    db.add(template)
    db.flush()
    variant = ShiftVariant(
        shift_template_id=template.id,
        label="24h",
        start_day_class="any",
        starts_at=starts,
        ends_at=ends,
        end_day_offset=end_day_offset,
        required_count=1,
        constraints=[],
    )
    db.add(variant)
    db.flush()
    return variant


def _generated(db, year: int, month: int, slot_date: date):
    rows = generate_slots_for_month(db, year=year, month=month, organization_id=1)
    match = [row for row in rows if row.slot_date == slot_date]
    assert len(match) == 1
    return match[0]


@pytest.fixture()
def org_db():
    db = _db()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_summer_slot_stores_berlin_instant(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(8, 0), end_day_offset=1)
    db.commit()
    slot = _generated(db, 2026, 7, date(2026, 7, 1))
    assert _as_utc(slot.starts_at) == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    assert _as_utc(slot.ends_at) == datetime(2026, 7, 2, 6, 0, tzinfo=UTC)


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_october_dst_fallback_duty_has_25_statutory_hours(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(8, 0), end_day_offset=1)
    db.commit()
    slot = _generated(db, 2026, 10, date(2026, 10, 24))
    minutes = statutory_work_minutes(
        slot=slot,
        contract_group=None,
        template=SimpleTemplate("bereitschaftsdienst"),
        day_class="weekend",
        episodes=(),
    )
    assert minutes == 25 * 60


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_march_dst_spring_forward_duty_has_23_statutory_hours(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(8, 0), end_day_offset=1)
    db.commit()
    slot = _generated(db, 2027, 3, date(2027, 3, 27))
    minutes = statutory_work_minutes(
        slot=slot,
        contract_group=None,
        template=SimpleTemplate("bereitschaftsdienst"),
        day_class="weekend",
        episodes=(),
    )
    assert minutes == 23 * 60


def test_same_day_duty_statutory_minutes_unchanged(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(16, 0), end_day_offset=0)
    db.commit()
    slot = _generated(db, 2026, 7, date(2026, 7, 1))
    minutes = statutory_work_minutes(
        slot=slot,
        contract_group=None,
        template=SimpleTemplate("other"),
        day_class="weekday",
        episodes=(),
    )
    assert minutes == 8 * 60
    assert _slot_is_night_duty(slot) is False


class SimpleTemplate:
    def __init__(self, category: str) -> None:
        self.category = category
        self.valuation_override = None


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_duty_activity_at_local_0830_fits_0800_slot(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(16, 0), end_day_offset=0)
    group = ContractGroup(
        organization_id=1,
        name="BD",
        weekly_hours_at_100=Decimal("40"),
        vacation_days_at_100=Decimal("30"),
        regular_week_pattern=[],
        category_rules=[
            {
                "category": "bereitschaftsdienst",
                "counts_toward_contract": True,
                "credit_mode": "duration",
                "holiday_credit_bonus": "0",
                "statutory_factor": "1",
                "call_outs_count_as_work": False,
            }
        ],
        status_mappings=[],
    )
    db.add(group)
    db.flush()
    member = TeamMember(organization_id=1, first_name="A", last_name="B", email="a@example.com", is_active=True)
    db.add(member)
    db.flush()
    db.add(
        EmploymentPeriod(
            team_member_id=member.id,
            contract_group_id=group.id,
            employment_percentage=100,
            start_date=date(2000, 1, 1),
            end_date=None,
        )
    )
    period = PlanningPeriod(organization_id=1, year=2026, month=7, status="published")
    db.add(period)
    db.flush()
    generated = _generated(db, 2026, 7, date(2026, 7, 1))
    template = db.query(ShiftTemplate).one()
    variant = db.query(ShiftVariant).one()
    slot = RosterSlot(
        planning_period_id=period.id,
        shift_template_id=template.id,
        shift_variant_id=variant.id,
        slot_date=generated.slot_date,
        position=1,
        label=generated.label,
        starts_at=generated.starts_at,
        ends_at=generated.ends_at,
        day_class="weekday",
    )
    db.add(slot)
    db.flush()
    db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
    db.commit()
    started = datetime(2026, 7, 1, 6, 30, tzinfo=UTC)
    row = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=slot.id,
            kind="in_duty_activity",
            started_at=started,
            ended_at=datetime(2026, 7, 1, 7, 0, tzinfo=UTC),
        ),
        organization_id=1,
        team_member_id=member.id,
        actor="test",
        source="test",
    )
    assert row.started_at is not None


def test_night_duty_21_to_07_summer_and_winter():
    summer = RosterSlot(
        slot_date=date(2026, 7, 1),
        starts_at=datetime(2026, 7, 1, 19, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 2, 5, 0, tzinfo=UTC),
    )
    winter = RosterSlot(
        slot_date=date(2026, 1, 15),
        starts_at=datetime(2026, 1, 15, 20, 0, tzinfo=UTC),
        ends_at=datetime(2026, 1, 16, 6, 0, tzinfo=UTC),
    )
    assert _slot_is_night_duty(summer) is True
    assert _slot_is_night_duty(winter) is True
    assert _is_night_duty(summer.slot_date, summer.starts_at, summer.ends_at) is True
    assert _is_night_duty(winter.slot_date, winter.starts_at, winter.ends_at) is True


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_evening_21_local_is_night_when_stored_as_utc_instant():
    summer = RosterSlot(
        slot_date=date(2026, 7, 1),
        starts_at=datetime(2026, 7, 1, 19, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 21, 0, tzinfo=UTC),
    )
    winter = RosterSlot(
        slot_date=date(2026, 1, 15),
        starts_at=datetime(2026, 1, 15, 20, 0, tzinfo=UTC),
        ends_at=datetime(2026, 1, 15, 22, 0, tzinfo=UTC),
    )
    assert _slot_is_night_duty(summer) is True
    assert _slot_is_night_duty(winter) is True
    assert _is_night_duty(summer.slot_date, summer.starts_at, summer.ends_at) is True
    assert _is_night_duty(winter.slot_date, winter.starts_at, winter.ends_at) is True


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_early_morning_local_is_not_night():
    winter = RosterSlot(
        slot_date=date(2026, 1, 15),
        starts_at=datetime(2026, 1, 14, 23, 30, tzinfo=UTC),
        ends_at=datetime(2026, 1, 15, 7, 0, tzinfo=UTC),
    )
    assert _slot_is_night_duty(winter) is False
    assert _is_night_duty(winter.slot_date, winter.starts_at, winter.ends_at) is False


@pytest.mark.xfail(reason="slot times are wall-clock values labelled as UTC", strict=True)
def test_ics_resolve_uses_real_instant_for_generated_slot(org_db):
    db = org_db
    _overnight_template(db, starts=time(8, 0), ends=time(8, 0), end_day_offset=1)
    db.commit()
    generated = _generated(db, 2026, 7, date(2026, 7, 1))
    slot = RosterSlot(
        slot_date=generated.slot_date,
        starts_at=generated.starts_at,
        ends_at=generated.ends_at,
        shift_variant_id=None,
    )
    start, end, all_day = _resolve_event_times(slot)
    assert all_day is False
    assert start is not None and end is not None
    assert _as_utc(start) == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    assert _as_utc(end) == datetime(2026, 7, 2, 6, 0, tzinfo=UTC)
