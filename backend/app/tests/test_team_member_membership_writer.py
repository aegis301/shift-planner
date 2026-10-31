from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, ShiftGroup, TeamMember, TeamMemberShiftGroup
from app.models.base import Base
from app.tests.test_api import _seed_membership

ADMIN_EMAIL = "writer-admin@example.com"
ADMIN_PASSWORD = "secret"
INVITEE_EMAIL = "seeded@example.com"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(Organization(id=1, name="Host", slug="host", plan_tier="team"))
        db.add(Organization(id=2, name="Other", slug="other", plan_tier="team"))
        db.flush()
        db.add(ShiftGroup(id=1, organization_id=1, code="g1", name="G1", display_order=0))
        db.add(ShiftGroup(id=2, organization_id=1, code="g2", name="G2", display_order=1))
        db.add(Account(email=INVITEE_EMAIL, hashed_password=hash_password("x")))
        _seed_membership(db, ADMIN_EMAIL, ADMIN_PASSWORD, 1, "admin")
        db.commit()

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        yield test_client
    app.dependency_overrides.clear()


def _stints(team_member_id: int) -> list[tuple[int, date, date | None]]:
    db = next(app.dependency_overrides[get_db]())
    rows = db.scalars(
        select(TeamMemberShiftGroup)
        .where(TeamMemberShiftGroup.team_member_id == team_member_id)
        .order_by(TeamMemberShiftGroup.shift_group_id, TeamMemberShiftGroup.start_date)
    ).all()
    return [(row.shift_group_id, row.start_date, row.end_date) for row in rows]


def _create_member(client: TestClient) -> int:
    response = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def test_profile_save_does_not_change_stints(client: TestClient):
    member_id = _create_member(client)
    response = client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {"team_member_id": member_id, "start_date": "2020-01-01", "end_date": "2020-06-30"},
                {"team_member_id": member_id, "start_date": "2099-01-01", "end_date": None},
            ]
        },
    )
    assert response.status_code == 200, response.text
    before = _stints(member_id)

    response = client.patch(
        f"/api/v1/team-members/{member_id}",
        json={"nickname": "Countess", "notes": "updated"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["nickname"] == "Countess"
    assert _stints(member_id) == before


def test_team_member_update_with_shift_group_ids_returns_422(client: TestClient):
    member_id = _create_member(client)
    response = client.patch(
        f"/api/v1/team-members/{member_id}",
        json={"nickname": "Ignored", "shift_group_ids": [1]},
    )
    assert response.status_code == 422
    assert "shift_group_ids" in response.text
    assert "/memberships" in response.text
    assert _stints(member_id) == []
    db = next(app.dependency_overrides[get_db]())
    assert db.get(TeamMember, member_id).nickname is None


def test_invite_with_prepared_profile_seeds_first_stint(client: TestClient):
    response = client.post(
        "/api/v1/organization/invites",
        json={
            "invitee_email": INVITEE_EMAIL,
            "role": "team_member",
            "prepare_team_member_profile": True,
            "first_name": "Seed",
            "last_name": "Ed",
            "shift_group_ids": [2],
        },
    )
    assert response.status_code == 200, response.text
    db = next(app.dependency_overrides[get_db]())
    member = db.scalar(select(TeamMember).where(TeamMember.email == INVITEE_EMAIL))
    assert member is not None
    assert _stints(member.id) == [(2, date.today(), None)]


def test_shift_group_team_members_put_keeps_dated_history(client: TestClient):
    member_id = _create_member(client)
    other_id = int(
        client.post(
            "/api/v1/team-members",
            json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
        ).json()["id"]
    )
    response = client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {"team_member_id": member_id, "start_date": "2020-01-01", "end_date": "2020-06-30"},
                {"team_member_id": member_id, "start_date": "2021-01-01", "end_date": None},
            ]
        },
    )
    assert response.status_code == 200, response.text

    response = client.put("/api/v1/shift-groups/1/team-members", json={"team_member_ids": [other_id]})
    assert response.status_code == 200, response.text
    today = date.today()
    assert _stints(member_id) == [
        (1, date(2020, 1, 1), date(2020, 6, 30)),
        (1, date(2021, 1, 1), today),
    ]
    assert _stints(other_id) == [(1, today, None)]
