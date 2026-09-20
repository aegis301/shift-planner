from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, ShiftGroup, TeamMember, User, UserShiftGroup
from app.models.base import Base
from app.services.hours_ledger import pattern_minutes_for_date


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    return user


def test_pattern_minutes_weekday_and_overnight():
    pattern = [
        {"weekday": "mon", "start": "08:00:00", "end": "16:30:00"},
        {"weekday": "sat", "start": "20:00:00", "end": "08:00:00"},
    ]
    assert pattern_minutes_for_date(pattern, date(2026, 8, 3)) == 510
    assert pattern_minutes_for_date(pattern, date(2026, 8, 4)) == 0
    assert pattern_minutes_for_date(pattern, date(2026, 8, 8)) == 720


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
        planner = _seed_membership(db, "planner@example.com", "secret", 1, "planner")
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
        g1 = ShiftGroup(organization_id=1, code="icu", name="ICU", display_order=0)
        g2 = ShiftGroup(organization_id=1, code="ward", name="Ward", display_order=1)
        db.add_all([g1, g2])
        db.flush()
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=g1.id))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "organization_slug": "default"},
    ).status_code == 200


def set_group_members(client: TestClient, group_id: int, member_ids: list[int]) -> None:
    response = client.put(
        f"/api/v1/shift-groups/{group_id}/memberships",
        json={
            "memberships": [
                {"team_member_id": member_id, "start_date": "2026-01-01", "end_date": None}
                for member_id in member_ids
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
    return response.json()["id"]


def test_hours_ledger_running_account_keeps_columns_separate(client: TestClient):
    login(client, "admin@example.com", "secret")
    member_id = create_member(client, "hours@example.com")
    set_group_members(client, 1, [member_id])
    opening = client.put(
        f"/api/v1/team-members/{member_id}/time-account-opening",
        json={
            "as_of_date": "2026-01-01",
            "overtime_minutes": 60,
            "vacation_days_remaining": "5",
            "sick_days_used_ytd": "0",
        },
    )
    assert opening.status_code == 200
    created = client.post(
        "/api/v1/time-entries",
        json={
            "team_member_id": member_id,
            "entry_date": "2026-08-03",
            "kind": "work",
            "duration_minutes": 120,
            "statutory_minutes": 40,
            "credited_minutes": 100,
            "counts_toward_contract": True,
        },
    )
    assert created.status_code == 200
    absence = client.post(
        "/api/v1/time-entries",
        json={
            "team_member_id": member_id,
            "entry_date": "2026-08-04",
            "kind": "absence",
            "all_day": True,
            "consumes_vacation": True,
            "counts_toward_contract": False,
        },
    )
    assert absence.status_code == 200
    ledger = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": member_id,
            "start_date": "2026-08-03",
            "end_date": "2026-08-03",
        },
    )
    assert ledger.status_code == 200
    payload = ledger.json()
    totals = payload["totals"]
    assert totals["statutory_minutes"] == 40
    assert totals["credited_minutes"] == 100
    assert totals["credited_minutes_toward_contract"] == 100
    assert totals["contract_target_minutes"] == 510
    assert totals["opening_overtime_minutes"] == 60
    assert totals["running_overtime_minutes"] == 60 + 100 - 510
    assert "combined" not in totals
    assert payload["opening"]["overtime_minutes"] == 60
    assert payload["entries"][0]["statutory_minutes"] == 40
    assert payload["entries"][0]["credited_minutes"] == 100
    month = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": member_id,
            "start_date": "2026-08-03",
            "end_date": "2026-08-04",
        },
    )
    month_totals = month.json()["totals"]
    assert month_totals["absence_count"] == 1
    assert float(month_totals["vacation_days_consumed"]) == 1
    assert float(month_totals["vacation_days_remaining"]) == 4


def test_hours_ledger_scope_member_own_and_planner_shift_group(client: TestClient):
    login(client, "admin@example.com", "secret")
    in_scope = create_member(client, "inscope@example.com")
    out_scope = create_member(client, "outscope@example.com")
    set_group_members(client, 2, [out_scope])
    linked = client.get("/api/v1/team-members").json()
    portal_member_id = next(row["id"] for row in linked if row["email"] == "docperson@example.com")
    set_group_members(client, 1, [in_scope, portal_member_id])

    login(client, "doc@example.com", "docsecret")
    own = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": portal_member_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "team_member_portal": "true",
        },
    )
    assert own.status_code == 200
    other = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": in_scope,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "team_member_portal": "true",
        },
    )
    assert other.status_code == 403

    login(client, "planner@example.com", "secret")
    missing_group = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": in_scope,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )
    assert missing_group.status_code == 403
    allowed = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": in_scope,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "shift_group_id": 1,
            "include_reconciliation": "true",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["reconciliation"] == []
    denied = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": out_scope,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "shift_group_id": 1,
        },
    )
    assert denied.status_code == 403
    other_group = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": out_scope,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "shift_group_id": 2,
        },
    )
    assert other_group.status_code == 403


def test_hours_ledger_patch_statutory_and_credited(client: TestClient):
    login(client, "admin@example.com", "secret")
    member_id = create_member(client, "snap@example.com")
    created = client.post(
        "/api/v1/time-entries",
        json={
            "team_member_id": member_id,
            "entry_date": "2026-08-03",
            "kind": "work",
            "duration_minutes": 60,
            "statutory_minutes": 60,
            "credited_minutes": 60,
        },
    )
    assert created.status_code == 200
    entry_id = created.json()["id"]
    patched = client.patch(
        f"/api/v1/time-entries/{entry_id}",
        json={"credited_minutes": 90, "statutory_minutes": 50},
    )
    assert patched.status_code == 200
    assert patched.json()["credited_minutes"] == 90
    assert patched.json()["statutory_minutes"] == 50
    ledger = client.get(
        "/api/v1/time-entries/ledger",
        params={
            "team_member_id": member_id,
            "start_date": "2026-08-03",
            "end_date": "2026-08-03",
        },
    )
    row = ledger.json()["entries"][0]
    assert row["credited_minutes"] == 90
    assert row["statutory_minutes"] == 50
