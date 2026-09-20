from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

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
from app.schemas import ContractCategoryRule
from app.services.holidays import classify_day
from app.services.time_entries import derive_entries, list_time_entries
from app.services.work_time_valuation import statutory_work_minutes, tariff_credit_minutes

STUFE_I = ContractCategoryRule(
    category="bereitschaftsdienst",
    credit_mode="factor",
    credit_factor=Decimal("0.6"),
    holiday_credit_bonus=Decimal("25"),
    statutory_factor=Decimal("1"),
    call_outs_count_as_work=False,
)
STUFE_II = STUFE_I.model_copy(update={"credit_factor": Decimal("0.95")})
RUF = ContractCategoryRule(
    category="rufdienst",
    counts_toward_contract=False,
    credit_mode="none",
    holiday_credit_bonus=Decimal("0"),
    statutory_factor=Decimal("1"),
    call_outs_count_as_work=True,
)


def _slot(*, slot_date: date, hours: int = 24) -> SimpleNamespace:
    start = datetime(slot_date.year, slot_date.month, slot_date.day, 8, 0, tzinfo=UTC)
    return SimpleNamespace(slot_date=slot_date, starts_at=start, ends_at=start + timedelta(hours=hours))


def _group(*rules: ContractCategoryRule) -> SimpleNamespace:
    return SimpleNamespace(category_rules=[rule.model_dump(mode="json") for rule in rules])


def _template(category: str, override: ContractCategoryRule | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        category=category,
        valuation_override=None if override is None else override.model_dump(mode="json"),
    )


def test_functions_are_pure():
    source = Path(__file__).resolve().parents[1] / "services" / "work_time_valuation.py"
    text = source.read_text()
    assert "sqlalchemy" not in text
    assert "Session" not in text
    weekday = date(2026, 3, 2)
    assert classify_day(weekday) == "weekday"
    statutory_work_minutes(
        slot=_slot(slot_date=weekday),
        contract_group=_group(STUFE_I),
        template=_template("bereitschaftsdienst"),
        day_class="weekday",
        episodes=(),
    )


def test_weekday_bereitschaft_stufe_i():
    weekday = date(2026, 3, 2)
    slot = _slot(slot_date=weekday)
    group = _group(STUFE_I)
    template = _template("bereitschaftsdienst")
    assert statutory_work_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=()
    ) == 1440
    assert tariff_credit_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=()
    ) == 864


def test_holiday_bereitschaft_adds_percentage_points():
    holiday = date(2026, 5, 1)
    assert classify_day(holiday) == "holiday"
    slot = _slot(slot_date=holiday)
    group = _group(STUFE_I)
    template = _template("bereitschaftsdienst")
    assert statutory_work_minutes(
        slot=slot, contract_group=group, template=template, day_class="holiday", episodes=()
    ) == 1440
    assert tariff_credit_minutes(
        slot=slot, contract_group=group, template=template, day_class="holiday", episodes=()
    ) == 1224


def test_rufbereitschaft_adds_call_out_episodes():
    weekday = date(2026, 3, 2)
    slot = _slot(slot_date=weekday)
    group = _group(RUF)
    template = _template("rufdienst")
    episodes = (SimpleNamespace(duration_minutes=30), SimpleNamespace(duration_minutes=45))
    assert statutory_work_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=episodes
    ) == 75
    assert tariff_credit_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=episodes
    ) == 75


def test_template_override_beats_contract_group_rule():
    weekday = date(2026, 3, 2)
    slot = _slot(slot_date=weekday)
    group = _group(STUFE_I)
    template = _template("bereitschaftsdienst", override=STUFE_II)
    assert tariff_credit_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=()
    ) == 1368
    assert statutory_work_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=()
    ) == 1440


def test_contract_group_factor_change_does_not_rewrite_stored_entries():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    try:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        group = ContractGroup(
            organization_id=1,
            name="Standard",
            weekly_hours_at_100=Decimal("40"),
            vacation_days_at_100=Decimal("30"),
            regular_week_pattern=[],
            category_rules=[STUFE_I.model_dump(mode="json")],
            status_mappings=[],
        )
        db.add(group)
        member = TeamMember(
            organization_id=1,
            first_name="Pat",
            last_name="Ledger",
            email="ledger-val@example.com",
        )
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
        template = ShiftTemplate(
            organization_id=1,
            code="BD",
            name="Bereitschaft",
            category="bereitschaftsdienst",
        )
        db.add(template)
        db.flush()
        variant = ShiftVariant(
            shift_template_id=template.id,
            label="24h",
            start_day_class="any",
            starts_at=time(8, 0),
            ends_at=time(8, 0),
            end_day_offset=1,
            required_count=1,
        )
        db.add(variant)
        period = PlanningPeriod(organization_id=1, year=2026, month=3, status="draft")
        db.add(period)
        db.flush()
        start = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
        slot = RosterSlot(
            planning_period_id=period.id,
            shift_template_id=template.id,
            shift_variant_id=variant.id,
            slot_date=date(2026, 3, 2),
            position=1,
            starts_at=start,
            ends_at=start + timedelta(hours=24),
        )
        db.add(slot)
        db.flush()
        db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
        db.commit()
        derive_entries(
            db,
            organization_id=1,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            member_ids=[member.id],
        )
        rows = list_time_entries(
            db,
            organization_id=1,
            team_member_id=member.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert len(rows) == 1
        assert rows[0].statutory_minutes == 1440
        assert rows[0].credited_minutes == 864
        entry_id = rows[0].id
        group.category_rules = [STUFE_II.model_dump(mode="json")]
        db.commit()
        derive_entries(
            db,
            organization_id=1,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            member_ids=[member.id],
        )
        again = list_time_entries(
            db,
            organization_id=1,
            team_member_id=member.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert again[0].id == entry_id
        assert again[0].credited_minutes == 864
        assert again[0].statutory_minutes == 1440
    finally:
        db.close()
        engine.dispose()
