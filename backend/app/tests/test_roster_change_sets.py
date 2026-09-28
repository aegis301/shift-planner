import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import (
    AuditLog,
    Organization,
    RosterChangeSet,
    RosterSlotAssignment,
    ShiftGroup,
    SolverRun,
    UserShiftGroup,
)
from app.models.base import Base
from app.services import roster_change_sets
from app.services.roster_change_sets import (
    RosterChangeInput,
    RosterChangeSetError,
    apply_roster_change_set,
)
from app.services.solver_fixture import seed_solver_fixture
from app.services.solver_runs import apply_solver_run
from app.tests.test_api import _seed_membership, login


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@example.com", "secret", 1, "admin")
        db.add(ShiftGroup(organization_id=1, code="default_sg", name="Default SG", display_order=0))
        db.commit()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _session():
    return next(app.dependency_overrides[get_db]())


def _two_slots(client: TestClient) -> tuple[int, int, int, int]:
    login(client)
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Set", "email": "set-ada@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post("/api/v1/shift-templates", json={"code": "CSET", "name": "Set", "category": "other"}).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Day",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 2,
            "constraints": [{"type": "no_additional_same_day", "severity": "error"}],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slots = [row for row in roster["slots"] if row["shift_template_id"] == template["id"] and row["slot_date"] == "2026-05-04"]
    assert len(slots) == 2
    return period_id, member, slots[0]["id"], slots[1]["id"]


def test_all_or_nothing_refusal_writes_nothing(client: TestClient):
    period_id, member, first, second = _two_slots(client)
    response = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={
            "mode": "all_or_nothing",
            "label": "Paste 2 cells",
            "items": [
                {"roster_slot_id": first, "team_member_id": member},
                {"roster_slot_id": second, "team_member_id": member},
            ],
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["status"] == "refused"
    assert {item["outcome"] for item in body["items"]} == {"refused"}
    assert all(item["refusal_code"] == "RULE_ERROR" for item in body["items"])
    db = _session()
    try:
        assert db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_([first, second]))) is None
        audits = db.scalars(select(AuditLog).where(AuditLog.entity_type == "roster_change_set")).all()
        assert audits == []
    finally:
        db.close()


def test_best_effort_and_clear_plus_assign(client: TestClient):
    period_id, member, first, second = _two_slots(client)
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    template_id = next(row["shift_template_id"] for row in roster["slots"] if row["id"] == first)
    next_day = next(
        row["id"] for row in roster["slots"] if row["slot_date"] == "2026-05-05" and row["shift_template_id"] == template_id
    )
    other = client.post(
        "/api/v1/team-members",
        json={"first_name": "Bea", "last_name": "Set", "email": "set-bea@example.com", "employment_percentage": 100},
    ).json()["id"]
    mixed = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={
            "mode": "best_effort",
            "items": [
                {"roster_slot_id": first, "team_member_id": member},
                {"roster_slot_id": second, "team_member_id": member},
                {"roster_slot_id": next_day, "team_member_id": other},
            ],
        },
    )
    assert mixed.status_code == 200
    outcomes = {item["roster_slot_id"]: item["outcome"] for item in mixed.json()["items"]}
    assert outcomes[second] == "refused"
    assert outcomes[next_day] == "applied"
    cleared = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={
            "mode": "all_or_nothing",
            "items": [
                {"roster_slot_id": next_day, "team_member_id": None},
                {"roster_slot_id": first, "team_member_id": other},
            ],
        },
    )
    assert cleared.status_code == 200
    assert {item["outcome"] for item in cleared.json()["items"]} == {"applied"}


def test_revert_restores_and_redo_and_changed_since(client: TestClient):
    login(client)
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Cara", "last_name": "Set", "email": "set-cara@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post("/api/v1/shift-templates", json={"code": "CREV", "name": "Rev", "category": "other"}).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Day", "start_day_class": "any", "starts_at": "09:00:00", "ends_at": "17:00:00", "end_day_offset": 0, "required_count": 1},
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 4}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot_id = next(row["id"] for row in roster["slots"] if row["shift_template_id"] == template["id"])
    created = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={"mode": "all_or_nothing", "items": [{"roster_slot_id": slot_id, "team_member_id": member}]},
    )
    assert created.status_code == 200
    reverted = client.post(f"/api/v1/roster-matrix/change-sets/{created.json()['id']}/revert")
    assert reverted.status_code == 200
    assert reverted.json()["status"] == "applied"
    roster_after = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert all(row["team_member_id"] != member for row in roster_after["assignments"] if row["roster_slot_id"] == slot_id)
    redone = client.post(f"/api/v1/roster-matrix/change-sets/{reverted.json()['id']}/revert")
    assert redone.status_code == 200
    roster_redo = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert any(row["roster_slot_id"] == slot_id and row["team_member_id"] == member for row in roster_redo["assignments"])
    other = client.post(
        "/api/v1/team-members",
        json={"first_name": "Dora", "last_name": "Set", "email": "set-dora@example.com", "employment_percentage": 100},
    ).json()["id"]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot_id, "team_member_id": other})
    stale = client.post(f"/api/v1/roster-matrix/change-sets/{redone.json()['id']}/revert")
    assert stale.status_code == 409
    assert any(item["refusal_code"] == "changed_since" for item in stale.json()["items"])
    still = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert any(row["roster_slot_id"] == slot_id and row["team_member_id"] == other for row in still["assignments"])


def test_single_put_records_a_change_set_and_published_group_is_refused(client: TestClient):
    login(client)
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Eve", "last_name": "Set", "email": "set-eve@example.com", "employment_percentage": 100},
    ).json()["id"]
    group = client.post("/api/v1/shift-groups", json={"code": "CEVE", "name": "Eve", "display_order": 2}).json()
    client.put(
        f"/api/v1/shift-groups/{group['id']}/memberships",
        json={"memberships": [{"team_member_id": member, "start_date": "2026-01-01", "end_date": None}]},
    )
    template = client.post("/api/v1/shift-templates", json={"code": "CEVT", "name": "Eve", "category": "other"}).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Day", "start_day_class": "any", "starts_at": "08:00:00", "ends_at": "12:00:00", "end_day_offset": 0, "required_count": 1},
    )
    client.put(f"/api/v1/shift-groups/{group['id']}/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id={group['id']}").json()
    slot_id = next(row["id"] for row in roster["slots"] if row["shift_template_id"] == template["id"])
    saved = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot_id, "team_member_id": member})
    assert saved.status_code == 200
    assert saved.json()["change_set_id"]
    listed = client.get(f"/api/v1/roster-matrix/{period_id}/change-sets?shift_group_id={group['id']}")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == saved.json()["change_set_id"]
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id={group['id']}").status_code == 200
    refused = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets?shift_group_id={group['id']}",
        json={"items": [{"roster_slot_id": slot_id, "team_member_id": member}]},
    )
    assert refused.status_code == 409
    assert refused.json()["items"][0]["refusal_code"] == "PUBLISHED"


def test_planner_cannot_apply_outside_assigned_groups(client: TestClient):
    login(client)
    group = client.post("/api/v1/shift-groups", json={"code": "CPLN", "name": "Planner", "display_order": 3}).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 2}).json()["id"]
    db = _session()
    try:
        planner = _seed_membership(db, "planner-sets@example.com", "secret", 1, "planner")
        db.commit()
        planner_id = planner.id
    finally:
        db.close()
    logged = client.post(
        "/api/v1/auth/login",
        json={"email": "planner-sets@example.com", "password": "secret", "organization_slug": "default"},
    )
    assert logged.status_code == 200
    denied = client.post(f"/api/v1/roster-matrix/{period_id}/change-sets?shift_group_id={group['id']}", json={"items": []})
    assert denied.status_code == 403
    db = _session()
    try:
        db.add(UserShiftGroup(user_id=planner_id, shift_group_id=group["id"]))
        db.commit()
    finally:
        db.close()


def test_hundred_items_build_plan_state_once_and_commit_once(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    commits: list[int] = []
    try:
        result = seed_solver_fixture(db, profile="comfortable", rng_seed=1, year=2026, month=10, history_months=0)
        shift_group_id = result.shift_group_ids[0]
        from app.models import RosterSlot

        base_ids = list(
            db.scalars(select(RosterSlot.id).where(RosterSlot.planning_period_id == result.target_period_id))
        )
        assert base_ids
        slot_ids = [base_ids[index % len(base_ids)] for index in range(100)]
        calls = {"count": 0}
        real = roster_change_sets.build_plan_state

        def wrapped(*args, **kwargs):
            calls["count"] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(roster_change_sets, "build_plan_state", wrapped)
        event.listen(db, "after_commit", lambda _session: commits.append(1))
        apply_roster_change_set(
            db,
            organization_id=result.organization_id,
            planning_period_id=result.target_period_id,
            shift_group_id=shift_group_id,
            items=[RosterChangeInput(roster_slot_id=slot_id, team_member_id=result.member_ids[0]) for slot_id in slot_ids],
            mode="all_or_nothing",
            actor="test",
            source="ui",
            created_by_user_id=None,
            label="100 cells",
        )
        assert calls["count"] == 1
        assert commits == [1]
    finally:
        db.close()
        engine.dispose()


def test_solver_best_effort_applies_the_legal_subset(client: TestClient):
    period_id, member, first, second = _two_slots(client)
    group_id = client.get("/api/v1/shift-groups").json()[0]["id"]
    db = _session()
    try:
        run = SolverRun(
            organization_id=1,
            planning_period_id=period_id,
            shift_group_id=group_id,
            status="succeeded",
            parameters={"overwrite_existing": False},
            proposed_assignments=[
                {"roster_slot_id": first, "team_member_id": member},
                {"roster_slot_id": second, "team_member_id": 999999},
            ],
        )
        db.add(run)
        db.commit()
        run_id = run.id
    finally:
        db.close()
    db = _session()
    try:
        applied, assignments = apply_solver_run(
            db, period_id, run_id, organization_id=1, actor="test", source="rest", mode="best_effort"
        )
        assert applied.applied_at is not None
        assert applied.change_set_id is not None
        assert {row.roster_slot_id for row in assignments} == {first}
    finally:
        db.close()


def test_planner_cannot_edit_a_slot_outside_the_authorized_group(client: TestClient):
    login(client)
    group_a = client.post("/api/v1/shift-groups", json={"code": "CGA", "name": "Group A", "display_order": 4}).json()
    group_b = client.post("/api/v1/shift-groups", json={"code": "CGB", "name": "Group B", "display_order": 5}).json()
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Gus", "last_name": "Set", "email": "set-gus@example.com", "employment_percentage": 100},
    ).json()["id"]
    client.put(
        f"/api/v1/shift-groups/{group_b['id']}/memberships",
        json={"memberships": [{"team_member_id": member, "start_date": "2026-01-01", "end_date": None}]},
    )
    template = client.post("/api/v1/shift-templates", json={"code": "CGBS", "name": "Group B only", "category": "other"}).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Day", "start_day_class": "any", "starts_at": "08:00:00", "ends_at": "12:00:00", "end_day_offset": 0, "required_count": 1},
    )
    client.put(f"/api/v1/shift-groups/{group_b['id']}/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id={group_b['id']}").json()
    slot_id = next(row["id"] for row in roster["slots"] if row["shift_template_id"] == template["id"])
    db = _session()
    try:
        planner = _seed_membership(db, "planner-scope@example.com", "secret", 1, "planner")
        db.flush()
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=group_a["id"]))
        db.commit()
    finally:
        db.close()
    logged = client.post(
        "/api/v1/auth/login",
        json={"email": "planner-scope@example.com", "password": "secret", "organization_slug": "default"},
    )
    assert logged.status_code == 200
    refused = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets?shift_group_id={group_a['id']}",
        json={"mode": "all_or_nothing", "items": [{"roster_slot_id": slot_id, "team_member_id": member}]},
    )
    assert refused.status_code == 409
    assert refused.json()["items"][0]["refusal_code"] == "SLOT_OUTSIDE_GROUP"
    db = _session()
    try:
        assert db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id)) is None
    finally:
        db.close()


def test_clearing_or_reassigning_coupled_partner_is_refused(client: TestClient):
    login(client)
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Hex", "last_name": "Set", "email": "set-hex@example.com", "employment_percentage": 100},
    ).json()["id"]
    other = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ivy", "last_name": "Set", "email": "set-ivy@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post("/api/v1/shift-templates", json={"code": "CCPL", "name": "Couple", "category": "other"}).json()
    early = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Early", "start_day_class": "any", "starts_at": "08:00:00", "ends_at": "12:00:00", "end_day_offset": 0, "required_count": 1},
    ).json()
    late = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Late", "start_day_class": "any", "starts_at": "18:00:00", "ends_at": "22:00:00", "end_day_offset": 0, "required_count": 1},
    ).json()
    assert (
        client.patch(
            f"/api/v1/shift-templates/variants/{early['id']}",
            json={
                "constraints": [
                    {
                        "type": "requires_coupled_shift",
                        "severity": "error",
                        "paired_shift_variant_id": late["id"],
                        "partner_day_offset": 1,
                    }
                ]
            },
        ).status_code
        == 200
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    source = next(row["id"] for row in roster["slots"] if row["slot_date"] == "2026-09-10" and row["shift_variant_id"] == early["id"])
    partner = next(row["id"] for row in roster["slots"] if row["slot_date"] == "2026-09-11" and row["shift_variant_id"] == late["id"])
    elsewhere = next(row["id"] for row in roster["slots"] if row["slot_date"] == "2026-09-20" and row["shift_variant_id"] == late["id"])
    assert client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": partner, "team_member_id": member}).status_code == 200
    assert client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": source, "team_member_id": member}).status_code == 200
    blocked = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={
            "mode": "all_or_nothing",
            "items": [
                {"roster_slot_id": partner, "team_member_id": None},
                {"roster_slot_id": elsewhere, "team_member_id": other},
            ],
        },
    )
    assert blocked.status_code == 409
    by_slot = {item["roster_slot_id"]: item for item in blocked.json()["items"]}
    assert by_slot[partner]["refusal_code"] == "RULE_ERROR"
    assert any(finding["code"] == "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED" for finding in by_slot[partner]["findings"])
    assert by_slot[elsewhere]["refusal_code"] == "SET_REFUSED"
    kept = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assignees = {row["roster_slot_id"]: row["team_member_id"] for row in kept["assignments"]}
    assert assignees[source] == member
    assert assignees[partner] == member
    assert elsewhere not in assignees
    partial = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={
            "mode": "best_effort",
            "items": [
                {"roster_slot_id": partner, "team_member_id": None},
                {"roster_slot_id": elsewhere, "team_member_id": other},
            ],
        },
    )
    assert partial.status_code == 200
    partial_by_slot = {item["roster_slot_id"]: item["outcome"] for item in partial.json()["items"]}
    assert partial_by_slot[partner] == "refused"
    assert partial_by_slot[elsewhere] == "applied"
    reassigned = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={"mode": "all_or_nothing", "items": [{"roster_slot_id": partner, "team_member_id": other}]},
    )
    assert reassigned.status_code == 409
    assert reassigned.json()["items"][0]["refusal_code"] == "RULE_ERROR"
    final = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    final_assignees = {row["roster_slot_id"]: row["team_member_id"] for row in final["assignments"]}
    assert final_assignees[partner] == member
    assert final_assignees[source] == member


def test_revert_rechecks_the_assignment_under_the_slot_lock(client: TestClient, monkeypatch):
    login(client)
    member = client.post(
        "/api/v1/team-members",
        json={"first_name": "Joy", "last_name": "Set", "email": "set-joy@example.com", "employment_percentage": 100},
    ).json()["id"]
    other = client.post(
        "/api/v1/team-members",
        json={"first_name": "Kim", "last_name": "Set", "email": "set-kim@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post("/api/v1/shift-templates", json={"code": "CLCK", "name": "Lock", "category": "other"}).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Day", "start_day_class": "any", "starts_at": "09:00:00", "ends_at": "17:00:00", "end_day_offset": 0, "required_count": 1},
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 11}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot_id = next(row["id"] for row in roster["slots"] if row["shift_template_id"] == template["id"])
    created = client.post(
        f"/api/v1/roster-matrix/{period_id}/change-sets",
        json={"items": [{"roster_slot_id": slot_id, "team_member_id": member}]},
    )
    assert created.status_code == 200
    real_lock = roster_change_sets.lock_roster_slots_for_assignment

    def lock_and_replace(db, slot_ids):
        real_lock(db, slot_ids)
        if slot_id not in slot_ids:
            return
        assignment = db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id))
        if assignment is not None and assignment.team_member_id != other:
            assignment.team_member_id = other
            db.flush()

    monkeypatch.setattr(roster_change_sets, "lock_roster_slots_for_assignment", lock_and_replace)
    stale = client.post(f"/api/v1/roster-matrix/change-sets/{created.json()['id']}/revert")
    assert stale.status_code == 409
    assert any(item["refusal_code"] == "changed_since" for item in stale.json()["items"])
    db = _session()
    try:
        kept = db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id))
        assert kept is not None
        assert kept.team_member_id == other
    finally:
        db.close()


def test_unknown_mode_is_rejected_before_a_row_is_stored(client: TestClient):
    login(client)
    rejected = client.post("/api/v1/roster-matrix/1/change-sets", json={"mode": "sideways", "items": []})
    assert rejected.status_code == 422
    db = _session()
    try:
        with pytest.raises(RosterChangeSetError) as exc:
            apply_roster_change_set(
                db,
                organization_id=1,
                planning_period_id=1,
                shift_group_id=None,
                items=[],
                mode="sideways",
                actor="test",
                source="mcp",
                created_by_user_id=None,
            )
        assert exc.value.code == "INVALID_MODE"
        assert db.scalar(select(func.count()).select_from(RosterChangeSet)) == 0
    finally:
        db.rollback()
        db.close()
