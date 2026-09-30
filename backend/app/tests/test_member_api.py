from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, ShiftGroup, TeamMember, User
from app.models.base import Base
from app.services.shift_swaps import (
    SWAP_KIND_DIRECT,
    SWAP_KIND_GIVEAWAY,
    SWAP_STATUS_ACCEPTED,
    SWAP_STATUS_APPROVED,
    SWAP_STATUS_CLAIMED,
    SWAP_STATUS_DRAFT,
    SWAP_STATUS_OPEN,
    SWAP_STATUS_TARGETED,
    ShiftSwapRequest,
    member_swap_actions,
)


def _user(db, email: str, password: str, role: str) -> User:
    account = Account(email=email, hashed_password=hash_password(password))
    db.add(account)
    db.flush()
    user = User(account_id=account.id, organization_id=1, role=role, locale="de")
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _user(db, "admin@example.com", "secret", "admin")
        ada_user = _user(db, "ada@example.com", "ada-secret", "team_member")
        bob_user = _user(db, "bob@example.com", "bob-secret", "team_member")
        db.add(ShiftGroup(organization_id=1, code="sg", name="Group", display_order=0))
        db.flush()
        ada = TeamMember(
            organization_id=1,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            user_id=ada_user.id,
        )
        bob = TeamMember(
            organization_id=1,
            first_name="Bob",
            last_name="Colleague",
            email="bob@example.com",
            user_id=bob_user.id,
        )
        db.add(ada)
        db.add(bob)
        db.commit()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, SessionLocal, engine
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def _member_ids(SessionLocal) -> tuple[int, int]:
    with SessionLocal() as db:
        ada = db.scalar(select(TeamMember).where(TeamMember.email == "ada@example.com"))
        bob = db.scalar(select(TeamMember).where(TeamMember.email == "bob@example.com"))
        assert ada is not None and bob is not None
        return ada.id, bob.id


def _prepare_month(client: TestClient, SessionLocal) -> tuple[int, int, int]:
    ada_id, bob_id = _member_ids(SessionLocal)
    _login(client, "admin@example.com", "secret")
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "BD", "name": "Bereitschaft Ada", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    client.put("/api/v1/shift-groups/1/shift-templates", json={"shift_template_ids": [template["id"]]})
    client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {"team_member_id": ada_id, "start_date": "2026-01-01", "end_date": None},
                {"team_member_id": bob_id, "start_date": "2026-01-01", "end_date": None},
            ]
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()
    slot = next(row for row in roster["slots"] if row["shift_template_id"] == template["id"])
    assigned = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": ada_id},
    )
    assert assigned.status_code == 200, assigned.text
    return period_id, ada_id, slot["id"]


def test_member_routes_reject_an_unlinked_account(client):
    test_client, _session, _engine = client
    _login(test_client, "admin@example.com", "secret")
    routes = [
        ("GET", "/api/v1/me/home"),
        ("GET", "/api/v1/me/duties?from=2026-10-01&to=2026-10-31"),
        ("GET", "/api/v1/me/wishes/1?shift_group_id=1"),
        ("PUT", "/api/v1/me/wishes/1/cells?shift_group_id=1", {"cells": []}),
        ("PUT", "/api/v1/me/wishes/1/intents?shift_group_id=1", {"intents": []}),
        ("PUT", "/api/v1/me/wishes/1/note?shift_group_id=1", {"team_member_id": 1, "summary": "x"}),
        ("GET", "/api/v1/me/swaps"),
        ("GET", "/api/v1/me/hours?from=2026-10-01&to=2026-10-31"),
        ("POST", "/api/v1/me/calendar-token"),
        ("DELETE", "/api/v1/me/calendar-token"),
    ]
    for item in routes:
        method, path = item[0], item[1]
        body = item[2] if len(item) > 2 else None
        response = test_client.request(method, path, json=body)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "no_linked_team_member"


def test_member_reads_and_writes_only_their_own_data(client):
    test_client, SessionLocal, _engine = client
    period_id, ada_id, slot_id = _prepare_month(test_client, SessionLocal)
    _login(test_client, "ada@example.com", "ada-secret")
    home = test_client.get("/api/v1/me/home")
    assert home.status_code == 200, home.text
    assert all(row["roster_slot_id"] == slot_id for row in home.json()["duties"] if row["planning_period_id"] == period_id)
    duties = test_client.get("/api/v1/me/duties?from=2026-10-01&to=2026-10-31")
    assert duties.status_code == 200
    assert duties.json()
    assert all(row["roster_slot_id"] == slot_id for row in duties.json())
    wishes = test_client.get(f"/api/v1/me/wishes/{period_id}?shift_group_id=1")
    assert wishes.status_code == 200, wishes.text
    body = wishes.json()
    assert body["editable"] is True
    assert {row["id"] for row in body["matrix"]["team_members"]} == {ada_id}
    assert all(row["team_member_id"] == ada_id for row in body["cells"])
    saved = test_client.put(
        f"/api/v1/me/wishes/{period_id}/cells?shift_group_id=1",
        json={"cells": [{"team_member_id": ada_id, "cell_date": "2026-10-03", "status": "frei"}]},
    )
    assert saved.status_code == 200, saved.text
    _, bob_id = _member_ids(SessionLocal)
    foreign = test_client.put(
        f"/api/v1/me/wishes/{period_id}/cells?shift_group_id=1",
        json={"cells": [{"team_member_id": bob_id, "cell_date": "2026-10-04", "status": "frei"}]},
    )
    assert foreign.status_code == 403
    assert foreign.json()["detail"]["code"] == "not_self"
    note = test_client.put(
        f"/api/v1/me/wishes/{period_id}/note?shift_group_id=1",
        json={"team_member_id": ada_id, "summary": "mine"},
    )
    assert note.status_code == 200
    assert note.json()["team_member_id"] == ada_id
    hours = test_client.get("/api/v1/me/hours?from=2026-10-01&to=2026-10-31")
    assert hours.status_code == 200
    assert hours.json()["team_member_id"] == ada_id
    _login(test_client, "bob@example.com", "bob-secret")
    bob_wishes = test_client.get(f"/api/v1/me/wishes/{period_id}?shift_group_id=1")
    assert all(row["team_member_id"] == bob_id for row in bob_wishes.json()["cells"])
    assert bob_wishes.json()["note"] is None
    bob_duties = test_client.get("/api/v1/me/duties?from=2026-10-01&to=2026-10-31")
    assert all(row["roster_slot_id"] != slot_id for row in bob_duties.json())


def test_member_swaps_list_only_the_callers_requests(client):
    test_client, SessionLocal, _engine = client
    period_id, ada_id, slot_id = _prepare_month(test_client, SessionLocal)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            ShiftSwapRequest(
                organization_id=1,
                planning_period_id=period_id,
                shift_group_id=1,
                kind=SWAP_KIND_GIVEAWAY,
                status=SWAP_STATUS_OPEN,
                offered_by_team_member_id=ada_id,
                offered_slot_id=slot_id,
                warning_findings=[],
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    _login(test_client, "ada@example.com", "ada-secret")
    ada_rows = test_client.get("/api/v1/me/swaps")
    assert ada_rows.status_code == 200, ada_rows.text
    assert len(ada_rows.json()) == 1
    ada_row = ada_rows.json()[0]
    assert ada_row["offered_by_team_member_id"] == ada_id
    assert "withdraw" in ada_row["allowed_actions"]
    assert ada_row["disabled_reasons"]["claim"] == "SHIFT_SWAP_INELIGIBLE"
    _login(test_client, "bob@example.com", "bob-secret")
    bob_rows = test_client.get("/api/v1/me/swaps").json()
    assert len(bob_rows) == 1
    assert bob_rows[0]["offered_by_team_member_id"] == ada_id
    assert "claim" in bob_rows[0]["allowed_actions"]
    assert bob_rows[0]["target_team_member_id"] is None


def test_published_wishes_are_read_only(client):
    test_client, SessionLocal, _engine = client
    period_id, ada_id, _slot_id = _prepare_month(test_client, SessionLocal)
    published = test_client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1")
    assert published.status_code == 200
    published = test_client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1")
    assert published.status_code == 200, published.text
    _login(test_client, "ada@example.com", "ada-secret")
    wishes = test_client.get(f"/api/v1/me/wishes/{period_id}?shift_group_id=1")
    assert wishes.json()["editable"] is False
    assert wishes.json()["read_only_reason"] == "published"
    refused = test_client.put(
        f"/api/v1/me/wishes/{period_id}/cells?shift_group_id=1",
        json={"cells": [{"team_member_id": ada_id, "cell_date": "2026-10-05", "status": "frei"}]},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "published"


def test_calendar_token_ics_hides_colleagues(client):
    test_client, SessionLocal, _engine = client
    period_id, _ada_id, ada_slot = _prepare_month(test_client, SessionLocal)
    _, bob_id = _member_ids(SessionLocal)
    roster = test_client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()
    other_slot = next(row["id"] for row in roster["slots"] if row["id"] != ada_slot)
    client_put = test_client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": other_slot, "team_member_id": bob_id},
    )
    assert client_put.status_code == 200, client_put.text
    test_client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1")
    _login(test_client, "ada@example.com", "ada-secret")
    created = test_client.post("/api/v1/me/calendar-token")
    assert created.status_code == 200
    token = created.json()["calendar_token"]
    test_client.cookies.clear()
    ics = test_client.get(f"/api/v1/me/calendar.ics?token={token}")
    assert ics.status_code == 200
    text = ics.text
    assert "Bereitschaft Ada" in text
    assert "Colleague" not in text
    assert "Bob" not in text
    assert test_client.get("/api/v1/me/calendar.ics?token=nope").status_code == 401
    _login(test_client, "ada@example.com", "ada-secret")
    assert test_client.delete("/api/v1/me/calendar-token").status_code == 204
    assert test_client.get(f"/api/v1/me/calendar.ics?token={token}").status_code == 401


def test_home_and_duties_query_count_does_not_grow_with_duties(client):
    test_client, SessionLocal, engine = client
    _prepare_month(test_client, SessionLocal)
    ada_id, _bob_id = _member_ids(SessionLocal)

    def seed(count: int, month: int) -> None:
        with SessionLocal() as db:
            period = test_client.post("/api/v1/planning-periods", json={"year": 2026, "month": month}).json()
            from app.models import PlanningPeriod, RosterSlot, RosterSlotAssignment

            period_row = db.get(PlanningPeriod, period["id"])
            assert period_row is not None
            start = datetime(2026, month, 1, 8, 0, tzinfo=UTC)
            for index in range(count):
                slot = RosterSlot(
                    planning_period_id=period_row.id,
                    slot_date=period_row and __import__("datetime").date(2026, month, 1) + timedelta(days=index % 27),
                    position=index + 1,
                    starts_at=start + timedelta(days=index % 27),
                    ends_at=start + timedelta(days=index % 27, hours=8),
                    source="test",
                )
                db.add(slot)
                db.flush()
                db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=ada_id, source="test"))
            db.commit()

    from app.services.member_portal import get_member_home, list_member_duties

    def count_queries(callback) -> int:
        total = {"n": 0}

        def before(*_args, **_kwargs):
            total["n"] += 1

        event.listen(engine, "before_cursor_execute", before)
        try:
            callback()
        finally:
            event.remove(engine, "before_cursor_execute", before)
        return total["n"]

    with SessionLocal() as db:
        user = db.scalar(select(User).join(Account).where(Account.email == "ada@example.com"))
        assert user is not None
        seed(5, 11)
        small_home = count_queries(lambda: get_member_home(db, user=user))
        small_duties = count_queries(
            lambda: list_member_duties(db, user=user, start=__import__("datetime").date(2026, 11, 1), end=__import__("datetime").date(2026, 11, 30))
        )
        seed(50, 12)
        large_home = count_queries(lambda: get_member_home(db, user=user))
        large_duties = count_queries(
            lambda: list_member_duties(db, user=user, start=__import__("datetime").date(2026, 12, 1), end=__import__("datetime").date(2026, 12, 31))
        )
    assert small_home == large_home
    assert small_duties == large_duties


@pytest.mark.parametrize(
    ("status", "kind", "viewer", "eligible", "action", "outcome"),
    [
        (SWAP_STATUS_DRAFT, SWAP_KIND_GIVEAWAY, "offerer", False, "withdraw", "allowed"),
        (SWAP_STATUS_DRAFT, SWAP_KIND_GIVEAWAY, "other", False, "withdraw", "SHIFT_SWAP_NOT_OWNER"),
        (SWAP_STATUS_OPEN, SWAP_KIND_GIVEAWAY, "other", True, "claim", "allowed"),
        (SWAP_STATUS_OPEN, SWAP_KIND_GIVEAWAY, "offerer", True, "claim", "SHIFT_SWAP_INELIGIBLE"),
        (SWAP_STATUS_OPEN, SWAP_KIND_GIVEAWAY, "other", False, "claim", "SHIFT_SWAP_INELIGIBLE"),
        (SWAP_STATUS_TARGETED, SWAP_KIND_DIRECT, "target", False, "accept", "allowed"),
        (SWAP_STATUS_TARGETED, SWAP_KIND_DIRECT, "offerer", False, "accept", "SHIFT_SWAP_NOT_OWNER"),
        (SWAP_STATUS_TARGETED, SWAP_KIND_DIRECT, "target", False, "decline", "allowed"),
        (SWAP_STATUS_TARGETED, SWAP_KIND_DIRECT, "other", False, "decline", "SHIFT_SWAP_INVALID_TRANSITION"),
        (SWAP_STATUS_CLAIMED, SWAP_KIND_GIVEAWAY, "offerer", False, "withdraw", "allowed"),
        (SWAP_STATUS_CLAIMED, SWAP_KIND_GIVEAWAY, "target", False, "withdraw", "SHIFT_SWAP_NOT_OWNER"),
        (SWAP_STATUS_ACCEPTED, SWAP_KIND_DIRECT, "offerer", False, "withdraw", "allowed"),
        (SWAP_STATUS_APPROVED, SWAP_KIND_DIRECT, "offerer", False, "withdraw", None),
        (SWAP_STATUS_APPROVED, SWAP_KIND_DIRECT, "target", False, "decline", "SHIFT_SWAP_INVALID_TRANSITION"),
        (SWAP_STATUS_OPEN, SWAP_KIND_GIVEAWAY, "other", True, "decline", "SHIFT_SWAP_INVALID_TRANSITION"),
    ],
)
def test_member_swap_actions_match_transition_rules(status, kind, viewer, eligible, action, outcome):
    ids = {"offerer": 1, "target": 2, "other": 3}
    row = ShiftSwapRequest(
        kind=kind,
        status=status,
        offered_by_team_member_id=1,
        target_team_member_id=2,
        offered_slot_id=9,
        shift_group_id=1,
        planning_period_id=1,
        organization_id=1,
    )
    allowed, disabled = member_swap_actions(row, team_member_id=ids[viewer], eligible_to_claim=eligible)
    if outcome == "allowed":
        assert action in allowed
        assert action not in disabled
    elif outcome is None:
        assert action not in allowed
        assert action not in disabled
    else:
        assert action not in allowed
        assert disabled[action] == outcome
