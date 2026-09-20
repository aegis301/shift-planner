from calendar import monthrange
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.schemas import PlanningPeriodCreate, ShiftGroupCreate
from app.services.fairness import build_fairness_accounts
from app.services.organizations import create_organization_record
from app.services.planning import create_planning_period, set_shift_group_planning_to_preliminary
from app.services.roster_matrix import list_roster_slot_assignments, list_roster_slots
from app.services.rules import build_plan_state
from app.services.rules.statutory import member_worktime_metrics, statutory_rules_for_org
from app.services.shift_groups import create_shift_group
from app.services.solver_fixture import (
    SolverFixtureSafetyError,
    eligible_member_ids_for_slot,
    fixture_digest,
    greedy_assign_period,
    seed_solver_fixture,
)
from app.services.team_members import list_team_members

SEED = dict(rng_seed=1, year=2026, month=11, history_months=2)


def _memory_db() -> tuple[Session, object]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return testing_session(), engine


@pytest.fixture()
def db():
    session, engine = _memory_db()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_identical_parameters_produce_identical_digest():
    first, first_engine = _memory_db()
    second, second_engine = _memory_db()
    try:
        result_a = seed_solver_fixture(first, profile="comfortable", **SEED)
        result_b = seed_solver_fixture(second, profile="comfortable", **SEED)
        assert fixture_digest(first, result_a.organization_id) == fixture_digest(
            second, result_b.organization_id
        )
    finally:
        first.close()
        first_engine.dispose()
        second.close()
        second_engine.dispose()


def test_comfortable_greedy_assignment_fills_every_slot(db):
    result = seed_solver_fixture(db, profile="comfortable", **SEED)
    greedy_assign_period(
        db,
        planning_period_id=result.target_period_id,
        organization_id=result.organization_id,
        require_full=True,
    )
    slots = list_roster_slots(db, planning_period_id=result.target_period_id)
    assignments = list_roster_slot_assignments(db, planning_period_id=result.target_period_id)
    assert slots
    assert len(assignments) == len(slots)
    assert {row.roster_slot_id for row in assignments} == {slot.id for slot in slots}


def test_infeasible_has_unstaffable_bd24_slot(db):
    result = seed_solver_fixture(db, profile="infeasible", **SEED)
    bd24_slots = [
        slot
        for slot in list_roster_slots(db, planning_period_id=result.target_period_id)
        if slot.shift_template is not None and slot.shift_template.code == "bd24"
    ]
    assert bd24_slots
    unstaffable = [
        slot
        for slot in bd24_slots
        if not eligible_member_ids_for_slot(db, slot, organization_id=result.organization_id)
    ]
    assert unstaffable


def test_history_fairness_deviations_are_nonzero_and_unequal(db):
    result = seed_solver_fixture(db, profile="comfortable", **SEED)
    accounts = build_fairness_accounts(
        db,
        result.target_period_id,
        organization_id=result.organization_id,
    )
    duties = [
        item.deviation_absolute
        for member in accounts.members
        for item in member.dimensions
        if item.dimension_id == "duties"
    ]
    assert duties
    assert any(abs(value) > 1e-9 for value in duties)
    assert len({round(value, 6) for value in duties}) > 1


def test_weekly_average_nonzero_for_every_member(db):
    result = seed_solver_fixture(db, profile="comfortable", **SEED)
    last_day = monthrange(result.year, result.month)[1]
    state = build_plan_state(
        db,
        organization_id=result.organization_id,
        start_date=date(result.year, result.month, 1),
        end_date=date(result.year, result.month, last_day),
    )
    rules = statutory_rules_for_org(db, result.organization_id)
    members = list_team_members(db, organization_id=result.organization_id, active_only=True)
    assert members
    for member in members:
        metrics = member_worktime_metrics(state, member.id, rules)
        assert metrics["weekly_average_minutes"] > 0


def test_refuses_existing_plan_versions_without_force(db):
    create_organization_record(db, name="Default", slug="default")
    db.commit()
    organization = create_organization_record(db, name="Other", slug="other-fixture")
    db.commit()
    group = create_shift_group(
        db,
        ShiftGroupCreate(code="g1", name="Group 1"),
        organization_id=organization.id,
        actor="test",
        source="test",
    )
    period = create_planning_period(
        db,
        PlanningPeriodCreate(year=2026, month=10),
        organization_id=organization.id,
        actor="test",
        source="test",
    )
    set_shift_group_planning_to_preliminary(
        db,
        period.id,
        shift_group_id=group.id,
        organization_id=organization.id,
        actor="test",
        source="test",
    )
    with pytest.raises(SolverFixtureSafetyError, match="plan versions"):
        seed_solver_fixture(
            db,
            profile="comfortable",
            organization_id=organization.id,
            year=2026,
            month=11,
            history_months=0,
            rng_seed=1,
        )


def test_refuses_default_organization_without_force(db):
    organization = create_organization_record(db, name="Default", slug="default")
    db.commit()
    with pytest.raises(SolverFixtureSafetyError, match="DEFAULT_ORGANIZATION_ID"):
        seed_solver_fixture(
            db,
            profile="comfortable",
            organization_id=organization.id,
            year=2026,
            month=11,
            history_months=0,
            rng_seed=1,
        )
