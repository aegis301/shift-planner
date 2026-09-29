import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import Organization, ShiftGroup
from app.models.base import Base
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


def _member(client: TestClient, email: str) -> int:
    return client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": email, "employment_percentage": 100},
    ).json()["id"]


def _template(client: TestClient, code: str) -> dict:
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": code, "name": "Duty", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Day",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 2,
        },
    )
    return template


def test_single_cell_assignment_messages_stay_stable(client: TestClient):
    login(client)
    member_id = _member(client, "golden-ok@example.com")
    template = _template(client, "GOLD")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(row for row in roster["slots"] if row["shift_template_id"] == template["id"])

    saved = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": member_id},
    )
    assert saved.status_code == 200
    assert saved.json()["team_member_id"] == member_id
    assert saved.json()["roster_slot_id"] == slot["id"]

    cleared = client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] is True

    group = client.post("/api/v1/shift-groups", json={"code": "GOLDG", "name": "Gold", "display_order": 0}).json()
    insider = _member(client, "golden-in@example.com")
    outsider = _member(client, "golden-out@example.com")
    client.put(
        f"/api/v1/shift-groups/{group['id']}/memberships",
        json={"memberships": [{"team_member_id": insider, "start_date": "2026-01-01", "end_date": None}]},
    )
    linked = _template(client, "GOL2")
    client.put(f"/api/v1/shift-groups/{group['id']}/shift-templates", json={"shift_template_ids": [linked["id"]]})
    scoped_period = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]
    late = _member(client, "golden-late@example.com")
    client.put(
        f"/api/v1/shift-groups/{group['id']}/memberships",
        json={
            "memberships": [
                {"team_member_id": insider, "start_date": "2026-01-01", "end_date": None},
                {"team_member_id": late, "start_date": "2026-01-01", "end_date": None},
            ]
        },
    )
    scoped = client.get(f"/api/v1/roster-matrix/{scoped_period}").json()
    scoped_slot = next(row for row in scoped["slots"] if row["shift_template_id"] == linked["id"])
    not_roster = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": scoped_slot["id"], "team_member_id": late},
    )
    assert not_roster.status_code == 400
    assert not_roster.json()["detail"] == "Team member is not on the roster for this planning period and shift group"
    cannot_cover = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": scoped_slot["id"], "team_member_id": outsider},
    )
    assert cannot_cover.status_code == 400
    assert cannot_cover.json()["detail"] == "Team member is not a member of a shift group that covers this template"

    client.put(
        f"/api/v1/matrix/{scoped_period}/shift-intents/bulk",
        json={
            "intents": [
                {
                    "team_member_id": insider,
                    "cell_date": scoped_slot["slot_date"],
                    "shift_group_id": group["id"],
                    "shift_template_id": linked["id"],
                    "kind": "no_go",
                }
            ]
        },
    )
    no_go = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": scoped_slot["id"], "team_member_id": insider},
    )
    assert no_go.status_code == 400
    assert no_go.json()["detail"] == "Team member marked this shift template as a no-go on that day"

    blocked_template = client.post(
        "/api/v1/shift-templates",
        json={"code": "GOLB", "name": "Blocked", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{blocked_template['id']}/variants",
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
    block_period = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    block_member = _member(client, "golden-block@example.com")
    block_roster = client.get(f"/api/v1/roster-matrix/{block_period}").json()
    block_slots = [
        row
        for row in block_roster["slots"]
        if row["shift_template_id"] == blocked_template["id"] and row["slot_date"] == "2026-07-01"
    ]
    assert len(block_slots) == 2
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": block_slots[0]["id"], "team_member_id": block_member},
        ).status_code
        == 200
    )
    blocked = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": block_slots[1]["id"], "team_member_id": block_member},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "Constraint violation: no additional shift assignments allowed on this day."

    publish_group = client.post("/api/v1/shift-groups", json={"code": "GOLDP", "name": "Published", "display_order": 1}).json()
    publish_member = _member(client, "golden-pub@example.com")
    client.put(
        f"/api/v1/shift-groups/{publish_group['id']}/memberships",
        json={"memberships": [{"team_member_id": publish_member, "start_date": "2026-01-01", "end_date": None}]},
    )
    publish_template = _template(client, "GOLP")
    client.put(
        f"/api/v1/shift-groups/{publish_group['id']}/shift-templates",
        json={"shift_template_ids": [publish_template["id"]]},
    )
    publish_period = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 6}).json()["id"]
    published = client.post(
        f"/api/v1/planning-periods/{publish_period}/publish?shift_group_id={publish_group['id']}"
    )
    assert published.status_code == 200
    publish_roster = client.get(f"/api/v1/roster-matrix/{publish_period}").json()
    publish_slot = next(row for row in publish_roster["slots"] if row["shift_template_id"] == publish_template["id"])
    denied = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": publish_slot["id"], "team_member_id": publish_member},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Roster assignments are read-only while this shift group's plan is published"
