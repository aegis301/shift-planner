from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import PlanningPeriod, RosterSlot
from app.models.base import Base
from app.schemas import RosterSlotAssignmentUpsert
from app.services.roster_matrix import upsert_roster_slot_assignment
from app.services.rules import build_plan_state
from app.services.rules.builtin import (
    ConsecutiveWeekendsRule,
    DuplicateDayRule,
    TemplateNoGoConflictRule,
)
from app.services.rules.registry import resolve_active_rules
from app.services.rules.shift_constraints import (
    MaxAssignmentsPerMonthRule,
    MinRestHoursRule,
    NoAdditionalSameDayRule,
    RequiresCoupledShiftRule,
    TeamMemberPropertyRequirementRule,
    UnavailableOverlapPolicyRule,
)
from app.services.rules.statutory import (
    MaxDailyWorkingTimeRule,
    MinRestPeriodRule,
    RestAfterLongDutyRule,
    WeeklyAverageCapRule,
)
from app.services.solver.model import build_solver_context, cpsat_supported_codes, planning_window
from app.services.solver.solve import list_solver_target_slots, solve_roster
from app.services.solver.weights import read_solver_objective_weights
from app.services.solver_fixture import eligible_member_ids_for_slot, seed_solver_fixture

SPIKE_SEED = dict(rng_seed=1, year=2026, month=10, history_months=2)
TIER_B_CODES = {"WORKTIME_MIN_REST", "WORKTIME_REST_AFTER_LONG_DUTY", "WORKTIME_WEEKLY_AVERAGE"}
EVALUATE_CLASSES = (
    NoAdditionalSameDayRule,
    MinRestHoursRule,
    UnavailableOverlapPolicyRule,
    MaxAssignmentsPerMonthRule,
    RequiresCoupledShiftRule,
    TeamMemberPropertyRequirementRule,
    TemplateNoGoConflictRule,
    DuplicateDayRule,
    ConsecutiveWeekendsRule,
    MaxDailyWorkingTimeRule,
    MinRestPeriodRule,
    RestAfterLongDutyRule,
    WeeklyAverageCapRule,
)


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


def _run_for(result, *, random_seed: int = 1, overwrite_existing: bool = False):
    return SimpleNamespace(
        organization_id=result.organization_id,
        planning_period_id=result.target_period_id,
        shift_group_id=result.shift_group_ids[0],
        parameters={
            "time_budget_seconds": 30,
            "num_search_workers": 1,
            "random_seed": random_seed,
            "overwrite_existing": overwrite_existing,
        },
    )


def _deadline(seconds: float = 30) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _solve(db: Session, result, *, random_seed: int = 1, overwrite_existing: bool = False):
    return solve_roster(
        db,
        _run_for(result, random_seed=random_seed, overwrite_existing=overwrite_existing),
        is_cancelled=lambda: False,
        deadline=_deadline(),
    )


def test_variable_construction_does_not_call_evaluate(db, monkeypatch):
    result = seed_solver_fixture(db, profile="comfortable", **SPIKE_SEED)
    calls: list[str] = []

    def boom(self, state):
        del state
        calls.append(type(self).__name__)
        raise AssertionError("evaluate() called during variable construction")

    for cls in EVALUATE_CLASSES:
        monkeypatch.setattr(cls, "evaluate", boom)

    def boom_plan(*args, **kwargs):
        del args, kwargs
        raise AssertionError("evaluate_plan_state called during variable construction")

    monkeypatch.setattr("app.services.rules.registry.evaluate_plan_state", boom_plan)
    period = db.get(PlanningPeriod, result.target_period_id)
    assert period is not None
    start, end = planning_window(period)
    state = build_plan_state(
        db,
        organization_id=result.organization_id,
        start_date=start,
        end_date=end,
    )
    slots = list_solver_target_slots(
        db,
        planning_period_id=result.target_period_id,
        shift_group_id=result.shift_group_ids[0],
        organization_id=result.organization_id,
    )
    from app.models import Organization

    org = db.get(Organization, result.organization_id)
    build_solver_context(
        db,
        state=state,
        target_slots=slots,
        weights=read_solver_objective_weights(org),
        overwrite_existing=False,
    )
    assert calls == []


@pytest.mark.parametrize("profile", ["comfortable", "tight", "infeasible"])
def test_proposed_assignments_pass_preflight(db, profile):
    result = seed_solver_fixture(db, profile=profile, **SPIKE_SEED)
    solved = _solve(db, result)
    for row in solved.proposed_assignments:
        upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(
                roster_slot_id=int(row["roster_slot_id"]),
                team_member_id=int(row["team_member_id"]),
                comment=row.get("comment"),
                manual_override=bool(row.get("manual_override", False)),
            ),
            organization_id=result.organization_id,
            actor="test",
            source="test",
        )


@pytest.mark.parametrize("profile", ["comfortable", "tight"])
def test_post_check_empty_for_cpsat_supported_rules(db, profile):
    result = seed_solver_fixture(db, profile=profile, **SPIKE_SEED)
    solved = _solve(db, result)
    period = db.get(PlanningPeriod, result.target_period_id)
    assert period is not None
    start, end = planning_window(period)
    rules = resolve_active_rules(result.organization_id, start, end, db=db)
    supported = cpsat_supported_codes(rules)
    found = {row["code"] for row in solved.post_check_findings}
    assert not (found & supported)


def test_two_runs_on_identical_input_produce_identical_roster(db):
    result = seed_solver_fixture(db, profile="comfortable", **SPIKE_SEED)
    first = _solve(db, result, random_seed=1)
    second = _solve(db, result, random_seed=1)

    def assignment_key(row: dict) -> tuple[int, int]:
        return int(row["roster_slot_id"]), int(row["team_member_id"])

    assert sorted(first.proposed_assignments, key=assignment_key) == sorted(
        second.proposed_assignments, key=assignment_key
    )
    assert first.unfilled_slots == second.unfilled_slots


@pytest.mark.parametrize("profile", ["comfortable", "tight"])
def test_tdl_profiles_fill_all_slots_within_five_seconds(db, profile):
    result = seed_solver_fixture(db, profile=profile, **SPIKE_SEED)
    started = datetime.now(UTC)
    solved = _solve(db, result)
    elapsed = (datetime.now(UTC) - started).total_seconds()
    slot_count = len(
        list_solver_target_slots(
            db,
            planning_period_id=result.target_period_id,
            shift_group_id=result.shift_group_ids[0],
            organization_id=result.organization_id,
        )
    )
    assert elapsed < 5.0
    assert len(solved.proposed_assignments) == slot_count
    assert solved.unfilled_slots == []


def test_infeasible_returns_known_bd24_holes_and_binding_constraints(db):
    result = seed_solver_fixture(db, profile="infeasible", **SPIKE_SEED)
    solved = _solve(db, result)
    slots = list_solver_target_slots(
        db,
        planning_period_id=result.target_period_id,
        shift_group_id=result.shift_group_ids[0],
        organization_id=result.organization_id,
    )
    expected_holes = sorted(
        {
            slot.slot_date.isoformat()
            for slot in slots
            if slot.shift_template is not None
            and slot.shift_template.code == "bd24"
            and not eligible_member_ids_for_slot(db, slot, organization_id=result.organization_id)
        }
    )
    assert len(solved.proposed_assignments) == 82
    assert len(solved.unfilled_slots) == 2
    assert len(solved.proposed_assignments) + len(solved.unfilled_slots) == len(slots)
    hole_dates = []
    for row in solved.unfilled_slots:
        slot = db.get(RosterSlot, int(row["roster_slot_id"]))
        assert slot is not None
        assert slot.shift_template is not None
        assert slot.shift_template.code == "bd24"
        hole_dates.append(slot.slot_date.isoformat())
        codes = set(row["binding_constraints"])
        assert "ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES" in codes
        assert "ROSTER_TEMPLATE_NO_GO_CONFLICT" in codes
    assert sorted(hole_dates) == expected_holes


def test_objective_components_reported_without_nogo(db):
    result = seed_solver_fixture(db, profile="comfortable", **SPIKE_SEED)
    solved = _solve(db, result)
    assert "unfilled" in solved.objective_breakdown
    assert "duty_count" in solved.objective_breakdown
    assert "fairness" in solved.objective_breakdown
    assert "nogo" not in solved.objective_breakdown
    assert "no_go" not in solved.objective_breakdown
    assert "ROSTER_TEMPLATE_NO_GO_CONFLICT" not in solved.objective_breakdown


def test_tier_b_rules_absent_from_model_present_in_post_check(db):
    result = seed_solver_fixture(db, profile="arbzg", **SPIKE_SEED)
    period = db.get(PlanningPeriod, result.target_period_id)
    assert period is not None
    start, end = planning_window(period)
    rules = resolve_active_rules(result.organization_id, start, end, db=db)
    supported = cpsat_supported_codes(rules)
    assert not (TIER_B_CODES & supported)
    solved = _solve(db, result, overwrite_existing=False)
    found = {row["code"] for row in solved.post_check_findings}
    assert found >= TIER_B_CODES
