from datetime import date

import pytest
from fastapi.testclient import TestClient

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


def _create_daily_template(client: TestClient, code: str, *, required_count: int = 1) -> tuple[dict, dict]:
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": code, "name": code, "category": "other"},
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Daily",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "required_count": required_count,
        },
    ).json()
    return template, variant


def test_sync_roster_adds_slots_preserves_existing_assignment(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Sync",
            "last_name": "Keep",
            "email": "sync-keep@example.com",
            "employment_percentage": 100,
        },
    ).json()["id"]
    template, variant = _create_daily_template(client, "SYNCK", required_count=1)
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert len(roster["slots"]) == 30
    first_slot = roster["slots"][0]
    client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": first_slot["id"], "team_member_id": team_member_id},
    )

    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={"required_count": 2},
    )
    sync = client.post(f"/api/v1/planning-periods/{period_id}/sync-roster")
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["sync"]["added_count"] == 30
    assert body["sync"]["removed_count"] == 0
    assert len(body["matrix"]["slots"]) == 60
    assert len(body["matrix"]["assignments"]) == 1
    assert body["matrix"]["assignments"][0]["roster_slot_id"] == first_slot["id"]


def test_sync_roster_removes_weekday_slots_and_clears_assignments(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Sync",
            "last_name": "Remove",
            "email": "sync-remove@example.com",
            "employment_percentage": 100,
        },
    ).json()["id"]
    template, variant = _create_daily_template(client, "SYNCR")
    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={
            "start_day_class": "any",
            "start_weekdays": ["mon", "tue", "wed", "thu", "fri"],
            "include_holidays": False,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    friday_slots = [slot for slot in roster["slots"] if date.fromisoformat(slot["slot_date"]).weekday() == 4]
    assert friday_slots
    client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": friday_slots[0]["id"], "team_member_id": team_member_id},
    )

    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={"start_weekdays": ["mon", "tue", "wed", "thu"]},
    )
    sync = client.post(f"/api/v1/planning-periods/{period_id}/sync-roster")
    assert sync.status_code == 200
    body = sync.json()
    assert body["sync"]["removed_count"] >= 1
    assert body["sync"]["assignments_cleared_count"] >= 1
    remaining_fridays = [
        slot for slot in body["matrix"]["slots"] if date.fromisoformat(slot["slot_date"]).weekday() == 4
    ]
    assert not remaining_fridays


def test_sync_roster_blocked_when_shift_group_published(client: TestClient):
    login(client)
    _create_daily_template(client, "SYNCP")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1")
    client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1")
    sync = client.post(f"/api/v1/planning-periods/{period_id}/sync-roster?shift_group_id=1")
    assert sync.status_code == 409
    assert sync.json()["detail"]["code"] == "ROSTER_SYNC_PUBLISHED"


def test_sync_roster_regenerate_still_clears_all_assignments(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Regen",
            "last_name": "Clear",
            "email": "regen-clear@example.com",
            "employment_percentage": 100,
        },
    ).json()["id"]
    _create_daily_template(client, "REGEN")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 11}).json()["id"]
    slot = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"][0]
    client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
    )
    regenerated = client.post(f"/api/v1/planning-periods/{period_id}/regenerate-roster")
    assert regenerated.status_code == 200
    assert regenerated.json()["assignments"] == []
