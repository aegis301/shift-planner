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


def _seed_period_with_assignment(client: TestClient) -> tuple[int, int]:
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Version",
            "last_name": "Member",
            "email": "version-member@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "VER", "name": "Versiondienst", "category": "other"},
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
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    slot = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"][0]
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments?shift_group_id=1",
            json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
        ).status_code
        == 200
    )
    return period_id, team_member_id


def test_draft_to_preliminary_creates_version_0_1(client: TestClient):
    login(client)
    period_id, _ = _seed_period_with_assignment(client)
    response = client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1")
    assert response.status_code == 200
    body = response.json()
    assert body["working_major_version"] == 0
    assert body["working_minor_version"] == 1
    versions = client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()
    assert len(versions["versions"]) == 1
    assert versions["versions"][0]["major_version"] == 0
    assert versions["versions"][0]["minor_version"] == 1


def test_first_publish_creates_version_1_0_and_blocks_edits(client: TestClient):
    login(client)
    period_id, team_member_id = _seed_period_with_assignment(client)
    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200
    publish = client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1")
    assert publish.status_code == 200
    assert publish.json()["working_major_version"] == 1
    assert publish.json()["working_minor_version"] == 0
    versions = client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()
    published = [row for row in versions["versions"] if row["lifecycle_phase"] == "published"]
    assert len(published) == 1
    assert published[0]["major_version"] == 1
    slot = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"][0]
    denied = client.put(
        "/api/v1/roster-matrix/assignments?shift_group_id=1",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
    )
    assert denied.status_code == 403


def test_reopen_from_published_bumps_working_version(client: TestClient):
    login(client)
    period_id, _ = _seed_period_with_assignment(client)
    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    reopen = client.post(
        f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1",
        json={"is_major_update": False},
    )
    assert reopen.status_code == 200
    assert reopen.json()["working_major_version"] == 1
    assert reopen.json()["working_minor_version"] == 1


def test_manual_save_in_preliminary_creates_snapshot(client: TestClient):
    login(client)
    period_id, _ = _seed_period_with_assignment(client)
    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200
    save = client.post(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1", json={})
    assert save.status_code == 200
    assert save.json()["major_version"] == 0
    assert save.json()["minor_version"] == 2


def test_version_roster_export(client: TestClient):
    login(client)
    period_id, _ = _seed_period_with_assignment(client)
    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200
    version_id = client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()["versions"][0]["id"]
    csv = client.get(
        f"/api/v1/planning-periods/{period_id}/versions/{version_id}/export/roster-matrix.csv"
    )
    assert csv.status_code == 200
    assert "team_member" in csv.text
