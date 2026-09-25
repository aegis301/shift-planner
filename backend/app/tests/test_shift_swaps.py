from datetime import date
from threading import Barrier, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import (
    Account,
    AuditLog,
    Organization,
    PlanningCell,
    PlanningDayStatusDefinition,
    RosterSlot,
    ShiftGroup,
    TeamMember,
    TeamMemberShiftGroup,
    User,
)
from app.models.base import Base
from app.services.shift_swaps import (
    APPROVAL_QUEUE_STATUSES,
    ShiftSwapConflictError,
    claim_shift_swap,
    list_eligible_claimants,
    list_shift_swaps,
    list_unresolved_shift_swaps,
)


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    db.flush()
    return user


def _add_linked_member(db, user: User, *, first_name: str, email: str, shift_group_id: int | None) -> TeamMember:
    member = TeamMember(
        organization_id=user.organization_id,
        first_name=first_name,
        last_name="Swap",
        email=email,
        user_id=user.id,
        is_active=True,
    )
    db.add(member)
    db.flush()
    if shift_group_id is not None:
        db.add(
            TeamMemberShiftGroup(
                team_member_id=member.id,
                shift_group_id=shift_group_id,
                start_date=date(2000, 1, 1),
            )
        )
    return member


@pytest.fixture()
def swap_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@example.com", "secret", 1, "admin")
        sg = ShiftGroup(organization_id=1, code="sg1", name="SG", display_order=0)
        db.add(sg)
        db.flush()
        alice_user = _seed_membership(db, "alice@example.com", "alicesecret", 1, "team_member")
        bob_user = _seed_membership(db, "bob@example.com", "bobsecret", 1, "team_member")
        dana_user = _seed_membership(db, "dana@example.com", "danasecret", 1, "team_member")
        outsider_user = _seed_membership(db, "outsider@example.com", "outsidersecret", 1, "team_member")
        _add_linked_member(db, alice_user, first_name="Alice", email="alice-tm@example.com", shift_group_id=sg.id)
        _add_linked_member(db, bob_user, first_name="Bob", email="bob-tm@example.com", shift_group_id=sg.id)
        _add_linked_member(db, dana_user, first_name="Dana", email="dana-tm@example.com", shift_group_id=sg.id)
        _add_linked_member(
            db, outsider_user, first_name="Out", email="out-tm@example.com", shift_group_id=None
        )
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login_as(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "organization_slug": "default"},
    )
    assert response.status_code == 200, response.text


def login_admin(client: TestClient) -> None:
    login_as(client, "admin@example.com", "secret")


def _ids(client: TestClient) -> dict[str, int]:
    login_admin(client)
    members = {row["email"]: row["id"] for row in client.get("/api/v1/team-members").json()}
    return {
        "alice": members["alice-tm@example.com"],
        "bob": members["bob-tm@example.com"],
        "dana": members["dana-tm@example.com"],
        "outsider": members["out-tm@example.com"],
    }


def test_giveaway_apply_creates_plan_version_and_audit_trail(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=10, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "draft"
    request_id = created.json()["id"]
    opened = swap_client.post(f"/api/v1/shift-swaps/{request_id}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "open"
    assert ids["bob"] in opened.json()["eligible_member_ids"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{request_id}/claim")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "claimed"
    assert claimed.json()["target_team_member_id"] == ids["bob"]
    login_admin(swap_client)
    approved = swap_client.post(f"/api/v1/shift-swaps/{request_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    before = swap_client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()
    assert before["working_major_version"] == 1
    assert before["working_minor_version"] == 0
    applied = swap_client.post(f"/api/v1/shift-swaps/{request_id}/apply")
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["request"]["status"] == "applied"
    assert body["plan_version"]["trigger"] == "swap_apply"
    assert body["plan_version"]["major_version"] == 1
    assert body["plan_version"]["minor_version"] == 1
    assert body["assignments"][0]["team_member_id"] == ids["bob"]
    assert body["assignments"][0]["source"] == "shift_swap"
    after = swap_client.get(f"/api/v1/planning-periods/{period_id}/versions?shift_group_id=1").json()
    assert after["working_minor_version"] == 1
    assert after["versions"][0]["trigger"] == "swap_apply"
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        logs = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "shift_swap_request",
                    AuditLog.entity_id == str(request_id),
                )
            )
        )
        assert {"create", "open", "claim", "approve", "apply"} <= {row.action for row in logs}
        assignment_logs = list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "roster_slot_assignment")))
        assert any(row.source == "shift_swap" for row in assignment_logs)
    finally:
        db.close()


def test_direct_swap_transitions_and_withdraw(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, other, _template_id = _seed_published_month(swap_client, month=11, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "direct",
            "offered_slot_id": offered["id"],
            "target_team_member_id": ids["bob"],
            "counterparty_slot_id": other["id"],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]
    opened = swap_client.post(f"/api/v1/shift-swaps/{request_id}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "targeted"
    login_as(swap_client, "bob@example.com", "bobsecret")
    accepted = swap_client.post(f"/api/v1/shift-swaps/{request_id}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    login_as(swap_client, "alice@example.com", "alicesecret")
    withdrawn = swap_client.post(f"/api/v1/shift-swaps/{request_id}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"


def test_statutory_error_refuses_claim_with_named_violation(swap_client: TestClient):
    ids = _ids(swap_client)
    _activate_max_duties(swap_client, severity="error")
    period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=3, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{created.json()['id']}/claim")
    assert claimed.status_code == 409, claimed.text
    detail = claimed.json()["detail"]
    assert detail["code"] == "SHIFT_SWAP_ILLEGAL"
    assert any(item["code"] == "WORKTIME_MAX_DUTIES" for item in detail["findings"])
    assert "Duty count exceeds" in detail["message"]


def test_warning_findings_reach_approver(swap_client: TestClient):
    ids = _ids(swap_client)
    _activate_max_duties(swap_client, severity="warning")
    period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=4, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{request_id}/claim")
    assert claimed.status_code == 200, claimed.text
    assert any(
        item["code"] == "WORKTIME_MAX_DUTIES" and item["severity"] == "warning"
        for item in claimed.json()["warning_findings"]
    )
    login_admin(swap_client)
    approved = swap_client.post(f"/api/v1/shift-swaps/{request_id}/approve")
    assert approved.status_code == 200, approved.text
    assert any(item["code"] == "WORKTIME_MAX_DUTIES" for item in approved.json()["warning_findings"])


def test_ineligible_member_cannot_claim(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, _other, template_id = _seed_published_month(swap_client, month=5, ids=ids, publish=False)
    intent = swap_client.put(
        f"/api/v1/matrix/{period_id}/shift-intents/bulk?shift_group_id=1",
        json={
            "intents": [
                {
                    "team_member_id": ids["bob"],
                    "cell_date": offered["slot_date"],
                    "shift_group_id": 1,
                    "shift_template_id": template_id,
                    "kind": "no_go",
                }
            ]
        },
    )
    assert intent.status_code == 200, intent.text
    assert swap_client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    assert ids["bob"] not in created.json()["eligible_member_ids"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{created.json()['id']}/claim")
    assert claimed.status_code == 409, claimed.text
    assert claimed.json()["detail"]["code"] == "SHIFT_SWAP_INELIGIBLE"


def test_concurrent_claims_exactly_one_succeeds(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=6, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    first = swap_client.post(f"/api/v1/shift-swaps/{request_id}/claim")
    assert first.status_code == 200, first.text
    login_as(swap_client, "dana@example.com", "danasecret")
    second = swap_client.post(f"/api/v1/shift-swaps/{request_id}/claim")
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "SHIFT_SWAP_CONFLICT"

    login_admin(swap_client)
    period_id2, offered2, _other2, _ = _seed_published_month(swap_client, month=7, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    raced = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id2,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered2["id"],
            "open_immediately": True,
        },
    )
    assert raced.status_code == 200, raced.text
    race_id = raced.json()["id"]
    barrier = Barrier(2)
    outcomes: list[int] = []

    def _claim(email: str, password: str) -> None:
        with TestClient(app) as other:
            login_as(other, email, password)
            barrier.wait()
            outcomes.append(other.post(f"/api/v1/shift-swaps/{race_id}/claim").status_code)

    threads = [
        Thread(target=_claim, args=("bob@example.com", "bobsecret")),
        Thread(target=_claim, args=("dana@example.com", "danasecret")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count(200) == 1
    assert outcomes.count(409) == 1
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        with pytest.raises(ShiftSwapConflictError) as exc:
            claim_shift_swap(
                db,
                race_id,
                organization_id=1,
                claimer_team_member_id=ids["dana"],
                actor="test",
                source="test",
            )
        assert exc.value.code == "SHIFT_SWAP_CONFLICT"
    finally:
        db.close()


def test_member_cannot_approve_and_outsider_cannot_list(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, _other, _ = _seed_published_month(swap_client, month=8, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    request_id = created.json()["id"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    assert swap_client.post(f"/api/v1/shift-swaps/{request_id}/claim").status_code == 200
    assert swap_client.post(f"/api/v1/shift-swaps/{request_id}/approve").status_code == 403
    listed = swap_client.get(f"/api/v1/shift-swaps?planning_period_id={period_id}&shift_group_id=1")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == request_id
    login_as(swap_client, "outsider@example.com", "outsidersecret")
    listed_out = swap_client.get(f"/api/v1/shift-swaps?planning_period_id={period_id}&shift_group_id=1")
    assert listed_out.status_code == 200
    assert listed_out.json() == []
    assert swap_client.get(f"/api/v1/shift-swaps/{request_id}").status_code == 403


def test_eligible_members_rank_underserved_first(swap_client: TestClient):
    ids = _ids(swap_client)
    _period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=9, ids=ids)
    login_admin(swap_client)
    over = swap_client.put(
        f"/api/v1/team-members/{ids['bob']}/time-account-opening",
        json={"as_of_date": "2020-01-01", "fairness_balances": {"duties": 50}},
    )
    under = swap_client.put(
        f"/api/v1/team-members/{ids['dana']}/time-account-opening",
        json={"as_of_date": "2020-01-01", "fairness_balances": {"duties": 0}},
    )
    assert over.status_code == 200, over.text
    assert under.status_code == 200, under.text
    login_as(swap_client, "alice@example.com", "alicesecret")
    ranked = swap_client.get(
        f"/api/v1/shift-swaps/eligible-members?roster_slot_id={offered['id']}&shift_group_id=1"
    )
    assert ranked.status_code == 200, ranked.text
    body = ranked.json()
    assert ids["dana"] in body
    assert ids["bob"] in body
    assert body.index(ids["dana"]) < body.index(ids["bob"])


def test_eligible_members_unranked_when_fairness_fails(swap_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    ids = _ids(swap_client)
    _period_id, offered, _other, _template_id = _seed_published_month(swap_client, month=2, ids=ids)

    def _boom(*_args, **_kwargs):
        raise ValueError("fairness unavailable")

    monkeypatch.setattr("app.services.shift_swaps.build_fairness_accounts", _boom)
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        ranked = list_eligible_claimants(
            db,
            roster_slot_id=offered["id"],
            organization_id=1,
            shift_group_id=1,
            exclude_team_member_id=ids["alice"],
        )
    finally:
        db.close()
    assert ranked == sorted(ranked)
    assert ids["bob"] in ranked
    assert ids["dana"] in ranked
    assert ids["alice"] not in ranked


def test_unresolved_pool_filters_sorts_and_keeps_past_duties(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, earlier, later, _ = _seed_published_month(swap_client, month=12, ids=ids)
    assert earlier["slot_date"] < later["slot_date"]

    login_as(swap_client, "alice@example.com", "alicesecret")
    draft = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": earlier["id"],
        },
    )
    assert draft.status_code == 200, draft.text
    login_as(swap_client, "bob@example.com", "bobsecret")
    later_open = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": later["id"],
            "open_immediately": True,
        },
    )
    assert later_open.status_code == 200, later_open.text
    later_id = later_open.json()["id"]

    login_admin(swap_client)
    unresolved = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert unresolved.status_code == 200, unresolved.text
    assert [row["id"] for row in unresolved.json()] == [later_id]
    assert unresolved.json()[0]["status"] == "open"
    assert unresolved.json()[0]["duty_date"] == later["slot_date"]
    assert unresolved.json()[0]["offered_by_team_member_id"] == ids["bob"]

    login_as(swap_client, "alice@example.com", "alicesecret")
    withdrawn_draft = swap_client.post(f"/api/v1/shift-swaps/{draft.json()['id']}/withdraw")
    assert withdrawn_draft.status_code == 200, withdrawn_draft.text
    earlier_open = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "direct",
            "offered_slot_id": earlier["id"],
            "target_team_member_id": ids["dana"],
            "open_immediately": True,
        },
    )
    assert earlier_open.status_code == 200, earlier_open.text
    earlier_id = earlier_open.json()["id"]
    assert earlier_open.json()["status"] == "targeted"

    login_admin(swap_client)
    ordered = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert ordered.status_code == 200, ordered.text
    assert [row["id"] for row in ordered.json()] == [earlier_id, later_id]
    assert ordered.json()[0]["target_team_member_id"] == ids["dana"]
    assert ordered.json()[0]["request_age_days"] >= 0
    assert ordered.json()[1]["request_age_days"] >= ordered.json()[0]["request_age_days"]

    login_as(swap_client, "dana@example.com", "danasecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{later_id}/claim")
    assert claimed.status_code == 200, claimed.text
    login_admin(swap_client)
    after_claim = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert [row["id"] for row in after_claim.json()] == [earlier_id]
    queue_params = "&".join(f"statuses={status}" for status in sorted(APPROVAL_QUEUE_STATUSES))
    queued = swap_client.get(
        f"/api/v1/shift-swaps?planning_period_id={period_id}&shift_group_id=1&{queue_params}"
    )
    assert queued.status_code == 200, queued.text
    assert [row["id"] for row in queued.json()] == [later_id]
    assert queued.json()[0]["status"] == "claimed"

    _set_slot_date(swap_client, earlier["id"], date(2020, 1, 2))
    past = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert past.status_code == 200, past.text
    assert past.json()[0]["id"] == earlier_id
    assert past.json()[0]["status"] == "targeted"
    assert past.json()[0]["days_until_duty"] < 0
    assert past.json()[0]["duty_date"] == "2020-01-02"

    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        service_rows = list_unresolved_shift_swaps(
            db,
            organization_id=1,
            planning_period_id=period_id,
            shift_group_id=1,
        )
        queued_rows = list_shift_swaps(
            db,
            organization_id=1,
            planning_period_id=period_id,
            shift_group_id=1,
            statuses=list(APPROVAL_QUEUE_STATUSES),
        )
    finally:
        db.close()
    assert [row.id for row in service_rows] == [earlier_id]
    assert service_rows[0].days_until_duty < 0
    assert [row.id for row in queued_rows] == [later_id]


def test_planner_can_withdraw_open_request_and_member_cannot(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, _other, _ = _seed_published_month(swap_client, month=1, ids=ids)
    login_as(swap_client, "alice@example.com", "alicesecret")
    created = swap_client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    forbidden = swap_client.post(f"/api/v1/shift-swaps/{request_id}/withdraw")
    assert forbidden.status_code == 403
    unresolved_as_member = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert unresolved_as_member.status_code == 403
    login_admin(swap_client)
    withdrawn = swap_client.post(f"/api/v1/shift-swaps/{request_id}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    empty = swap_client.get(
        f"/api/v1/shift-swaps/unresolved?planning_period_id={period_id}&shift_group_id=1"
    )
    assert empty.status_code == 200, empty.text
    assert empty.json() == []


def _set_slot_date(client: TestClient, slot_id: int, slot_date: date) -> None:
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        slot = db.get(RosterSlot, slot_id)
        assert slot is not None
        slot.slot_date = slot_date
        db.commit()
    finally:
        db.close()


def _activate_max_duties(client: TestClient, *, severity: str) -> None:
    login_admin(client)
    response = client.post(
        "/api/v1/work-time-rule-sets",
        json={
            "name": f"swap-duties-{severity}",
            "is_active": True,
            "rules": [
                {
                    "type": "max_duties_per_period",
                    "severity": severity,
                    "count": 1,
                    "period": "month",
                    "additional_allowance_per_quarter": 0,
                    "categories": ["bereitschaftsdienst"],
                }
            ],
        },
    )
    assert response.status_code == 201, response.text


def _seed_published_month(
    client: TestClient,
    *,
    month: int,
    ids: dict[str, int],
    publish: bool = True,
) -> tuple[int, dict, dict, int]:
    login_admin(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": f"SW{month}", "name": f"Swap {month}", "category": "bereitschaftsdienst"},
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "required_count": 1,
        },
    )
    assert variant.status_code == 200, variant.text
    linked = client.put(
        "/api/v1/shift-groups/1/shift-templates",
        json={"shift_template_ids": [template["id"]]},
    )
    assert linked.status_code == 200, linked.text
    period_id = client.post("/api/v1/planning-periods", json={"year": 2027, "month": month}).json()["id"]
    slots = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"]
    offered = slots[0]
    other = next(slot for slot in slots if slot["slot_date"] != offered["slot_date"])
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments?shift_group_id=1",
            json={"roster_slot_id": offered["id"], "team_member_id": ids["alice"]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments?shift_group_id=1",
            json={"roster_slot_id": other["id"], "team_member_id": ids["bob"]},
        ).status_code
        == 200
    )
    if publish:
        assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200
    return period_id, offered, other, template["id"]


def _seed_cross_group_month(
    client: TestClient,
    *,
    ids: dict[str, int],
    late_constraints: list[dict] | None = None,
    long_hours: tuple[str, str] = ("08:00:00", "08:00:00"),
    long_date: str = "2027-12-01",
    min_rest: bool = True,
) -> tuple[int, dict, dict]:
    """Bob is in shift groups 1 and 2. By default group 2 holds a 24 h duty from 08:00 on the
    1st to 08:00 on the 2nd; group 1 holds a 14:00 duty on the 2nd that Alice gives away."""
    login_admin(client)
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        group_b = ShiftGroup(organization_id=1, code="sg2", name="SG B", display_order=1)
        db.add(group_b)
        db.flush()
        db.add(
            TeamMemberShiftGroup(
                team_member_id=ids["bob"],
                shift_group_id=group_b.id,
                start_date=date(2000, 1, 1),
            )
        )
        db.commit()
        group_b_id = group_b.id
    finally:
        db.close()
    if min_rest:
        _activate_min_rest(client)
    late = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "XGA",
            "name": "Late A",
            "category": "bereitschaftsdienst",
            "constraints": late_constraints or [],
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/shift-templates/{late['id']}/variants",
            json={
                "label": "Spät",
                "start_day_class": "any",
                "starts_at": "14:00:00",
                "ends_at": "22:00:00",
                "required_count": 1,
            },
        ).status_code
        == 200
    )
    long_duty = client.post(
        "/api/v1/shift-templates",
        json={"code": "XGB", "name": "24h B", "category": "bereitschaftsdienst"},
    ).json()
    assert (
        client.post(
            f"/api/v1/shift-templates/{long_duty['id']}/variants",
            json={
                "label": "B",
                "start_day_class": "any",
                "starts_at": long_hours[0],
                "ends_at": long_hours[1],
                "required_count": 1,
            },
        ).status_code
        == 200
    )
    for group_id, template_id in ((1, late["id"]), (group_b_id, long_duty["id"])):
        linked = client.put(
            f"/api/v1/shift-groups/{group_id}/shift-templates",
            json={"shift_template_ids": [template_id]},
        )
        assert linked.status_code == 200, linked.text
    period_id = client.post("/api/v1/planning-periods", json={"year": 2027, "month": 12}).json()["id"]
    slots_a = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()["slots"]
    slots_b = client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id={group_b_id}").json()["slots"]
    offered = next(slot for slot in slots_a if slot["slot_date"] == "2027-12-02")
    long_slot = next(slot for slot in slots_b if slot["slot_date"] == long_date)
    assigned = client.put(
        "/api/v1/roster-matrix/assignments?shift_group_id=1",
        json={"roster_slot_id": offered["id"], "team_member_id": ids["alice"]},
    )
    assert assigned.status_code == 200, assigned.text
    published = client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1")
    assert published.status_code == 200, published.text
    return period_id, offered, {**long_slot, "shift_group_id": group_b_id}


def _activate_min_rest(client: TestClient) -> None:
    response = client.post(
        "/api/v1/work-time-rule-sets",
        json={
            "name": "swap-min-rest",
            "is_active": True,
            "rules": [
                {
                    "type": "min_rest_period",
                    "severity": "error",
                    "hours": "11",
                    "reducible_to_hours": "10",
                    "compensation_window_days": 31,
                    "call_out_handling": "interrupt",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text


def _assign_long_duty(client: TestClient, long_slot: dict, member_id: int) -> None:
    login_admin(client)
    response = client.put(
        f"/api/v1/roster-matrix/assignments?shift_group_id={long_slot['shift_group_id']}",
        json={"roster_slot_id": long_slot["id"], "team_member_id": member_id},
    )
    assert response.status_code == 200, response.text


def _open_giveaway(client: TestClient, period_id: int, offered: dict) -> dict:
    login_as(client, "alice@example.com", "alicesecret")
    created = client.post(
        "/api/v1/shift-swaps",
        json={
            "planning_period_id": period_id,
            "shift_group_id": 1,
            "kind": "giveaway",
            "offered_slot_id": offered["id"],
            "open_immediately": True,
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


def _assert_min_rest_refusal(response) -> None:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "SHIFT_SWAP_ILLEGAL"
    assert any(item["code"] == "WORKTIME_MIN_REST" for item in detail["findings"])


def test_duty_in_other_group_blocks_claim_and_eligibility(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, long_slot = _seed_cross_group_month(swap_client, ids=ids)
    _assign_long_duty(swap_client, long_slot, ids["bob"])
    created = _open_giveaway(swap_client, period_id, offered)
    assert ids["bob"] not in created["eligible_member_ids"]
    assert ids["dana"] in created["eligible_member_ids"]
    listed = swap_client.get(
        f"/api/v1/shift-swaps/eligible-members?roster_slot_id={offered['id']}&shift_group_id=1"
    )
    assert listed.status_code == 200, listed.text
    assert ids["bob"] not in listed.json()
    login_as(swap_client, "bob@example.com", "bobsecret")
    _assert_min_rest_refusal(swap_client.post(f"/api/v1/shift-swaps/{created['id']}/claim"))


def test_duty_in_other_group_blocks_apply(swap_client: TestClient):
    ids = _ids(swap_client)
    period_id, offered, long_slot = _seed_cross_group_month(swap_client, ids=ids)
    created = _open_giveaway(swap_client, period_id, offered)
    assert ids["bob"] in created["eligible_member_ids"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{created['id']}/claim")
    assert claimed.status_code == 200, claimed.text
    login_admin(swap_client)
    approved = swap_client.post(f"/api/v1/shift-swaps/{created['id']}/approve")
    assert approved.status_code == 200, approved.text
    _assign_long_duty(swap_client, long_slot, ids["bob"])
    _assert_min_rest_refusal(swap_client.post(f"/api/v1/shift-swaps/{created['id']}/apply"))
    matrix = swap_client.get(f"/api/v1/roster-matrix/{period_id}?shift_group_id=1").json()
    holder = next(row for row in matrix["assignments"] if row["roster_slot_id"] == offered["id"])
    assert holder["team_member_id"] == ids["alice"]


def test_group_status_does_not_judge_duty_in_other_group(swap_client: TestClient):
    """Bob's group-2 duty on the swap day meets a blocking status he set in group 1. That
    pairing is not the swap's business: the offered group-1 template allows the overlap, and
    roster rules only look at duties of the swap's group."""
    ids = _ids(swap_client)
    period_id, offered, long_slot = _seed_cross_group_month(
        swap_client,
        ids=ids,
        late_constraints=[{"type": "unavailable_overlap_policy", "unavailable_overlap_mode": "allow"}],
        long_hours=("06:00:00", "07:00:00"),
        long_date="2027-12-02",
        min_rest=False,
    )
    _assign_long_duty(swap_client, long_slot, ids["bob"])
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        db.add(
            PlanningDayStatusDefinition(
                organization_id=1,
                code="xg_block",
                label="Blocked",
                color_preset="sky",
                blocks_roster_assignment=True,
            )
        )
        db.add(
            PlanningCell(
                planning_period_id=period_id,
                shift_group_id=1,
                team_member_id=ids["bob"],
                cell_date=date(2027, 12, 2),
                status="xg_block",
            )
        )
        db.commit()
    finally:
        db.close()
    created = _open_giveaway(swap_client, period_id, offered)
    assert ids["bob"] in created["eligible_member_ids"]
    login_as(swap_client, "bob@example.com", "bobsecret")
    claimed = swap_client.post(f"/api/v1/shift-swaps/{created['id']}/claim")
    assert claimed.status_code == 200, claimed.text
