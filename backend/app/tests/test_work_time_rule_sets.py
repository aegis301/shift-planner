from fastapi.testclient import TestClient

pytest_plugins = ("app.tests.test_api",)


def login(client: TestClient, email: str = "admin@example.com", password: str = "secret") -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "organization_slug": "default"},
    ).status_code == 200


def consecutive_days_rule(days: int = 6) -> dict:
    return {
        "type": "max_consecutive_work_days",
        "severity": "warning",
        "source_note": "ArbZG",
        "days": days,
    }


def create_rule_set(client: TestClient, name: str = "ArbZG", days: int = 6, is_active: bool | None = None) -> dict:
    payload: dict = {"name": name, "rules": [consecutive_days_rule(days)]}
    if is_active is not None:
        payload["is_active"] = is_active
    response = client.post("/api/v1/work-time-rule-sets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _seed_period(client: TestClient) -> int:
    member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Rule",
            "last_name": "Member",
            "email": "rule-member@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "WR", "name": "Regelndienst", "category": "other"},
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
    client.put("/api/v1/shift-groups/1/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 11}).json()["id"]
    slot = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"][0]
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments?shift_group_id=1",
            json={"roster_slot_id": slot["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    return period_id


def test_edit_referenced_set_creates_new_version_and_pins_plan(client: TestClient):
    login(client)
    created = create_rule_set(client)
    assert created["version"] == 1
    assert created["is_active"] is True
    period_id = _seed_period(client)
    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    versions = client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()["versions"]
    published = next(row for row in versions if row["lifecycle_phase"] == "published")
    assert published["work_time_rule_set_version_id"] == created["id"]
    patched = client.patch(
        f"/api/v1/work-time-rule-sets/{created['id']}",
        json={"rules": [consecutive_days_rule(7)]},
    )
    assert patched.status_code == 200
    assert patched.json()["id"] != created["id"]
    assert patched.json()["version"] == 2
    assert patched.json()["is_active"] is True
    assert patched.json()["rules"][0]["days"] == 7
    original = client.get(f"/api/v1/work-time-rule-sets/{created['id']}").json()
    assert original["is_active"] is False
    assert original["rules"][0]["days"] == 6
    versions_after = client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()["versions"]
    published_after = next(row for row in versions_after if row["lifecycle_phase"] == "published")
    assert published_after["work_time_rule_set_version_id"] == created["id"]


def test_only_one_active_set_and_explicit_switch(client: TestClient):
    login(client)
    first = create_rule_set(client, name="ArbZG")
    second = create_rule_set(client, name="TV-Ärzte TdL", is_active=False)
    assert first["is_active"] is True
    assert second["is_active"] is False
    switched = client.patch(f"/api/v1/work-time-rule-sets/{second['id']}", json={"is_active": True})
    assert switched.status_code == 200
    assert switched.json()["is_active"] is True
    assert switched.json()["id"] == second["id"]
    rows = client.get("/api/v1/work-time-rule-sets").json()
    active = [row for row in rows if row["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == second["id"]


def test_planner_can_read_but_not_write(planner_client: TestClient):
    login(planner_client)
    created = create_rule_set(planner_client)
    login(planner_client, "planner@example.com", "plannersecret")
    listed = planner_client.get("/api/v1/work-time-rule-sets")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created["id"]
    denied = planner_client.post(
        "/api/v1/work-time-rule-sets",
        json={"name": "Nope", "rules": [consecutive_days_rule()]},
    )
    assert denied.status_code == 403


def test_admin_only_writes(client: TestClient, team_member_client: TestClient):
    login(client)
    create_rule_set(client)
    login(team_member_client, "doc@example.com", "docsecret")
    denied_read = team_member_client.get("/api/v1/work-time-rule-sets")
    assert denied_read.status_code == 403
    denied_write = team_member_client.post(
        "/api/v1/work-time-rule-sets",
        json={"name": "Nope", "rules": [consecutive_days_rule()]},
    )
    assert denied_write.status_code == 403
    login(client)
    listed = client.get("/api/v1/work-time-rule-sets")
    assert listed.status_code == 200
    assert listed.json()


def test_rule_config_is_removed():
    from app import models
    from app.models import WorkTimeRuleSet

    assert not hasattr(models, "RuleConfig")
    assert WorkTimeRuleSet.__tablename__ == "work_time_rule_sets"
