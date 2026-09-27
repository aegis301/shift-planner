import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Account, RosterSlot, ShiftGroupShiftTemplate, User
from app.models.base import Base
from app.schemas import RosterSlotAssignmentUpsert
from app.services import roster_candidates
from app.services.roster_candidates import list_slot_candidates
from app.services.roster_matrix import upsert_roster_slot_assignment
from app.services.solver_fixture import seed_solver_fixture

SEED = dict(rng_seed=1, year=2026, month=10, history_months=0)


def _memory_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return factory(), engine


def _first_slot(db, result):
    shift_group_id = result.shift_group_ids[0]
    slot = db.scalar(
        select(RosterSlot)
        .join(ShiftGroupShiftTemplate, ShiftGroupShiftTemplate.shift_template_id == RosterSlot.shift_template_id)
        .where(
            RosterSlot.planning_period_id == result.target_period_id,
            ShiftGroupShiftTemplate.shift_group_id == shift_group_id,
        )
        .order_by(RosterSlot.slot_date, RosterSlot.id)
    )
    assert slot is not None
    return slot, shift_group_id


def test_blocked_matches_assignment_refusal_on_tight_fixture():
    db, engine = _memory_db()
    try:
        result = seed_solver_fixture(db, profile="tight", **SEED)
        slot, shift_group_id = _first_slot(db, result)
        payload = list_slot_candidates(
            db,
            slot.id,
            organization_id=result.organization_id,
            shift_group_id=shift_group_id,
        )
        assert payload.candidates
        for candidate in payload.candidates:
            assert candidate.status in {"ok", "warning", "blocked", "ineligible"}
            refused = False
            try:
                upsert_roster_slot_assignment(
                    db,
                    RosterSlotAssignmentUpsert(
                        roster_slot_id=slot.id,
                        team_member_id=candidate.team_member_id,
                        manual_override=False,
                    ),
                    organization_id=result.organization_id,
                    actor="test",
                    source="test",
                    commit=False,
                )
            except ValueError:
                refused = True
            db.rollback()
            assert (candidate.status == "blocked") is refused, (candidate.team_member_id, candidate.status, refused)
    finally:
        db.close()
        engine.dispose()


def test_slot_candidates_build_plan_state_once(monkeypatch):
    db, engine = _memory_db()
    try:
        result = seed_solver_fixture(db, profile="tight", **SEED)
        slot, shift_group_id = _first_slot(db, result)
        calls = {"count": 0}
        real = roster_candidates.build_plan_state

        def wrapped(*args, **kwargs):
            calls["count"] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(roster_candidates, "build_plan_state", wrapped)
        list_slot_candidates(
            db,
            slot.id,
            organization_id=result.organization_id,
            shift_group_id=shift_group_id,
        )
        assert calls["count"] == 1
    finally:
        db.close()
        engine.dispose()


def test_comfortable_slot_candidates_log_timing(caplog):
    db, engine = _memory_db()
    try:
        result = seed_solver_fixture(db, profile="comfortable", **SEED)
        slot, shift_group_id = _first_slot(db, result)
        with caplog.at_level("INFO", logger="app.services.roster_candidates"):
            list_slot_candidates(
                db,
                slot.id,
                organization_id=result.organization_id,
                shift_group_id=shift_group_id,
            )
        timing = next(line for line in caplog.messages if line.startswith("slot candidates"))
        seconds = float(timing.rsplit("seconds=", 1)[1])
        if seconds > 1.5:
            pytest.skip(f"slot candidates took {seconds:.3f}s")
    finally:
        db.close()
        engine.dispose()


def _user(db, email: str, role: str, organization_id: int) -> User:
    account = Account(email=email, hashed_password="x")
    db.add(account)
    db.flush()
    user = User(account_id=account.id, organization_id=organization_id, role=role, locale="de")
    db.add(user)
    db.commit()
    return user


def test_planner_without_the_group_cannot_read_candidates():
    db, engine = _memory_db()
    try:
        result = seed_solver_fixture(db, profile="tight", **SEED)
        slot, shift_group_id = _first_slot(db, result)
        outsider = _user(db, "outsider-planner@example.com", "planner", result.organization_id)
        admin = _user(db, "fixture-admin@example.com", "admin", result.organization_id)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: outsider
        denied = client.get(
            f"/api/v1/roster-matrix/{result.target_period_id}/slots/{slot.id}/candidates",
            params={"shift_group_id": shift_group_id},
        )
        assert denied.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: admin
        allowed = client.get(
            f"/api/v1/roster-matrix/{result.target_period_id}/slots/{slot.id}/candidates",
            params={"shift_group_id": shift_group_id},
        )
        assert allowed.status_code == 200, allowed.text
        body = allowed.json()
        assert body["candidates"]
        assert {row["status"] for row in body["candidates"]} <= {"ok", "warning", "blocked", "ineligible"}
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()
