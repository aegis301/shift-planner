from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, ShiftGroup, TeamMember, TimeEntry, User
from app.models.base import Base
from app.schemas import TimeEntryCreate


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    return user


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@example.com", "secret", 1, "admin")
        portal = _seed_membership(db, "doc@example.com", "docsecret", 1, "team_member")
        db.flush()
        db.add(
            TeamMember(
                organization_id=1,
                first_name="Seeded",
                last_name="Member",
                email="docperson@example.com",
                user_id=portal.id,
            )
        )
        db.add(ShiftGroup(organization_id=1, code="default_sg", name="Default SG", display_order=0))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, engine
    app.dependency_overrides.clear()


def login_admin(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    ).status_code == 200


def login_team_member(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "doc@example.com", "password": "docsecret", "organization_slug": "default"},
    ).status_code == 200


def set_shift_group_membership(client: TestClient, *, team_member_id: int) -> None:
    response = client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {"team_member_id": team_member_id, "start_date": "2026-01-01", "end_date": None}
            ]
        },
    )
    assert response.status_code == 200


def create_member(client: TestClient, email: str) -> int:
    response = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Pat",
            "last_name": email.split("@")[0],
            "email": email,
            "employment_percentage": 100,
        },
    )
    assert response.status_code == 200
    member_id = response.json()["id"]
    set_shift_group_membership(client, team_member_id=member_id)
    return member_id


def ensure_night_template(client: TestClient) -> None:
    existing = client.get("/api/v1/shift-templates").json()
    if existing:
        return
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "N", "name": "Nacht", "category": "other"},
    ).json()
    assert (
        client.post(
            f"/api/v1/shift-templates/{template['id']}/variants",
            json={
                "label": "Nacht",
                "start_day_class": "any",
                "starts_at": "20:00:00",
                "ends_at": "08:00:00",
                "end_day_offset": 1,
                "required_count": 1,
            },
        ).status_code
        == 200
    )


def create_period(client: TestClient, year: int, month: int) -> int:
    ensure_night_template(client)
    response = client.post("/api/v1/planning-periods", json={"year": year, "month": month})
    assert response.status_code == 200
    return response.json()["id"]


def assign_on(client: TestClient, period_id: int, team_member_id: int, slot_date: str) -> int:
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(item for item in roster["slots"] if item["slot_date"] == slot_date)
    assigned = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
    )
    assert assigned.status_code == 200
    return slot["id"]


def list_entries(client: TestClient, team_member_id: int, start: str, end: str, *, portal: bool = False):
    params = {"team_member_id": team_member_id, "start_date": start, "end_date": end}
    if portal:
        params["team_member_portal"] = "true"
    return client.get("/api/v1/time-entries", params=params)


def test_kind_column_accepts_call_out_without_enum(client):
    test_client, engine = client
    kind_type = TimeEntry.__table__.c.kind.type
    assert getattr(kind_type, "enums", None) is None
    TimeEntryCreate.model_validate(
        {"team_member_id": 1, "entry_date": date(2026, 8, 1), "kind": "call_out"}
    )
    TimeEntryCreate.model_validate(
        {"team_member_id": 1, "entry_date": date(2026, 8, 1), "kind": "in_duty_activity"}
    )
    login_admin(test_client)
    member_id = create_member(test_client, "kinds@example.com")
    created = test_client.post(
        "/api/v1/time-entries",
        json={
            "team_member_id": member_id,
            "entry_date": "2026-08-02",
            "kind": "call_out",
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 200
    assert created.json()["kind"] == "call_out"
    names = {index["name"] for index in inspect(engine).get_indexes("time_entries")}
    assert "ix_time_entries_member_date" in names
    assert "ix_time_entries_roster_slot_id" in names


def test_derivation_is_idempotent_and_preserves_corrections(client):
    test_client, _engine = client
    login_admin(test_client)
    member_id = create_member(test_client, "idem@example.com")
    period_id = create_period(test_client, 2026, 8)
    assign_on(test_client, period_id, member_id, "2026-08-03")
    first = list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
    roster_rows = [row for row in first if row["source"] == "roster"]
    assert len(roster_rows) == 1
    entry_id = roster_rows[0]["id"]
    original_duration = roster_rows[0]["duration_minutes"]
    patched = test_client.patch(
        f"/api/v1/time-entries/{entry_id}",
        json={"duration_minutes": original_duration + 15, "comment": "corrected"},
    )
    assert patched.status_code == 200
    assert "duration_minutes" in patched.json()["corrected_fields"]
    derive = test_client.post(
        "/api/v1/time-entries/derive",
        json={"start_date": "2026-08-01", "end_date": "2026-08-31", "member_ids": [member_id]},
    )
    assert derive.status_code == 200
    again = test_client.post(
        "/api/v1/time-entries/derive",
        json={"start_date": "2026-08-01", "end_date": "2026-08-31", "member_ids": [member_id]},
    )
    assert again.status_code == 200
    second = list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
    roster_rows = [row for row in second if row["source"] == "roster"]
    assert len(roster_rows) == 1
    assert roster_rows[0]["id"] == entry_id
    assert roster_rows[0]["duration_minutes"] == original_duration + 15
    assert roster_rows[0]["comment"] == "corrected"
    recon = test_client.get(
        "/api/v1/time-entries/reconciliation",
        params={"team_member_id": member_id, "start_date": "2026-08-01", "end_date": "2026-08-31"},
    )
    assert recon.status_code == 200
    item = next(row for row in recon.json() if row["id"] == entry_id)
    assert item["diverges"] is True
    assert "duration_minutes" in item["corrected_fields"]
    manual = test_client.post(
        "/api/v1/time-entries",
        json={
            "team_member_id": member_id,
            "entry_date": "2026-08-10",
            "kind": "work",
            "duration_minutes": 45,
            "comment": "manual",
        },
    )
    assert manual.status_code == 200
    test_client.post(
        "/api/v1/time-entries/derive",
        json={"start_date": "2026-08-01", "end_date": "2026-08-31", "member_ids": [member_id]},
    )
    after = list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
    assert any(row["id"] == manual.json()["id"] and row["source"] == "manual" for row in after)


def test_removing_assignment_removes_derived_entry(client):
    test_client, _engine = client
    login_admin(test_client)
    member_id = create_member(test_client, "clear@example.com")
    period_id = create_period(test_client, 2026, 8)
    slot_id = assign_on(test_client, period_id, member_id, "2026-08-04")
    rows = [
        row
        for row in list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
        if row["source"] == "roster"
    ]
    assert len(rows) == 1
    cleared = test_client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot_id})
    assert cleared.status_code == 200
    rows = [
        row
        for row in list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
        if row["source"] == "roster"
    ]
    assert rows == []


def test_vacation_day_status_produces_all_day_absence(client):
    test_client, _engine = client
    login_admin(test_client)
    member_id = create_member(test_client, "vac@example.com")
    period_id = create_period(test_client, 2026, 8)
    cell = test_client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": member_id, "cell_date": "2026-08-11", "status": "urlaub"},
    )
    assert cell.status_code == 200
    rows = [
        row
        for row in list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
        if row["source"] == "day_status"
    ]
    assert len(rows) == 1
    assert rows[0]["kind"] == "absence"
    assert rows[0]["all_day"] is True
    assert rows[0]["consumes_vacation"] is True
    assert rows[0]["planning_day_status_code"] == "urlaub"
    frei = test_client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": member_id, "cell_date": "2026-08-11", "status": "frei"},
    )
    assert frei.status_code == 200
    rows = [
        row
        for row in list_entries(test_client, member_id, "2026-08-01", "2026-08-31").json()
        if row["source"] == "day_status"
    ]
    assert rows == []


def test_entries_query_spans_planning_periods(client):
    test_client, _engine = client
    login_admin(test_client)
    member_id = create_member(test_client, "span@example.com")
    august_id = create_period(test_client, 2026, 8)
    september_id = create_period(test_client, 2026, 9)
    assign_on(test_client, august_id, member_id, "2026-08-03")
    assign_on(test_client, september_id, member_id, "2026-09-07")
    rows = list_entries(test_client, member_id, "2026-08-01", "2026-09-30").json()
    roster_dates = sorted(row["entry_date"] for row in rows if row["source"] == "roster")
    assert roster_dates == ["2026-08-03", "2026-09-07"]


def test_member_cannot_write_another_members_entry(client):
    test_client, _engine = client
    login_admin(test_client)
    other_id = create_member(test_client, "other@example.com")
    login_team_member(test_client)
    me = test_client.get("/api/v1/auth/me").json()
    own_id = me["team_member_id"]
    denied = test_client.post(
        "/api/v1/time-entries?team_member_portal=true",
        json={
            "team_member_id": other_id,
            "entry_date": "2026-08-05",
            "kind": "work",
            "duration_minutes": 10,
        },
    )
    assert denied.status_code == 403
    allowed = test_client.post(
        "/api/v1/time-entries?team_member_portal=true",
        json={
            "team_member_id": own_id,
            "entry_date": "2026-08-05",
            "kind": "work",
            "duration_minutes": 10,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["team_member_id"] == own_id
    listed = list_entries(test_client, other_id, "2026-08-01", "2026-08-31", portal=True)
    assert listed.status_code == 403
