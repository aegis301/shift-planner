import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import Organization, SolverRun
from app.models.base import Base
from app.services.solver import SolverSolveResult
from app.services.solver_runs import (
    FAILURE_TIME_BUDGET_EXCEEDED,
    claim_next_queued_run,
    process_one_queued_run,
)

pytest_plugins = ("app.tests.test_api",)


def login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "secret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def _process_queued() -> SolverRun | None:
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        return process_one_queued_run(db)
    finally:
        db.close()


def _seed_solver_month(client: TestClient, *, month: int = 3, code: str = "SOLV") -> tuple[int, int, dict]:
    team_member = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Solver",
            "last_name": "Member",
            "email": f"solver-{code.lower()}-{month}@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [],
        },
    ).json()
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": code, "name": code, "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "required_count": 1,
        },
    )
    client.put(
        "/api/v1/shift-groups/1/shift-templates",
        json={"shift_template_ids": [template["id"]]},
    )
    memberships = client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {
                    "team_member_id": team_member["id"],
                    "start_date": "2026-01-01",
                    "end_date": None,
                }
            ]
        },
    )
    assert memberships.status_code == 200, memberships.text
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": month}).json()["id"]
    slot = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"][0]
    return period_id, team_member["id"], slot


def test_queue_solver_run_returns_immediately_with_run_id(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=3, code="QRUN")
    started = time.monotonic()
    response = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1, "random_seed": 7},
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert isinstance(body["id"], int)
    assert body["parameters"]["num_search_workers"] == 1
    assert body["parameters"]["random_seed"] == 7
    assert body["parameters"]["time_budget_seconds"] == 30
    assert elapsed < 2.0
    listed = client.get(f"/api/v1/planning-periods/{period_id}/solver-runs?shift_group_id=1")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]
    fetched = client.get(f"/api/v1/planning-periods/{period_id}/solver-runs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "queued"


def test_solver_run_refused_when_shift_group_published(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=4, code="PUBL")
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    response = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SOLVER_RUN_PUBLISHED"


def test_cancel_queued_run(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=5, code="CANC")
    queued = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1},
    ).json()
    cancelled = client.post(f"/api/v1/planning-periods/{period_id}/solver-runs/{queued['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert _process_queued() is None
    again = client.post(f"/api/v1/planning-periods/{period_id}/solver-runs/{queued['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "SOLVER_RUN_NOT_CANCELLABLE"


def test_completed_run_exposes_parameters_and_objective_breakdown(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=6, code="OBJB")
    queued = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1, "random_seed": 11, "num_search_workers": 1},
    ).json()
    processed = _process_queued()
    assert processed is not None
    body = client.get(f"/api/v1/planning-periods/{period_id}/solver-runs/{queued['id']}").json()
    assert body["status"] == "succeeded"
    assert body["parameters"]["num_search_workers"] == 1
    assert body["parameters"]["random_seed"] == 11
    assert "unfilled" in body["objective_breakdown"]
    assert isinstance(body["proposed_assignments"], list)
    assert isinstance(body["unfilled_slots"], list)
    assert "nogo" not in body["objective_breakdown"]


def test_reproducible_parameters_are_stored_and_stub_matches(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=7, code="SEED")
    first = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1, "random_seed": 1, "num_search_workers": 1},
    ).json()
    second = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1, "random_seed": 1, "num_search_workers": 1},
    ).json()
    assert first["parameters"]["random_seed"] == 1
    assert first["parameters"]["num_search_workers"] == 1
    assert second["parameters"]["random_seed"] == 1
    first_done = _process_queued()
    second_done = _process_queued()
    assert first_done is not None and second_done is not None
    a = client.get(f"/api/v1/planning-periods/{period_id}/solver-runs/{first['id']}").json()
    b = client.get(f"/api/v1/planning-periods/{period_id}/solver-runs/{second['id']}").json()
    assert a["unfilled_slots"] == b["unfilled_slots"]
    assert a["proposed_assignments"] == b["proposed_assignments"]
    assert a["objective_breakdown"] == b["objective_breakdown"]


def test_apply_writes_assignments_identical_in_shape_to_manual(client: TestClient, monkeypatch):
    login(client)
    period_id, team_member_id, slot = _seed_solver_month(client, month=8, code="APLY")

    def fake_solve(db, run, *, is_cancelled, deadline):
        return SolverSolveResult(
            proposed_assignments=[
                {
                    "roster_slot_id": slot["id"],
                    "team_member_id": team_member_id,
                    "comment": None,
                    "manual_override": False,
                }
            ],
            unfilled_slots=[],
            objective_breakdown={"unfilled": 0},
            post_check_findings=[],
        )

    monkeypatch.setattr("app.services.solver_runs.solve_roster", fake_solve)
    queued = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1, "overwrite_existing": True},
    ).json()
    assert _process_queued() is not None
    applied = client.post(f"/api/v1/planning-periods/{period_id}/solver-runs/{queued['id']}/apply")
    assert applied.status_code == 200, applied.text
    solver_assignment = applied.json()["assignments"][0]
    assert solver_assignment["roster_slot_id"] == slot["id"]
    assert solver_assignment["team_member_id"] == team_member_id
    assert solver_assignment["source"] == "solver"
    assert {"id", "comment", "manual_override", "created_at", "updated_at"} <= solver_assignment.keys()

    cleared = client.post(
        "/api/v1/roster-matrix/assignments/clear?shift_group_id=1",
        json={"roster_slot_id": slot["id"]},
    )
    assert cleared.status_code == 200
    manual = client.put(
        "/api/v1/roster-matrix/assignments?shift_group_id=1",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
    )
    assert manual.status_code == 200, manual.text
    manual_assignment = manual.json()
    for key in ("roster_slot_id", "team_member_id", "comment", "manual_override"):
        assert solver_assignment[key] == manual_assignment[key]
    assert set(solver_assignment) == set(manual_assignment)


def test_apply_refused_when_shift_group_published(client: TestClient):
    login(client)
    period_id, _, _ = _seed_solver_month(client, month=9, code="APUB")
    queued = client.post(
        f"/api/v1/planning-periods/{period_id}/solver-runs",
        json={"shift_group_id": 1},
    ).json()
    assert _process_queued() is not None
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    applied = client.post(f"/api/v1/planning-periods/{period_id}/solver-runs/{queued['id']}/apply")
    assert applied.status_code == 409
    assert applied.json()["detail"]["code"] == "SOLVER_RUN_PUBLISHED"


def test_run_exceeding_budget_ends_failed(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team", solver_time_budget_ceiling_seconds=120))
        db.commit()

    def slow_solve(db, run, *, is_cancelled, deadline):
        time.sleep(0.05)
        return SolverSolveResult()

    monkeypatch.setattr("app.services.solver_runs.solve_roster", slow_solve)
    with TestingSessionLocal() as db:
        from app.models import PlanningPeriod, ShiftGroup

        db.add(ShiftGroup(id=1, organization_id=1, code="g", name="G"))
        db.add(PlanningPeriod(id=1, organization_id=1, year=2026, month=1))
        db.commit()
        run = SolverRun(
            organization_id=1,
            planning_period_id=1,
            shift_group_id=1,
            status="queued",
            parameters={
                "time_budget_seconds": 0,
                "num_search_workers": 1,
                "random_seed": 1,
                "overwrite_existing": False,
            },
            proposed_assignments=[],
            objective_breakdown={},
            unfilled_slots=[],
            post_check_findings=[],
            queued_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        run_id = run.id

    with TestingSessionLocal() as db:
        processed = process_one_queued_run(db)
        assert processed is not None
        assert processed.id == run_id
        assert processed.status == "failed"
        assert processed.failure_reason == FAILURE_TIME_BUDGET_EXCEEDED


def test_cancel_requested_running_run_ends_cancelled(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        from app.models import PlanningPeriod, ShiftGroup

        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.add(ShiftGroup(id=1, organization_id=1, code="g", name="G"))
        db.add(PlanningPeriod(id=1, organization_id=1, year=2026, month=1))
        db.commit()
        run = SolverRun(
            organization_id=1,
            planning_period_id=1,
            shift_group_id=1,
            status="queued",
            parameters={
                "time_budget_seconds": 30,
                "num_search_workers": 1,
                "random_seed": 1,
                "overwrite_existing": False,
            },
            proposed_assignments=[],
            objective_breakdown={},
            unfilled_slots=[],
            post_check_findings=[],
            queued_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        run_id = run.id

    def canceling_solve(db, run, *, is_cancelled, deadline):
        run.cancel_requested = True
        db.commit()
        return SolverSolveResult()

    monkeypatch.setattr("app.services.solver_runs.solve_roster", canceling_solve)
    with TestingSessionLocal() as db:
        processed = process_one_queued_run(db)
        assert processed is not None
        assert processed.id == run_id
        assert processed.status == "cancelled"


def test_two_workers_cannot_claim_the_same_run():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        from app.models import PlanningPeriod, ShiftGroup

        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.add(ShiftGroup(id=1, organization_id=1, code="g", name="G"))
        db.add(PlanningPeriod(id=1, organization_id=1, year=2026, month=1))
        db.add(
            SolverRun(
                organization_id=1,
                planning_period_id=1,
                shift_group_id=1,
                status="queued",
                parameters={
                    "time_budget_seconds": 30,
                    "num_search_workers": 1,
                    "random_seed": 1,
                    "overwrite_existing": False,
                },
                proposed_assignments=[],
                objective_breakdown={},
                unfilled_slots=[],
                post_check_findings=[],
                queued_at=datetime.now(UTC),
            )
        )
        db.commit()
        queued_id = db.scalar(select(SolverRun.id))

    with TestingSessionLocal() as db:
        first = claim_next_queued_run(db)
        second = claim_next_queued_run(db)
        assert first is not None
        assert first.id == queued_id
        assert first.status == "running"
        assert second is None
        leftover = db.get(SolverRun, queued_id)
        assert leftover is not None
        assert leftover.status == "running"
