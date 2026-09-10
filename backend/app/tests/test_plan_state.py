from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker
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
    TeamMemberPropertyDefinition,
    TeamMemberPropertyValue,
    TimeEntry,
)
from app.models.base import Base
from app.services.rules import build_plan_state, clear_rules, register_rule
from app.services.rules.state import PlanState


@dataclass
class FakeRule:
    lookback: timedelta
    code: str = "FAKE_LOOKBACK"
    severity: Literal["warning"] = "warning"

    def evaluate(self, state: PlanState) -> list:
        del state
        return []


@pytest.fixture()
def plan_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = testing_session()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db, engine
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rules():
    clear_rules()
    yield
    clear_rules()


def _add_template(db: Session) -> tuple[ShiftTemplate, ShiftVariant]:
    template = ShiftTemplate(
        organization_id=1,
        code="bd",
        name="BD",
        category="bereitschaftsdienst",
        constraints=[],
    )
    db.add(template)
    db.flush()
    variant = ShiftVariant(
        shift_template_id=template.id,
        label="weekday",
        start_day_class="weekday",
        starts_at=time(8, 0),
        ends_at=time(16, 0),
        required_count=1,
        constraints=[],
    )
    db.add(variant)
    db.flush()
    return template, variant


def _add_period(db: Session, year: int, month: int) -> PlanningPeriod:
    period = PlanningPeriod(organization_id=1, year=year, month=month, status="draft")
    db.add(period)
    db.flush()
    return period


def _add_member(db: Session, *, email: str, first_name: str = "A") -> TeamMember:
    member = TeamMember(
        organization_id=1,
        first_name=first_name,
        last_name="B",
        email=email,
        is_active=True,
    )
    db.add(member)
    db.flush()
    return member


def _add_slot(
    db: Session,
    *,
    period: PlanningPeriod,
    template: ShiftTemplate,
    variant: ShiftVariant,
    slot_date: date,
    position: int = 1,
) -> RosterSlot:
    slot = RosterSlot(
        planning_period_id=period.id,
        shift_template_id=template.id,
        shift_variant_id=variant.id,
        slot_date=slot_date,
        position=position,
        label=variant.label,
    )
    db.add(slot)
    db.flush()
    return slot


def _add_assignment(db: Session, *, slot: RosterSlot, member: TeamMember) -> RosterSlotAssignment:
    row = RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id)
    db.add(row)
    db.flush()
    return row


def _seed_adjacent_months(db: Session) -> tuple[RosterSlotAssignment, RosterSlotAssignment]:
    template, variant = _add_template(db)
    jan = _add_period(db, 2026, 1)
    feb = _add_period(db, 2026, 2)
    member = _add_member(db, email="ab@example.com")
    jan_slot = _add_slot(db, period=jan, template=template, variant=variant, slot_date=date(2026, 1, 31))
    feb_slot = _add_slot(db, period=feb, template=template, variant=variant, slot_date=date(2026, 2, 1))
    jan_asg = _add_assignment(db, slot=jan_slot, member=member)
    feb_asg = _add_assignment(db, slot=feb_slot, member=member)
    db.commit()
    return jan_asg, feb_asg


def _collect_statements(engine, callback) -> list[str]:
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        callback()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    return statements


def test_build_plan_state_loads_assignments_across_month_boundary(plan_db):
    db, _engine = plan_db
    jan_asg, feb_asg = _seed_adjacent_months(db)
    state = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 1, 31),
        end_date=date(2026, 2, 1),
    )
    assert jan_asg.id in state.assignments_by_id
    assert feb_asg.id in state.assignments_by_id
    assert state.assignments_by_slot_id[jan_asg.roster_slot_id].id == jan_asg.id
    assert date(2026, 1, 31) in state.slots_by_date
    assert date(2026, 2, 1) in state.slots_by_date
    assert state.time_entries_by_member_id == {}
    assert state.employment_periods_by_member_id == {}
    slot = state.slots_by_id[jan_asg.roster_slot_id]
    unloaded = inspect(slot).unloaded
    assert "shift_template" not in unloaded
    assert "shift_variant" not in unloaded


def test_lookback_widening_is_driven_by_registered_rules(plan_db):
    db, _engine = plan_db
    template, variant = _add_template(db)
    jan = _add_period(db, 2026, 1)
    mar = _add_period(db, 2026, 3)
    member = _add_member(db, email="lookback@example.com")
    included = _add_slot(db, period=jan, template=template, variant=variant, slot_date=date(2026, 1, 20))
    excluded = _add_slot(db, period=jan, template=template, variant=variant, slot_date=date(2026, 1, 19), position=2)
    march_slot = _add_slot(db, period=mar, template=template, variant=variant, slot_date=date(2026, 3, 1))
    _add_assignment(db, slot=included, member=member)
    _add_assignment(db, slot=excluded, member=member)
    _add_assignment(db, slot=march_slot, member=member)
    db.commit()

    without_rule = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    assert without_rule.load_start == date(2026, 1, 29)
    assert included.id not in without_rule.slots_by_id
    assert march_slot.id in without_rule.slots_by_id

    register_rule(FakeRule(lookback=timedelta(days=40)))
    widened = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    assert widened.load_start == date(2026, 1, 20)
    assert included.id in widened.slots_by_id
    assert excluded.id not in widened.slots_by_id
    assert march_slot.id in widened.slots_by_id


def _seed_members_with_assignments_and_properties(db: Session, count: int) -> None:
    template, variant = _add_template(db)
    period = _add_period(db, 2026, 3)
    definition = TeamMemberPropertyDefinition(
        organization_id=1,
        name="grade",
        type="number",
        options=[],
    )
    db.add(definition)
    db.flush()
    for index in range(count):
        member = _add_member(db, email=f"m{index}@example.com", first_name=f"M{index}")
        slot = _add_slot(
            db,
            period=period,
            template=template,
            variant=variant,
            slot_date=date(2026, 3, 1 + (index % 31)),
            position=1 + index,
        )
        _add_assignment(db, slot=slot, member=member)
        db.add(
            TeamMemberPropertyValue(
                organization_id=1,
                team_member_id=member.id,
                property_definition_id=definition.id,
                value=index,
            )
        )
    db.commit()


def test_build_plan_state_query_count_does_not_scale_with_members(plan_db):
    db, engine = plan_db
    _seed_members_with_assignments_and_properties(db, 20)

    def run():
        build_plan_state(
            db,
            organization_id=1,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    statements_20 = _collect_statements(engine, run)
    assert len(statements_20) <= 20
    slot_loads = [
        statement
        for statement in statements_20
        if "roster_slots" in statement.lower() and "roster_slot_assignments" not in statement.lower()
    ]
    assignment_loads = [
        statement for statement in statements_20 if "roster_slot_assignments" in statement.lower()
    ]
    property_loads = [
        statement
        for statement in statements_20
        if "team_member_property_values" in statement.lower()
    ]
    assert len(slot_loads) == 1
    assert len(assignment_loads) == 1
    assert len(property_loads) == 1

    db.close()
    engine.dispose()

    small_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    small_session = sessionmaker(
        bind=small_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(small_engine)
    small_db = small_session()
    small_db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    small_db.commit()
    _seed_members_with_assignments_and_properties(small_db, 5)
    try:
        statements_5 = _collect_statements(
            small_engine,
            lambda: build_plan_state(
                small_db,
                organization_id=1,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
            ),
        )
    finally:
        small_db.close()
        small_engine.dispose()

    assert len(statements_5) == len(statements_20)


def test_build_plan_state_empty_window(plan_db):
    db, engine = plan_db
    _seed_adjacent_months(db)
    captured: dict[str, PlanState] = {}

    def run():
        captured["state"] = build_plan_state(
            db,
            organization_id=1,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 31),
        )

    statements = _collect_statements(engine, run)
    state = captured["state"]
    assert statements == []
    assert state.assignments_by_id == {}
    assert state.slots_by_id == {}
    assert state.members_by_id == {}
    assert state.time_entries_by_member_id == {}
    assert state.employment_periods_by_member_id is not None
    assert dict(state.employment_periods_by_member_id) == {}


def test_build_plan_state_single_day_window(plan_db):
    db, _engine = plan_db
    _jan_asg, feb_asg = _seed_adjacent_months(db)
    state = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )
    assert state.start_date == state.end_date == date(2026, 2, 1)
    assert feb_asg.id in state.assignments_by_id
    assert date(2026, 2, 1) in state.slots_by_date


def test_build_plan_state_cross_year_window(plan_db):
    db, _engine = plan_db
    template, variant = _add_template(db)
    dec = _add_period(db, 2026, 12)
    jan = _add_period(db, 2027, 1)
    member = _add_member(db, email="year@example.com")
    dec_slot = _add_slot(db, period=dec, template=template, variant=variant, slot_date=date(2026, 12, 31))
    jan_slot = _add_slot(db, period=jan, template=template, variant=variant, slot_date=date(2027, 1, 1))
    dec_asg = _add_assignment(db, slot=dec_slot, member=member)
    jan_asg = _add_assignment(db, slot=jan_slot, member=member)
    db.commit()
    state = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 12, 31),
        end_date=date(2027, 1, 1),
    )
    assert dec_asg.id in state.assignments_by_id
    assert jan_asg.id in state.assignments_by_id


def test_build_plan_state_loads_time_entries_and_employment_periods(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="ledger@example.com")
    group = ContractGroup(
        organization_id=1,
        name="Standard",
        weekly_hours_at_100=Decimal("40"),
        vacation_days_at_100=Decimal("30"),
        regular_week_pattern=[],
        category_rules=[],
        status_mappings=[],
    )
    db.add(group)
    db.flush()
    period = EmploymentPeriod(
        team_member_id=member.id,
        contract_group_id=group.id,
        employment_percentage=80,
        start_date=date(2026, 1, 1),
        end_date=None,
    )
    db.add(period)
    entry = TimeEntry(
        organization_id=1,
        team_member_id=member.id,
        entry_date=date(2026, 2, 1),
        kind="work",
        source="manual",
        duration_minutes=60,
    )
    db.add(entry)
    db.commit()
    state = build_plan_state(
        db,
        organization_id=1,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )
    assert state.employment_periods_by_member_id[member.id][0].id == period.id
    assert state.time_entries_by_member_id[member.id][0].id == entry.id


def test_no_existing_module_imports_rules_package():
    app_root = Path(__file__).resolve().parents[1]
    forbidden = "app.services.rules"
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        posix = path.as_posix()
        if "/services/rules/" in posix or posix.endswith("/tests/test_plan_state.py"):
            continue
        if posix.endswith("/services/constraints.py") or posix.endswith("/services/validation.py"):
            continue
        if posix.endswith("/services/roster_matrix.py") or posix.endswith("/services/workload.py"):
            continue
        if posix.endswith("/services/dashboard.py"):
            continue
        if posix.endswith("/tests/test_constraints_golden.py") or posix.endswith("/tests/test_plan_state.py"):
            continue
        if forbidden in path.read_text():
            offenders.append(str(path.relative_to(app_root)))
    assert offenders == []
