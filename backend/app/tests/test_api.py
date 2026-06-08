from datetime import date

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
    TeamMember,
    TeamMemberShiftGroup,
    Organization,
    OrganizationJoinRequest,
    ShiftGroup,
    User,
    UserShiftGroup,
)
from app.models.base import Base
from app.services.authz import ROLE_PLANNER


def _seed_membership(db, email: str, password: str, org_id: int, role: str, locale: str = "de") -> User:
    em = email.lower()
    acc = db.scalar(select(Account).where(Account.email == em))
    if acc is None:
        acc = Account(email=em, hashed_password=hash_password(password))
        db.add(acc)
        db.flush()
    u = User(account_id=acc.id, organization_id=org_id, role=role, locale=locale)
    db.add(u)
    return u


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
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def team_member_client():
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
        portal_user = _seed_membership(db, "doc@example.com", "docsecret", 1, "team_member")
        db.flush()
        linked_member = TeamMember(
            organization_id=1,
            first_name="Seeded",
            last_name="TeamMember",
            email="docperson@example.com",
            employment_percentage=100,
            user_id=portal_user.id,
        )
        db.add(linked_member)
        db.flush()
        sg = ShiftGroup(organization_id=1, code="tmportal_sg", name="Portal SG", display_order=0)
        db.add(sg)
        db.flush()
        db.add(TeamMemberShiftGroup(team_member_id=linked_member.id, shift_group_id=sg.id))
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


def login_team_member(cl: TestClient) -> None:
    response = cl.post(
        "/api/v1/auth/login",
        json={
            "email": "doc@example.com",
            "password": "docsecret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_me_team_member_for_admin_with_linked_profile(client: TestClient):
    login(client)
    assert client.get("/api/v1/auth/me/team-member").status_code == 404
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == "admin"
    uid = me["id"]
    created = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Admin",
            "last_name": "Linked",
            "email": "admin-linked-self@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [],
            "user_id": uid,
        },
    )
    assert created.status_code == 200
    assert client.get("/api/v1/auth/me").json()["capabilities"]["team_member_portal"] is True
    tm = client.get("/api/v1/auth/me/team-member")
    assert tm.status_code == 200
    assert tm.json()["email"] == "admin-linked-self@example.com"


def test_team_member_nickname_profile_and_matrix(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    uid = me["id"]
    created = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Nick",
            "last_name": "Mustermann",
            "nickname": "NM",
            "email": "nick-matrix@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [],
            "user_id": uid,
        },
    )
    assert created.status_code == 200
    member_id = created.json()["id"]
    patched = client.patch(
        "/api/v1/auth/me/team-member",
        json={"nickname": "  Planner  "},
    )
    assert patched.status_code == 200
    assert patched.json()["nickname"] == "Planner"
    period = client.post(
        "/api/v1/planning-periods",
        json={"year": 2030, "month": 6},
    )
    assert period.status_code == 200
    period_id = period.json()["id"]
    wishes = client.get(f"/api/v1/matrix/{period_id}")
    assert wishes.status_code == 200
    member_row = next(
        row for row in wishes.json()["team_members"] if row["id"] == member_id
    )
    assert member_row["nickname"] == "Planner"
    roster = client.get(f"/api/v1/roster-matrix/{period_id}")
    assert roster.status_code == 200
    roster_member = next(
        row for row in roster.json()["team_members"] if row["id"] == member_id
    )
    assert roster_member["nickname"] == "Planner"


def test_admin_matrix_team_member_portal_filters_to_linked_self(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    uid = me["id"]
    self_member = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Admin",
            "last_name": "Self",
            "email": "admin-self-portal@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
            "user_id": uid,
        },
    ).json()
    other_member = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Other",
            "last_name": "Person",
            "email": "other-portal@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2031, "month": 3}).json()["id"]
    full = client.get(f"/api/v1/matrix/{period_id}?shift_group_id=1").json()
    assert len(full["team_members"]) >= 2
    portal = client.get(
        f"/api/v1/matrix/{period_id}?shift_group_id=1&team_member_portal=true"
    ).json()
    assert len(portal["team_members"]) == 1
    assert portal["team_members"][0]["id"] == self_member["id"]
    denied = client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1&team_member_portal=true",
        json={
            "team_member_id": other_member["id"],
            "cell_date": "2031-03-01",
            "status": "frei",
        },
    )
    assert denied.status_code == 403
    allowed = client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1&team_member_portal=true",
        json={
            "team_member_id": self_member["id"],
            "cell_date": "2031-03-01",
            "status": "frei",
        },
    )
    assert allowed.status_code == 200


def test_login_without_organization_slug_when_email_unique(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "secret",
            "organization_slug": "",
        },
    )
    assert response.status_code == 200


def test_login_without_slug_when_same_email_in_two_orgs_prefers_slug_order():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="A", slug="org-a", plan_tier="team"))
        db.add(Organization(id=2, name="B", slug="org-b", plan_tier="team"))
        db.flush()
        acc = Account(email="dup@example.com", hashed_password=hash_password("pwone"))
        db.add(acc)
        db.flush()
        db.add(User(account_id=acc.id, organization_id=1, role="admin", locale="de"))
        db.add(User(account_id=acc.id, organization_id=2, role="admin", locale="de"))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            r = tc.post(
                "/api/v1/auth/login",
                json={
                    "email": "dup@example.com",
                    "password": "pwone",
                },
            )
            assert r.status_code == 200
            me = r.json()
            assert me["auth_kind"] == "user"
            assert me["organization"]["slug"] == "org-a"
    finally:
        app.dependency_overrides.clear()


def test_applicant_post_me_join_request_after_rejection():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Org", slug="orgslug", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@orgslug.example", "admsecret", 1, "admin")
        applicant = _seed_membership(db, "app@orgslug.example", "appsecret", 1, "applicant")
        db.flush()
        db.add(
            OrganizationJoinRequest(
                organization_id=1,
                requester_user_id=applicant.id,
                first_name="Old",
                last_name="Name",
                message=None,
                status="rejected",
            )
        )
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={
                        "email": "app@orgslug.example",
                        "password": "appsecret",
                        "organization_slug": "orgslug",
                    },
                ).status_code
                == 200
            )
            jr = tc.post(
                "/api/v1/auth/me/join-request",
                json={"first_name": "New", "last_name": "Applicant", "message": "Please reconsider"},
            )
            assert jr.status_code == 200
            assert jr.json()["status"] == "pending"
            assert jr.json()["first_name"] == "New"
            dup = tc.post(
                "/api/v1/auth/me/join-request",
                json={"first_name": "X", "last_name": "Y", "message": None},
            )
            assert dup.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_non_applicant_cannot_post_me_join_request(client: TestClient):
    login(client)
    assert (
        client.post(
            "/api/v1/auth/me/join-request",
            json={"first_name": "X", "last_name": "Y", "message": None},
        ).status_code
        == 403
    )


def test_delete_own_account_wrong_password(client: TestClient):
    login(client)
    response = client.post("/api/v1/auth/delete-account", json={"password": "wrong"})
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_own_account_sole_admin_forbidden(client: TestClient):
    login(client)
    response = client.post("/api/v1/auth/delete-account", json={"password": "secret"})
    assert response.status_code == 400
    assert "only" in response.json()["detail"].lower() and "admin" in response.json()["detail"].lower()
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_own_account_team_member_user(team_member_client: TestClient):
    login_team_member(team_member_client)
    response = team_member_client.post("/api/v1/auth/delete-account", json={"password": "docsecret"})
    assert response.status_code == 204
    assert team_member_client.get("/api/v1/auth/me").status_code == 401


def test_auth_me_includes_organization(client: TestClient):
    login(client)
    data = client.get("/api/v1/auth/me").json()
    assert data["auth_kind"] == "user"
    assert data["organization_id"] == 1
    assert data["organization"]["id"] == 1
    assert data["organization"]["name"] == "Default"
    assert data["organization"]["slug"] == "default"
    assert data["organization"]["plan_tier"] == "team"
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["organization"]["slug"] == "default"


def test_auth_me_admin_organization_shift_groups_reflects_org(client: TestClient):
    login(client)
    empty = client.get("/api/v1/auth/me").json()
    assert empty["role"] == "admin"
    assert len(empty["organization_shift_groups"]) == 1
    assert empty["organization_shift_groups"][0]["code"] == "default_sg"
    r = client.post(
        "/api/v1/shift-groups",
        json={"code": "g-me", "name": "Gm", "display_order": 0, "is_active": True},
    )
    assert r.status_code == 200
    gid = r.json()["id"]
    me = client.get("/api/v1/auth/me").json()
    assert any(x["id"] == gid for x in me["organization_shift_groups"])


def test_auth_me_team_member_organization_shift_groups_empty(team_member_client: TestClient):
    login_team_member(team_member_client)
    data = team_member_client.get("/api/v1/auth/me").json()
    assert data["organization_shift_groups"] == []


def test_register_account_only_onboarding_create_organization():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            reg = tc.post(
                "/api/v1/auth/register",
                json={
                    "email": "fresh@example.com",
                    "password": "pw12345678",
                    "password_confirm": "pw12345678",
                    "locale": "de",
                },
            )
            assert reg.status_code == 200
            body = reg.json()
            assert body["auth_kind"] == "account"
            assert body["email"] == "fresh@example.com"
            me = tc.get("/api/v1/auth/me").json()
            assert me["auth_kind"] == "account"
            assert tc.get("/api/v1/shift-groups").status_code == 403
            cr = tc.post(
                "/api/v1/auth/me/onboarding/create-organization",
                json={"organization_name": "Fresh Org", "organization_slug": "fresh-org"},
            )
            assert cr.status_code == 200
            u = cr.json()
            assert u["auth_kind"] == "user"
            assert u["organization"]["slug"] == "fresh-org"
            assert u["role"] == "admin"
    finally:
        app.dependency_overrides.clear()


def test_register_account_only_onboarding_join_organization():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Existing", slug="existing-org", plan_tier="team"))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            reg = tc.post(
                "/api/v1/auth/register",
                json={
                    "email": "joiner@example.com",
                    "password": "pw12345678",
                    "password_confirm": "pw12345678",
                    "locale": "en",
                },
            )
            assert reg.status_code == 200
            assert reg.json()["auth_kind"] == "account"
            jo = tc.post(
                "/api/v1/auth/me/onboarding/join-organization",
                json={
                    "organization_slug": "existing-org",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "message": None,
                },
            )
            assert jo.status_code == 200
            u = jo.json()
            assert u["auth_kind"] == "user"
            assert u["role"] == "applicant"
            assert u["organization"]["slug"] == "existing-org"
    finally:
        app.dependency_overrides.clear()


def test_auth_me_switch_active_organization():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="A", slug="org-a", plan_tier="team"))
        db.add(Organization(id=2, name="B", slug="org-b", plan_tier="team"))
        db.flush()
        acc = Account(email="multi@example.com", hashed_password=hash_password("pw"))
        db.add(acc)
        db.flush()
        db.add(User(account_id=acc.id, organization_id=1, role="admin", locale="de"))
        db.add(User(account_id=acc.id, organization_id=2, role="planner", locale="de"))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "multi@example.com", "password": "pw"},
                ).status_code
                == 200
            )
            me = tc.get("/api/v1/auth/me").json()
            assert me["organization_id"] == 1
            assert len(me["memberships"]) == 2
            r2 = tc.post("/api/v1/auth/me/active-organization", json={"organization_slug": "org-b"})
            assert r2.status_code == 200
            me2 = tc.get("/api/v1/auth/me").json()
            assert me2["organization_id"] == 2
            assert me2["role"] == "planner"
            assert tc.post("/api/v1/auth/me/active-organization", json={"organization_slug": "unknown"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_auth_me_add_organization_membership():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Alpha", slug="org-alpha", plan_tier="team"))
        db.add(Organization(id=2, name="Beta", slug="org-beta", plan_tier="team"))
        db.flush()
        acc = Account(email="adder@example.com", hashed_password=hash_password("secret12"))
        db.add(acc)
        db.flush()
        db.add(User(account_id=acc.id, organization_id=1, role="admin", locale="de"))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "adder@example.com", "password": "secret12", "organization_slug": "org-alpha"},
                ).status_code
                == 200
            )
            r_bad = tc.post(
                "/api/v1/auth/me/add-organization-membership",
                json={
                    "organization_slug": "org-beta",
                    "password": "wrong",
                    "first_name": "A",
                    "last_name": "B",
                    "message": None,
                },
            )
            assert r_bad.status_code == 400
            r_same = tc.post(
                "/api/v1/auth/me/add-organization-membership",
                json={
                    "organization_slug": "org-alpha",
                    "password": "secret12",
                    "first_name": "A",
                    "last_name": "B",
                    "message": None,
                },
            )
            assert r_same.status_code == 400
            r_ok = tc.post(
                "/api/v1/auth/me/add-organization-membership",
                json={
                    "organization_slug": "org-beta",
                    "password": "secret12",
                    "first_name": "Join",
                    "last_name": "Er",
                    "message": "hi",
                },
            )
            assert r_ok.status_code == 200
            body = r_ok.json()
            assert body["organization_id"] == 2
            assert body["role"] == "applicant"
            assert body["organization"]["slug"] == "org-beta"
            assert len(body["memberships"]) == 2
            jr = tc.get("/api/v1/auth/me/join-request").json()
            assert jr is not None
            assert jr["status"] == "pending"
            r_dup = tc.post(
                "/api/v1/auth/me/add-organization-membership",
                json={
                    "organization_slug": "org-beta",
                    "password": "secret12",
                    "first_name": "X",
                    "last_name": "Y",
                    "message": None,
                },
            )
            assert r_dup.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_organization_users_list_for_admin(client: TestClient):
    login(client)
    response = client.get("/api/v1/organization/users")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    admin_row = next(r for r in rows if r["email"] == "admin@example.com")
    assert admin_row["role"] == "admin"
    assert admin_row["id"] >= 1
    assert admin_row["is_active"] is True


def test_create_additional_organization_membership_as_admin(client: TestClient):
    login(client)
    response = client.post(
        "/api/v1/auth/me/create-organization-membership",
        json={
            "organization_name": "Fire Department Team",
            "organization_slug": "fire-dept-team",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"
    assert data["organization"]["slug"] == "fire-dept-team"
    assert len(data["memberships"]) == 2
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["organization"]["slug"] == "fire-dept-team"
    assert me_body["role"] == "admin"


def test_organization_users_forbidden_for_team_member(team_member_client: TestClient):
    login_team_member(team_member_client)
    assert team_member_client.get("/api/v1/organization/users").status_code == 403


def test_register_create_organization(client: TestClient):
    response = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "New Hospital",
            "organization_slug": "new-hospital-test",
            "email": "founder@regtest.example",
            "password": "founderpass1",
            "password_confirm": "founderpass1",
            "locale": "en",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"
    assert data["organization"]["slug"] == "new-hospital-test"
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == "founder@regtest.example"


def test_register_create_organization_password_confirm_mismatch(client: TestClient):
    response = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "X",
            "organization_slug": "x-hospital-slug",
            "email": "x@regtest.example",
            "password": "longpass12",
            "password_confirm": "otherpass12",
            "locale": "en",
        },
    )
    assert response.status_code == 422


def test_register_join_organization_password_confirm_mismatch(client: TestClient):
    response = client.post(
        "/api/v1/auth/register/join-organization",
        json={
            "organization_slug": "default",
            "email": "join-mismatch@example.com",
            "password": "joinerpass12",
            "password_confirm": "joinerpass99",
            "first_name": "A",
            "last_name": "B",
            "locale": "de",
        },
    )
    assert response.status_code == 422


def test_register_join_and_approve_create_team_member(client: TestClient):
    r0 = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "Join Flow Org",
            "organization_slug": "join-flow-org",
            "email": "owner@joinflow.example",
            "password": "ownerpass12",
            "password_confirm": "ownerpass12",
            "locale": "de",
        },
    )
    assert r0.status_code == 200
    client.post("/api/v1/auth/logout")
    r1 = client.post(
        "/api/v1/auth/register/join-organization",
        json={
            "organization_slug": "join-flow-org",
            "email": "joiner@joinflow.example",
            "password": "joinerpass12",
            "password_confirm": "joinerpass12",
            "first_name": "Join",
            "last_name": "Er",
            "locale": "de",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["role"] == "applicant"
    client.post("/api/v1/auth/logout")
    login_owner = client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@joinflow.example",
            "password": "ownerpass12",
            "organization_slug": "join-flow-org",
        },
    )
    assert login_owner.status_code == 200
    pending = client.get("/api/v1/organization/join-requests?status=pending").json()
    assert len(pending) == 1
    rid = pending[0]["id"]
    approve = client.post(
        f"/api/v1/organization/join-requests/{rid}/approve-create-team-member",
        json={
            "first_name": "Join",
            "last_name": "Er",
            "email": "joiner@joinflow.example",
            "employment_percentage": 100,
            "shift_group_ids": [],
        },
    )
    assert approve.status_code == 200
    client.post("/api/v1/auth/logout")
    login_joiner = client.post(
        "/api/v1/auth/login",
        json={
            "email": "joiner@joinflow.example",
            "password": "joinerpass12",
            "organization_slug": "join-flow-org",
        },
    )
    assert login_joiner.status_code == 200
    assert login_joiner.json()["role"] == "team_member"
    assert login_joiner.json()["capabilities"]["team_member_portal"] is True


def test_auth_and_team_member_crud(client: TestClient):
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    response = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "employment_percentage": 80},
    )
    assert response.status_code == 200
    assert response.json()["employment_percentage"] == 80
    assert client.get("/api/v1/team-members").json()[0]["email"] == "ada@example.com"


def test_roster_validation_no_go_conflict(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Max",
            "last_name": "Planck",
            "email": "max@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "N",
            "name": "Nachtdienst",
            "category": "other",
        },
    ).json()
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
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    request_date = date(2026, 5, 3).isoformat()
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(slot for slot in roster_matrix["slots"] if slot["slot_date"] == request_date)
    client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": team_member_id, "cell_date": request_date, "status": "frei"},
    )
    client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id},
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert warnings[0]["code"] == "ROSTER_MATRIX_UNAVAILABLE_CONFLICT"


def test_matrix_cell_note_and_csv_export(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Matrix",
            "last_name": "TeamMember",
            "email": "matrix@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]

    response = client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={
            "team_member_id": team_member_id,
            "cell_date": "2026-07-11",
            "status": "urlaub",
            "comment": "Urlaub aus E-Mail",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "urlaub"

    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert matrix["team_members"][0]["email"] == "matrix@example.com"
    assert matrix["cells"][0]["comment"] == "Urlaub aus E-Mail"

    note = client.put(
        f"/api/v1/matrix/{period_id}/notes?shift_group_id=1",
        json={
            "team_member_id": team_member_id,
            "summary": "Urlaub 11.-19.07.",
            "planning_preferences": "Hallo Christian, im Juli Urlaub vom 11.-19.07.",
            "sync_planning_preferences": True,
        },
    )
    assert note.status_code == 200
    assert note.json()["summary"] == "Urlaub 11.-19.07."
    matrix_after = client.get(f"/api/v1/matrix/{period_id}").json()
    assert matrix_after["team_members"][0]["planning_preferences"] == "Hallo Christian, im Juli Urlaub vom 11.-19.07."

    csv_response = client.get(f"/api/v1/exports/matrix/{period_id}.csv")
    assert csv_response.status_code == 200
    assert "2026-07-11" in csv_response.text
    assert "urlaub - Urlaub aus E-Mail" in csv_response.text


def test_matrix_bulk_upsert_and_clear(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Bulk",
            "last_name": "TeamMember",
            "email": "bulk@example.com",
            "employment_percentage": 80,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]

    response = client.put(
        f"/api/v1/matrix/{period_id}/cells/bulk?shift_group_id=1",
        json={
            "cells": [
                {"team_member_id": team_member_id, "cell_date": "2026-08-01", "status": "frei"},
                {
                    "team_member_id": team_member_id,
                    "cell_date": "2026-08-02",
                    "status": "lehre",
                    "comment": "Wochenendkombination",
                },
            ]
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 2

    clear_response = client.post(
        f"/api/v1/matrix/{period_id}/cells/clear?shift_group_id=1",
        json={"team_member_id": team_member_id, "cell_date": "2026-08-01"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted"] is True

    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert len(matrix["cells"]) == 1
    assert matrix["cells"][0]["status"] == "lehre"


def test_roster_matrix_assignment_validation_and_csv(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Roster",
            "last_name": "TeamMember",
            "email": "roster@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "T",
            "name": "Tagdienst",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tagdienst",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]

    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert roster_matrix["shift_templates"][0]["code"] == "T"
    assert len(roster_matrix["slots"]) == 31
    slot = next(slot for slot in roster_matrix["slots"] if slot["slot_date"] == "2026-07-11")

    assignment_response = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id, "comment": "final geplant"},
    )
    assert assignment_response.status_code == 200
    assert assignment_response.json()["team_member_id"] == team_member_id

    client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": team_member_id, "cell_date": "2026-07-11", "status": "urlaub"},
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert warnings[0]["code"] == "ROSTER_MATRIX_UNAVAILABLE_CONFLICT"

    csv_response = client.get(f"/api/v1/exports/roster-matrix/{period_id}.csv")
    assert csv_response.status_code == 200
    assert "2026-07-11" in csv_response.text
    assert "Tagdienst" in csv_response.text
    assert "TeamMember" in csv_response.text
    assert "final geplant" not in csv_response.text

    clear_response = client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted"] is True


def test_roster_matrix_published_xlsx_pdf_exports(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Export",
            "last_name": "Member",
            "email": "export-member@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "EX",
            "name": "Exportdienst",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tagdienst",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    slot = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"][0]
    assign = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": team_member_id, "manual_override": False},
    )
    assert assign.status_code == 200

    denied = client.get(f"/api/v1/exports/roster-matrix/{period_id}.xlsx?shift_group_id=1")
    assert denied.status_code == 403

    assert client.post(f"/api/v1/planning-periods/{period_id}/preliminary?shift_group_id=1").status_code == 200

    preliminary_xlsx = client.get(f"/api/v1/exports/roster-matrix/{period_id}.xlsx?shift_group_id=1")
    assert preliminary_xlsx.status_code == 200
    assert preliminary_xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    preliminary_pdf = client.get(f"/api/v1/exports/roster-matrix/{period_id}.pdf?shift_group_id=1")
    assert preliminary_pdf.status_code == 200
    assert preliminary_pdf.headers["content-type"].startswith("application/pdf")
    assert preliminary_pdf.content.startswith(b"%PDF")

    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200

    xlsx = client.get(f"/api/v1/exports/roster-matrix/{period_id}.xlsx?shift_group_id=1")
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert f'attachment; filename="roster-matrix-{period_id}.xlsx"' == xlsx.headers["content-disposition"]
    assert xlsx.content.startswith(b"PK")

    pdf = client.get(f"/api/v1/exports/roster-matrix/{period_id}.pdf?shift_group_id=1")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert f'attachment; filename="roster-matrix-{period_id}.pdf"' == pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF")


def test_create_shift_template_rejects_duplicate_code(client: TestClient):
    login(client)
    body = {"code": "DUPX", "name": "Eins", "category": "other"}
    assert client.post("/api/v1/shift-templates", json=body).status_code == 200
    conflict = client.post("/api/v1/shift-templates", json={**body, "name": "Zwei"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SHIFT_TEMPLATE_CODE_TAKEN"
    assert conflict.json()["detail"]["value"] == "DUPX"


def test_patch_shift_template_rejects_duplicate_code(client: TestClient):
    login(client)
    first = client.post(
        "/api/v1/shift-templates",
        json={"code": "P1", "name": "a", "category": "other"},
    ).json()
    client.post(
        "/api/v1/shift-templates",
        json={"code": "P2", "name": "b", "category": "other"},
    )
    conflict = client.patch(f"/api/v1/shift-templates/{first['id']}", json={"code": "P2"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SHIFT_TEMPLATE_CODE_TAKEN"


def test_shift_template_variants_holidays_and_generated_slots(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "BD",
            "name": "Bereitschaftsdienst",
            "category": "bereitschaftsdienst",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Wochentag",
            "start_day_class": "weekday",
            "end_day_class": "weekend",
            "starts_at": "15:45:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Wochenende Nacht",
            "start_day_class": "weekend",
            "starts_at": "20:00:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 2,
        },
    )
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Feiertag Nacht",
            "start_day_class": "holiday",
            "starts_at": "20:00:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 5}).json()
    holiday_slots = [slot for slot in preview if slot["slot_date"] == "2026-05-01"]
    assert holiday_slots
    assert holiday_slots[0]["day_class"] == "holiday"
    assert [slot["variant_label"] for slot in holiday_slots] == ["Feiertag Nacht"]

    saturday_slots = [
        slot for slot in preview if slot["slot_date"] == "2026-05-02" and slot["variant_label"] == "Wochenende Nacht"
    ]
    assert len(saturday_slots) == 2

    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    generated = [slot for slot in roster_matrix["slots"] if slot["slot_date"] == "2026-05-01"]
    assert generated[0]["starts_at"]
    assert generated[0]["template_code"] == "BD"


def test_regenerate_roster_slots_clears_assignments_and_updates_slots(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Reset", "last_name": "TeamMember", "email": "reset@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "RESET",
            "name": "Resetdienst",
            "category": "other",
        },
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert len(roster_matrix["slots"]) == 30
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": team_member_id})

    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={"required_count": 2},
    )
    regenerated = client.post(f"/api/v1/planning-periods/{period_id}/regenerate-roster")
    assert regenerated.status_code == 200
    regenerated_json = regenerated.json()
    assert len(regenerated_json["slots"]) == 60
    assert regenerated_json["assignments"] == []


def test_delete_shift_variant_clears_generated_slots_and_assignments(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Variant", "last_name": "Delete", "email": "variant-delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "VD",
            "name": "Variantendienst",
            "category": "other",
        },
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": team_member_id})

    delete_response = client.delete(f"/api/v1/shift-templates/variants/{variant['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    templates = client.get("/api/v1/shift-templates").json()
    updated_template = next(item for item in templates if item["id"] == template["id"])
    assert updated_template["variants"] == []

    next_roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert next_roster_matrix["slots"] == []
    assert next_roster_matrix["assignments"] == []


def test_shift_template_constraint_payload_roundtrip(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "CONS",
            "name": "Constraint Dienst",
            "category": "other",
            "constraints": [{"type": "no_additional_same_day", "severity": "error"}],
        },
    )
    assert template.status_code == 200
    assert template.json()["constraints"][0]["type"] == "no_additional_same_day"
    assert template.json()["constraints"][0]["severity"] == "error"
    variant = client.post(
        f"/api/v1/shift-templates/{template.json()['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
            "constraints": [{"type": "min_rest_hours", "severity": "warning", "min_rest_hours": 11}],
        },
    )
    assert variant.status_code == 200
    assert variant.json()["constraints"][0]["type"] == "min_rest_hours"
    patched_template = client.patch(
        f"/api/v1/shift-templates/{template.json()['id']}",
        json={"constraints": [{"type": "no_cross_day_into_unavailable_day", "severity": "info"}]},
    )
    assert patched_template.status_code == 200
    patched_variant = client.patch(
        f"/api/v1/shift-templates/variants/{variant.json()['id']}",
        json={"constraints": [{"type": "min_rest_hours", "severity": "error", "min_rest_hours": 12}]},
    )
    assert patched_variant.status_code == 200
    templates = client.get("/api/v1/shift-templates").json()
    row = next(item for item in templates if item["id"] == template.json()["id"])
    assert row["constraints"][0]["type"] == "no_cross_day_into_unavailable_day"
    assert row["variants"][0]["constraints"][0]["severity"] == "error"


def test_shift_template_constraint_legacy_enforcement_maps_to_severity(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "LEGY",
            "name": "Legacy",
            "category": "other",
            "constraints": [{"type": "no_additional_same_day", "enforcement": "block"}],
        },
    )
    assert template.status_code == 200
    assert template.json()["constraints"][0]["severity"] == "error"
    assert "enforcement" not in template.json()["constraints"][0]


def test_roster_assignment_allowed_when_same_day_constraint_is_info(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Info", "last_name": "Rule", "email": "info-rule@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "RINF", "name": "Regel", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 2,
            "constraints": [{"type": "no_additional_same_day", "severity": "info"}],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slots = [slot for slot in roster["slots"] if slot["slot_date"] == "2026-08-01" and slot["shift_template_id"] == template["id"]]
    assert len(slots) == 2
    assert client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slots[0]["id"], "team_member_id": member_id},
    ).status_code == 200
    second = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slots[1]["id"], "team_member_id": member_id},
    )
    assert second.status_code == 200


def test_roster_assignment_blocked_by_same_day_constraint(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Rule", "last_name": "Block", "email": "rule-block@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "RBLK", "name": "Regel", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 2,
            "constraints": [{"type": "no_additional_same_day", "severity": "error"}],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slots = [slot for slot in roster["slots"] if slot["slot_date"] == "2026-07-01" and slot["shift_template_id"] == template["id"]]
    assert len(slots) == 2
    first = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slots[0]["id"], "team_member_id": member_id},
    )
    assert first.status_code == 200
    blocked = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slots[1]["id"], "team_member_id": member_id},
    )
    assert blocked.status_code == 400
    assert "no additional shift assignments" in blocked.json()["detail"].lower()


def test_validation_warns_for_cross_day_unavailable_constraint(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Cross",
            "last_name": "Day",
            "email": "cross-day@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1],
        },
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "CRS", "name": "Nacht", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Nacht",
            "start_day_class": "any",
            "starts_at": "20:00:00",
            "ends_at": "06:00:00",
            "end_day_offset": 1,
            "required_count": 1,
            "constraints": [{"type": "no_cross_day_into_unavailable_day", "severity": "warning"}],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": member_id, "cell_date": "2026-07-02", "status": "urlaub"},
    )
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(row for row in roster["slots"] if row["slot_date"] == "2026-07-01" and row["shift_template_id"] == template["id"])
    assigned = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": member_id},
    )
    assert assigned.status_code == 200
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert any(row["code"] == "ROSTER_CONSTRAINT_CROSS_DAY_UNAVAILABLE" for row in warnings)


def test_validation_warns_for_max_assignments_per_month_constraint(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Limit", "last_name": "Monthly", "email": "limit-monthly@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "MMAX", "name": "Limit", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tag",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 3,
            "constraints": [
                {"type": "max_assignments_per_month", "severity": "warning", "max_assignments_per_month": 2}
            ],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slots = [row for row in roster["slots"] if row["slot_date"] == "2026-07-01" and row["shift_template_id"] == template["id"]]
    assert len(slots) == 3
    for slot in slots:
        assigned = client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": slot["id"], "team_member_id": member_id},
        )
        assert assigned.status_code == 200
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    max_rows = [row for row in warnings if row["code"] == "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH"]
    assert len(max_rows) == 1
    assert max_rows[0]["team_member_id"] == member_id
    assert max_rows[0]["date"] is None
    vids = max_rows[0]["details"].get("violating_roster_slot_ids")
    assert isinstance(vids, list) and len(vids) == 3


def test_shift_coupling_constraint_rejects_self_paired_variant(client: TestClient):
    login(client)
    t1 = client.post(
        "/api/v1/shift-templates",
        json={"code": "CSEL", "name": "Csel", "category": "other"},
    ).json()
    v1 = client.post(
        f"/api/v1/shift-templates/{t1['id']}/variants",
        json={
            "label": "Solo",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    bad = client.patch(
        f"/api/v1/shift-templates/variants/{v1['id']}",
        json={
            "constraints": [
                {
                    "type": "requires_coupled_shift",
                    "severity": "warning",
                    "paired_shift_variant_id": v1["id"],
                    "partner_day_offset": 1,
                }
            ]
        },
    )
    assert bad.status_code == 400


def test_validation_warns_when_shift_coupling_partner_missing(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Coup", "last_name": "Warn", "email": "coupling-warn@example.com", "employment_percentage": 100},
    ).json()["id"]
    t_plate = client.post(
        "/api/v1/shift-templates",
        json={"code": "CPLW", "name": "Koppel", "category": "other"},
    ).json()
    v_early = client.post(
        f"/api/v1/shift-templates/{t_plate['id']}/variants",
        json={
            "label": "Early",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "12:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    v_late = client.post(
        f"/api/v1/shift-templates/{t_plate['id']}/variants",
        json={
            "label": "Late",
            "start_day_class": "any",
            "starts_at": "18:00:00",
            "ends_at": "22:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    assert (
        client.patch(
            f"/api/v1/shift-templates/variants/{v_early['id']}",
            json={
                "constraints": [
                    {
                        "type": "requires_coupled_shift",
                        "severity": "warning",
                        "paired_shift_variant_id": v_late["id"],
                        "partner_day_offset": 1,
                    }
                ]
            },
        ).status_code
        == 200
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot_early = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-07-10" and row["shift_variant_id"] == v_early["id"]
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": slot_early["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    coup = [row for row in warnings if row["code"] == "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED"]
    assert len(coup) == 1
    assert coup[0]["severity"] == "warning"


def test_roster_assignment_blocked_when_shift_coupling_error_without_partner(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Coup", "last_name": "Block", "email": "coupling-block@example.com", "employment_percentage": 100},
    ).json()["id"]
    t_plate = client.post(
        "/api/v1/shift-templates",
        json={"code": "CPLB", "name": "Koppel", "category": "other"},
    ).json()
    v_early = client.post(
        f"/api/v1/shift-templates/{t_plate['id']}/variants",
        json={
            "label": "Early",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "12:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    v_late = client.post(
        f"/api/v1/shift-templates/{t_plate['id']}/variants",
        json={
            "label": "Late",
            "start_day_class": "any",
            "starts_at": "18:00:00",
            "ends_at": "22:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    assert (
        client.patch(
            f"/api/v1/shift-templates/variants/{v_early['id']}",
            json={
                "constraints": [
                    {
                        "type": "requires_coupled_shift",
                        "severity": "error",
                        "paired_shift_variant_id": v_late["id"],
                        "partner_day_offset": 1,
                    }
                ]
            },
        ).status_code
        == 200
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot_early = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-07-15" and row["shift_variant_id"] == v_early["id"]
    )
    blocked = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot_early["id"], "team_member_id": member_id},
    )
    assert blocked.status_code == 400


def test_roster_property_requirement_warning_allows_assign_and_surfaces_in_validation(client: TestClient):
    login(client)
    defn = client.post(
        "/api/v1/team-member-property-definitions",
        json={"name": "Training year", "type": "number"},
    ).json()
    member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Prop",
            "last_name": "ReqWarn",
            "email": "prop-req-warn@example.com",
            "employment_percentage": 100,
        },
    ).json()["id"]
    assert (
        client.put(
            f"/api/v1/team-members/{member_id}/property-values",
            json={"values": [{"property_definition_id": defn["id"], "value": 1}]},
        ).status_code
        == 200
    )
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "PREW", "name": "PropReq", "category": "other"},
    ).json()
    prop_req = {
        "type": "team_member_property_requirement",
        "severity": "warning",
        "property_requirement": {
            "kind": "all",
            "items": [
                {
                    "kind": "atom",
                    "property_definition_id": defn["id"],
                    "op": "gte",
                    "value": 3,
                }
            ],
        },
    }
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Main",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
            "constraints": [prop_req],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2027, "month": 4}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(
        row for row in roster["slots"] if row["slot_date"] == "2027-04-01" and row["shift_template_id"] == template["id"]
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": slot["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    hits = [w for w in warnings if w["code"] == "ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "warning"


def test_roster_property_requirement_error_blocks_assignment(client: TestClient):
    login(client)
    defn = client.post(
        "/api/v1/team-member-property-definitions",
        json={"name": "Seniority", "type": "number"},
    ).json()
    member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Prop",
            "last_name": "ReqBlock",
            "email": "prop-req-block@example.com",
            "employment_percentage": 100,
        },
    ).json()["id"]
    assert (
        client.put(
            f"/api/v1/team-members/{member_id}/property-values",
            json={"values": [{"property_definition_id": defn["id"], "value": 1}]},
        ).status_code
        == 200
    )
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "PREQ", "name": "Block", "category": "other"},
    ).json()
    prop_req = {
        "type": "team_member_property_requirement",
        "severity": "error",
        "property_requirement": {
            "kind": "atom",
            "property_definition_id": defn["id"],
            "op": "gte",
            "value": 5,
        },
    }
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Senior",
            "start_day_class": "any",
            "starts_at": "09:00:00",
            "ends_at": "17:00:00",
            "end_day_offset": 0,
            "required_count": 1,
            "constraints": [prop_req],
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2027, "month": 5}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(
        row for row in roster["slots"] if row["slot_date"] == "2027-05-01" and row["shift_template_id"] == template["id"]
    )
    blocked = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": member_id},
    )
    assert blocked.status_code == 400


def test_validation_warns_consecutive_weekend_roster_assignments(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Week", "last_name": "Pair", "email": "week-pair@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "WEKP", "name": "Wochenende", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Any",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    sid_mar7 = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-03-07" and row["shift_template_id"] == template["id"]
    )
    sid_mar14 = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-03-14" and row["shift_template_id"] == template["id"]
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": sid_mar7["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": sid_mar14["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    cons = [w for w in warnings if w["code"] == "ROSTER_CONSECUTIVE_WEEKENDS"]
    assert len(cons) == 1
    assert cons[0]["team_member_id"] == member_id
    pairs = cons[0]["details"].get("pairs")
    assert isinstance(pairs, list) and len(pairs) >= 1


def test_validation_no_consecutive_weekend_when_weekends_not_adjacent(client: TestClient):
    login(client)
    member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Week", "last_name": "Skip", "email": "week-skip@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "WEKS", "name": "Wochenende", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Any",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3}).json()["id"]
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    sid_mar7 = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-03-07" and row["shift_template_id"] == template["id"]
    )
    sid_mar21 = next(
        row
        for row in roster["slots"]
        if row["slot_date"] == "2026-03-21" and row["shift_template_id"] == template["id"]
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": sid_mar7["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/roster-matrix/assignments",
            json={"roster_slot_id": sid_mar21["id"], "team_member_id": member_id},
        ).status_code
        == 200
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert not any(w["code"] == "ROSTER_CONSECUTIVE_WEEKENDS" for w in warnings)


def test_delete_planning_period_removes_period_and_related_data(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Delete", "last_name": "TeamMember", "email": "delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": team_member_id, "cell_date": "2026-10-01", "status": "urlaub"},
    )
    client.put(
        f"/api/v1/matrix/{period_id}/notes",
        json={
            "team_member_id": team_member_id,
            "summary": "Zusammenfassung",
            "planning_preferences": "Quelle",
            "sync_planning_preferences": True,
        },
    )

    delete_response = client.delete(f"/api/v1/planning-periods/{period_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert all(period["id"] != period_id for period in client.get("/api/v1/planning-periods").json())
    assert client.get(f"/api/v1/roster-matrix/{period_id}").status_code == 404


def test_delete_shift_template_clears_generated_slots_and_assignments(client: TestClient):
    login(client)
    team_member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Template", "last_name": "Delete", "email": "template-delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "DEL",
            "name": "Löschdienst",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 11}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": team_member_id})

    delete_response = client.delete(f"/api/v1/shift-templates/{template['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert all(item["id"] != template["id"] for item in client.get("/api/v1/shift-templates").json())
    next_roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert next_roster_matrix["slots"] == []
    assert next_roster_matrix["assignments"] == []


def test_delete_team_member_clears_related_data(client: TestClient):
    login(client)
    created = client.post(
        "/api/v1/team-members",
        json={"first_name": "Purge", "last_name": "TeamMember", "email": "purge@example.com", "employment_percentage": 80},
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 12}).json()["id"]
    client.put(
        f"/api/v1/matrix/{period_id}/cells?shift_group_id=1",
        json={"team_member_id": created["id"], "cell_date": "2026-12-01", "status": "urlaub"},
    )
    client.put(
        f"/api/v1/matrix/{period_id}/notes",
        json={
            "team_member_id": created["id"],
            "summary": "summary",
            "planning_preferences": "mail",
            "sync_planning_preferences": True,
        },
    )

    delete_response = client.delete(f"/api/v1/team-members/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    members = client.get("/api/v1/team-members").json()
    assert all(item["id"] != created["id"] for item in members)
    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert matrix["cells"] == []
    notes = client.get(f"/api/v1/matrix/{period_id}/notes").json()
    assert notes == []


def test_shift_group_filters_matrix_and_assignment_eligibility(client: TestClient):
    login(client)
    member_in = client.post(
        "/api/v1/team-members",
        json={"first_name": "In", "last_name": "Group", "email": "ingroup@example.com", "employment_percentage": 100},
    ).json()
    member_out = client.post(
        "/api/v1/team-members",
        json={"first_name": "Out", "last_name": "Group", "email": "outgroup@example.com", "employment_percentage": 100},
    ).json()
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "SGT", "name": "Sg Test", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Slot",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    group = client.post(
        "/api/v1/shift-groups",
        json={"code": "SG", "name": "Gruppe", "display_order": 0},
    ).json()
    gid = group["id"]
    client.put(f"/api/v1/shift-groups/{gid}/team-members", json={"team_member_ids": [member_in["id"]]})
    client.put(f"/api/v1/shift-groups/{gid}/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3}).json()["id"]
    full = client.get(f"/api/v1/matrix/{period_id}").json()
    assert len(full["team_members"]) == 2
    assert len(full["shift_templates"]) == 1
    assert len(full["template_slot_days"]) > 0
    filtered = client.get(f"/api/v1/matrix/{period_id}?shift_group_id={gid}").json()
    assert len(filtered["team_members"]) == 1
    assert filtered["team_members"][0]["id"] == member_in["id"]
    assert len(filtered["shift_templates"]) == 1
    assert filtered["shift_templates"][0]["id"] == template["id"]
    assert len(filtered["template_slot_days"]) > 0
    assert filtered["shift_intents"] == []
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(s for s in roster["slots"] if s["shift_template_id"] == template["id"])
    bad = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": member_out["id"]})
    assert bad.status_code == 400
    good = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": member_in["id"]})
    assert good.status_code == 200
    intent_put = client.put(
        f"/api/v1/matrix/{period_id}/shift-intents/bulk",
        json={
            "intents": [
                {
                    "team_member_id": member_in["id"],
                    "cell_date": slot["slot_date"],
                    "shift_group_id": gid,
                    "shift_template_id": template["id"],
                    "kind": "no_go",
                }
            ]
        },
    )
    assert intent_put.status_code == 200
    warnings_conflict = client.get(f"/api/v1/validation/{period_id}").json()
    assert any(warning["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT" for warning in warnings_conflict)
    client.put("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    denied = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "team_member_id": member_in["id"]})
    assert denied.status_code == 400
    override = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": member_in["id"], "manual_override": True},
    )
    assert override.status_code == 200
    warnings_after = client.get(f"/api/v1/validation/{period_id}").json()
    assert all(warning["code"] != "ROSTER_TEMPLATE_NO_GO_CONFLICT" for warning in warnings_after)


def test_planning_period_status_transitions(client: TestClient):
    login(client)
    pid = client.post("/api/v1/planning-periods", json={"year": 2028, "month": 1}).json()["id"]
    to_preliminary = client.post(f"/api/v1/planning-periods/{pid}/preliminary?shift_group_id=1")
    assert to_preliminary.status_code == 200
    assert to_preliminary.json()["status"] == "preliminary"
    assert to_preliminary.json().get("published_at") is None

    pub = client.post(f"/api/v1/planning-periods/{pid}/publish?shift_group_id=1")
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"
    assert pub.json().get("published_at") is not None

    rollback = client.post(f"/api/v1/planning-periods/{pid}/preliminary?shift_group_id=1")
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "preliminary"
    assert rollback.json().get("published_at") is None

    to_draft = client.post(f"/api/v1/planning-periods/{pid}/draft?shift_group_id=1")
    assert to_draft.status_code == 200
    assert to_draft.json()["status"] == "draft"
    assert to_draft.json().get("published_at") is None


def test_publish_one_shift_group_leaves_other_unchanged(client: TestClient):
    login(client)
    second_group = client.post(
        "/api/v1/shift-groups",
        json={"code": "sg_b", "name": "Group B", "display_order": 1, "is_active": True},
    ).json()
    pid = client.post("/api/v1/planning-periods", json={"year": 2029, "month": 3}).json()["id"]
    assert client.post(f"/api/v1/planning-periods/{pid}/publish?shift_group_id=1").status_code == 200
    period = next(row for row in client.get("/api/v1/planning-periods").json() if row["id"] == pid)
    statuses = {row["shift_group_id"]: row["status"] for row in period["shift_group_statuses"]}
    assert statuses[1] == "published"
    assert statuses[second_group["id"]] == "draft"


def test_wishes_cells_isolated_per_shift_group(client: TestClient):
    login(client)
    second_group = client.post(
        "/api/v1/shift-groups",
        json={"code": "sg_two", "name": "Group Two", "display_order": 2, "is_active": True},
    ).json()
    member_id = client.post(
        "/api/v1/team-members",
        json={
            "first_name": "Iso",
            "last_name": "Lated",
            "email": "iso@example.com",
            "employment_percentage": 100,
            "shift_group_ids": [1, second_group["id"]],
        },
    ).json()["id"]
    pid = client.post("/api/v1/planning-periods", json={"year": 2029, "month": 4}).json()["id"]
    assert (
        client.put(
            f"/api/v1/matrix/{pid}/cells?shift_group_id=1",
            json={"team_member_id": member_id, "cell_date": "2029-04-01", "status": "urlaub"},
        ).status_code
        == 200
    )
    matrix_b = client.get(f"/api/v1/matrix/{pid}?shift_group_id={second_group['id']}").json()
    assert matrix_b["cells"] == []
    matrix_a = client.get(f"/api/v1/matrix/{pid}?shift_group_id=1").json()
    assert len(matrix_a["cells"]) == 1
    assert matrix_a["cells"][0]["status"] == "urlaub"


def test_team_member_shift_templates_forbidden(team_member_client: TestClient):
    login_team_member(team_member_client)
    assert team_member_client.get("/api/v1/shift-templates").status_code == 403


@pytest.fixture()
def planner_client():
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
        planner_user = _seed_membership(db, "planner@example.com", "plannersecret", 1, ROLE_PLANNER)
        db.flush()
        sg = ShiftGroup(organization_id=1, code="sg1", name="SG", display_order=0)
        db.add(sg)
        db.flush()
        db.add(UserShiftGroup(user_id=planner_user.id, shift_group_id=sg.id))
        ingroup_member = TeamMember(
            organization_id=1,
            first_name="In",
            last_name="Group",
            email="ingroup@example.com",
            employment_percentage=100,
        )
        db.add(ingroup_member)
        db.flush()
        db.add(TeamMemberShiftGroup(team_member_id=ingroup_member.id, shift_group_id=sg.id))
        other = TeamMember(
            organization_id=1,
            first_name="Out",
            last_name="Group",
            email="outgroup@example.com",
            employment_percentage=100,
        )
        db.add(other)
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


def login_planner(cl: TestClient) -> None:
    response = cl.post(
        "/api/v1/auth/login",
        json={
            "email": "planner@example.com",
            "password": "plannersecret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def test_planner_cannot_post_shift_template(planner_client: TestClient):
    login_planner(planner_client)
    response = planner_client.post(
        "/api/v1/shift-templates",
        json={"code": "X", "name": "X", "category": "other"},
    )
    assert response.status_code == 403


def test_planner_cannot_post_planning_period(planner_client: TestClient):
    login_planner(planner_client)
    response = planner_client.post("/api/v1/planning-periods", json={"year": 2050, "month": 1})
    assert response.status_code == 403


def test_planner_team_members_list_scoped(planner_client: TestClient):
    login_planner(planner_client)
    members = planner_client.get("/api/v1/team-members").json()
    assert len(members) == 1
    assert members[0]["email"] == "ingroup@example.com"


def test_planner_matrix_requires_shift_group(planner_client: TestClient):
    login(planner_client)
    pid = planner_client.post("/api/v1/planning-periods", json={"year": 2040, "month": 1}).json()["id"]
    login_planner(planner_client)
    assert planner_client.get(f"/api/v1/matrix/{pid}").status_code == 403
    assert planner_client.get(f"/api/v1/matrix/{pid}?shift_group_id=1").status_code == 200


def test_team_member_matrix_requires_shift_group(team_member_client: TestClient):
    login(team_member_client)
    pid = team_member_client.post("/api/v1/planning-periods", json={"year": 2030, "month": 1}).json()["id"]
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/matrix/{pid}").status_code == 400
    matrix = team_member_client.get(f"/api/v1/matrix/{pid}?shift_group_id=1")
    assert matrix.status_code == 200
    body = matrix.json()
    assert len(body["team_members"]) == 1
    assert body["team_members"][0]["id"] == 1


def test_team_member_roster_requires_preliminary_or_published(team_member_client: TestClient):
    login(team_member_client)
    pid = team_member_client.post("/api/v1/planning-periods", json={"year": 2031, "month": 1}).json()["id"]
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 403
    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/preliminary?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 200
    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/publish?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 200
    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/draft?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 403


def test_team_member_published_roster_binary_export_requires_scope(team_member_client: TestClient):
    login(team_member_client)
    template = team_member_client.post(
        "/api/v1/shift-templates",
        json={
            "code": "TMPDF",
            "name": "Teamdienst",
            "category": "other",
        },
    ).json()
    team_member_client.post(
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
    pid = team_member_client.post("/api/v1/planning-periods", json={"year": 2032, "month": 1}).json()["id"]
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/preliminary?shift_group_id=1").status_code == 200

    login_team_member(team_member_client)
    no_scope = team_member_client.get(f"/api/v1/exports/roster-matrix/{pid}.xlsx?team_member_portal=true")
    assert no_scope.status_code == 400
    ok = team_member_client.get(
        f"/api/v1/exports/roster-matrix/{pid}.xlsx?team_member_portal=true&shift_group_id=1"
    )
    assert ok.status_code == 200
    assert ok.content.startswith(b"PK")

    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/draft?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    denied = team_member_client.get(
        f"/api/v1/exports/roster-matrix/{pid}.pdf?team_member_portal=true&shift_group_id=1"
    )
    assert denied.status_code == 403


def test_team_member_wishes_editable_in_draft_and_preliminary_not_published(team_member_client: TestClient):
    login(team_member_client)
    pid = team_member_client.post("/api/v1/planning-periods", json={"year": 2033, "month": 1}).json()["id"]
    login_team_member(team_member_client)

    draft_cell = team_member_client.put(
        f"/api/v1/matrix/{pid}/cells?shift_group_id=1",
        json={"team_member_id": 1, "cell_date": "2033-01-01", "status": "frei", "comment": "draft"},
    )
    assert draft_cell.status_code == 200
    draft_note = team_member_client.put(
        f"/api/v1/matrix/{pid}/notes?shift_group_id=1",
        json={"team_member_id": 1, "summary": "month draft"},
    )
    assert draft_note.status_code == 200

    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/preliminary?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    allowed = team_member_client.put(
        f"/api/v1/matrix/{pid}/cells?shift_group_id=1",
        json={"team_member_id": 1, "cell_date": "2033-01-01", "status": "frei", "comment": "preliminary"},
    )
    assert allowed.status_code == 200
    note_allowed = team_member_client.put(
        f"/api/v1/matrix/{pid}/notes?shift_group_id=1",
        json={"team_member_id": 1, "summary": "month comment"},
    )
    assert note_allowed.status_code == 200

    login(team_member_client)
    assert team_member_client.post(f"/api/v1/planning-periods/{pid}/publish?shift_group_id=1").status_code == 200
    login_team_member(team_member_client)
    denied_published = team_member_client.put(
        f"/api/v1/matrix/{pid}/cells?shift_group_id=1",
        json={"team_member_id": 1, "cell_date": "2033-01-02", "status": "frei", "comment": "published"},
    )
    assert denied_published.status_code == 403
    denied_note_published = team_member_client.put(
        f"/api/v1/matrix/{pid}/notes?shift_group_id=1",
        json={"team_member_id": 1, "summary": "after publish"},
    )
    assert denied_note_published.status_code == 403


def test_planner_published_roster_binary_exports_require_shift_group(planner_client: TestClient):
    login(planner_client)
    template = planner_client.post(
        "/api/v1/shift-templates",
        json={
            "code": "PLX",
            "name": "Planerdienst",
            "category": "other",
        },
    ).json()
    planner_client.post(
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
    pid = planner_client.post("/api/v1/planning-periods", json={"year": 2041, "month": 1}).json()["id"]
    assert planner_client.post(f"/api/v1/planning-periods/{pid}/publish?shift_group_id=1").status_code == 200

    login_planner(planner_client)
    assert planner_client.get(f"/api/v1/exports/roster-matrix/{pid}.xlsx").status_code == 403
    scoped = planner_client.get(f"/api/v1/exports/roster-matrix/{pid}.xlsx?shift_group_id=1")
    assert scoped.status_code == 200
    assert scoped.content.startswith(b"PK")


def test_admin_delete_organization_user_removes_joiner(client: TestClient):
    r0 = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "Delete User Org",
            "organization_slug": "delete-user-org",
            "email": "owner-del@example.com",
            "password": "ownerdelpass1",
            "password_confirm": "ownerdelpass1",
            "locale": "de",
        },
    )
    assert r0.status_code == 200
    client.post("/api/v1/auth/logout")
    r1 = client.post(
        "/api/v1/auth/register/join-organization",
        json={
            "organization_slug": "delete-user-org",
            "email": "joiner-del@example.com",
            "password": "joinerdelpass1",
            "password_confirm": "joinerdelpass1",
            "first_name": "Del",
            "last_name": "Joiner",
            "locale": "de",
        },
    )
    assert r1.status_code == 200
    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner-del@example.com",
                "password": "ownerdelpass1",
                "organization_slug": "delete-user-org",
            },
        ).status_code
        == 200
    )
    pending = client.get("/api/v1/organization/join-requests?status=pending").json()
    rid = pending[0]["id"]
    assert (
        client.post(
            f"/api/v1/organization/join-requests/{rid}/approve-create-team-member",
            json={
                "first_name": "Del",
                "last_name": "Joiner",
                "email": "joiner-del@example.com",
                "employment_percentage": 100,
                "shift_group_ids": [],
            },
        ).status_code
        == 200
    )
    users = client.get("/api/v1/organization/users").json()
    joiner = next(u for u in users if u["email"] == "joiner-del@example.com")
    assert client.delete(f"/api/v1/organization/users/{joiner['id']}").status_code == 204
    users2 = client.get("/api/v1/organization/users").json()
    assert not any(u["email"] == "joiner-del@example.com" for u in users2)


def test_admin_delete_own_organization_user_rejected(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    response = client.delete(f"/api/v1/organization/users/{me['id']}")
    assert response.status_code == 400


def test_admin_reset_user_password(team_member_client: TestClient):
    login(team_member_client)
    uid = next(
        u["id"]
        for u in team_member_client.get("/api/v1/organization/users").json()
        if u["email"] == "doc@example.com"
    )
    assert (
        team_member_client.post(
            f"/api/v1/organization/users/{uid}/reset-password",
            json={"password": "resetpass9", "password_confirm": "resetpass9"},
        ).status_code
        == 204
    )
    team_member_client.post("/api/v1/auth/logout")
    assert (
        team_member_client.post(
            "/api/v1/auth/login",
            json={"email": "doc@example.com", "password": "resetpass9"},
        ).status_code
        == 200
    )


def test_admin_reset_own_password_rejected(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    response = client.post(
        f"/api/v1/organization/users/{me['id']}/reset-password",
        json={"password": "newpass12", "password_confirm": "newpass12"},
    )
    assert response.status_code == 400


def test_team_member_cannot_reset_password(team_member_client: TestClient):
    login_team_member(team_member_client)
    response = team_member_client.post(
        "/api/v1/organization/users/1/reset-password",
        json={"password": "newpass12", "password_confirm": "newpass12"},
    )
    assert response.status_code == 403


def test_reset_password_confirm_mismatch(team_member_client: TestClient):
    login(team_member_client)
    uid = next(
        u["id"]
        for u in team_member_client.get("/api/v1/organization/users").json()
        if u["email"] == "doc@example.com"
    )
    response = team_member_client.post(
        f"/api/v1/organization/users/{uid}/reset-password",
        json={"password": "newpass12", "password_confirm": "otherpass12"},
    )
    assert response.status_code == 422


def test_change_password(client: TestClient):
    login(client)
    assert (
        client.post(
            "/api/v1/auth/me/change-password",
            json={
                "current_password": "secret",
                "password": "newsecret1",
                "password_confirm": "newsecret1",
            },
        ).status_code
        == 204
    )
    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "newsecret1"},
        ).status_code
        == 200
    )


def test_change_password_wrong_current(client: TestClient):
    login(client)
    response = client.post(
        "/api/v1/auth/me/change-password",
        json={
            "current_password": "wrong",
            "password": "newsecret1",
            "password_confirm": "newsecret1",
        },
    )
    assert response.status_code == 400


def test_change_password_confirm_mismatch(client: TestClient):
    login(client)
    response = client.post(
        "/api/v1/auth/me/change-password",
        json={
            "current_password": "secret",
            "password": "newsecret1",
            "password_confirm": "othersecret1",
        },
    )
    assert response.status_code == 422


def test_admin_patch_team_member_unlink_user_id(team_member_client: TestClient):
    login(team_member_client)
    rows = team_member_client.get("/api/v1/team-members").json()
    linked = next(row for row in rows if row.get("user_id") is not None)
    response = team_member_client.patch(f"/api/v1/team-members/{linked['id']}", json={"user_id": None})
    assert response.status_code == 200
    assert response.json()["user_id"] is None


def test_team_member_cannot_delete_organization_user(team_member_client: TestClient):
    login_team_member(team_member_client)
    assert team_member_client.delete("/api/v1/organization/users/1").status_code == 403


def test_admin_patch_organization_user_role(team_member_client: TestClient):
    login(team_member_client)
    portal_account = next(u for u in team_member_client.get("/api/v1/organization/users").json() if u["email"] == "doc@example.com")
    uid = portal_account["id"]
    r1 = team_member_client.patch(f"/api/v1/organization/users/{uid}", json={"role": "planner"})
    assert r1.status_code == 200
    assert r1.json()["role"] == "planner"
    r2 = team_member_client.patch(f"/api/v1/organization/users/{uid}", json={"role": "team_member"})
    assert r2.status_code == 200
    assert r2.json()["role"] == "team_member"


def test_admin_patch_organization_user_role_rejects_applicant(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    assert client.patch(f"/api/v1/organization/users/{me['id']}", json={"role": "applicant"}).status_code == 422


def test_admin_cannot_demote_sole_admin_to_planner(client: TestClient):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    response = client.patch(f"/api/v1/organization/users/{me['id']}", json={"role": "planner"})
    assert response.status_code == 400


def test_planner_cannot_patch_organization_user_role(planner_client: TestClient):
    login_planner(planner_client)
    assert planner_client.patch("/api/v1/organization/users/1", json={"role": "team_member"}).status_code == 403


def test_organization_membership_invite_planner_flow():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Host Org", slug="host-org", plan_tier="team"))
        db.add(Organization(id=2, name="Other Org", slug="other-org", plan_tier="team"))
        db.flush()
        sg = ShiftGroup(organization_id=1, code="g1", name="G1", display_order=0)
        db.add(sg)
        db.flush()
        acc_inv = Account(email="invitee@example.com", hashed_password=hash_password("invpw"))
        db.add(acc_inv)
        db.flush()
        db.add(User(account_id=acc_inv.id, organization_id=2, role="team_member", locale="de"))
        _seed_membership(db, "hostadmin@example.com", "hostpw", 1, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "hostadmin@example.com", "password": "hostpw", "organization_slug": "host-org"},
                ).status_code
                == 200
            )
            inv = tc.post(
                "/api/v1/organization/invites",
                json={
                    "invitee_email": "invitee@example.com",
                    "role": "planner",
                    "planner_shift_group_ids": [1],
                    "message": "Join us",
                },
            )
            assert inv.status_code == 200
            assert inv.json()["status"] == "pending"
            listed = tc.get("/api/v1/organization/invites").json()
            assert len(listed) == 1
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "invitee@example.com", "password": "invpw", "organization_slug": "other-org"},
                ).status_code
                == 200
            )
            pending = tc.get("/api/v1/auth/me/organization-invites").json()
            assert len(pending) == 1
            assert pending[0]["organization"]["slug"] == "host-org"
            invite_id = pending[0]["id"]
            acc = tc.post(f"/api/v1/auth/me/organization-invites/{invite_id}/accept")
            assert acc.status_code == 200
            me = tc.get("/api/v1/auth/me").json()
            assert me["organization_id"] == 1
            assert me["role"] == "planner"
    finally:
        app.dependency_overrides.clear()


def test_organization_invite_rejects_unknown_email(client: TestClient):
    login(client)
    r = client.post(
        "/api/v1/organization/invites",
        json={
            "invitee_email": "nobody-at-all@example.com",
            "role": "planner",
            "planner_shift_group_ids": [1],
        },
    )
    assert r.status_code == 400


def test_organization_invite_revoke():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="R", slug="org-r", plan_tier="team"))
        db.flush()
        sg = ShiftGroup(organization_id=1, code="g1", name="G1", display_order=0)
        db.add(sg)
        db.flush()
        acc = Account(email="revoke_target@example.com", hashed_password=hash_password("x"))
        db.add(acc)
        db.flush()
        _seed_membership(db, "revoke_admin@example.com", "x", 1, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            tc.post(
                "/api/v1/auth/login",
                json={"email": "revoke_admin@example.com", "password": "x", "organization_slug": "org-r"},
            )
            inv = tc.post(
                "/api/v1/organization/invites",
                json={"invitee_email": "revoke_target@example.com", "role": "planner", "planner_shift_group_ids": [1]},
            )
            assert inv.status_code == 200
            iid = inv.json()["id"]
            assert tc.delete(f"/api/v1/organization/invites/{iid}").status_code == 204
            row = tc.get("/api/v1/organization/invites").json()
            assert row[0]["status"] == "revoked"
    finally:
        app.dependency_overrides.clear()


def test_organization_membership_invite_team_member_minimal_accept_with_body():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Host Org", slug="host-org", plan_tier="team"))
        db.add(Organization(id=2, name="Other Org", slug="other-org", plan_tier="team"))
        db.flush()
        sg = ShiftGroup(organization_id=1, code="g1", name="G1", display_order=0)
        db.add(sg)
        db.flush()
        acc_inv = Account(email="tmmin@example.com", hashed_password=hash_password("invpw"))
        db.add(acc_inv)
        db.flush()
        db.add(User(account_id=acc_inv.id, organization_id=2, role="team_member", locale="de"))
        _seed_membership(db, "hostadmin2@example.com", "hostpw", 1, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "hostadmin2@example.com", "password": "hostpw", "organization_slug": "host-org"},
                ).status_code
                == 200
            )
            inv = tc.post(
                "/api/v1/organization/invites",
                json={"invitee_email": "tmmin@example.com", "role": "team_member"},
            )
            assert inv.status_code == 200
            assert (
                tc.post(
                    "/api/v1/auth/login",
                    json={"email": "tmmin@example.com", "password": "invpw", "organization_slug": "other-org"},
                ).status_code
                == 200
            )
            pending = tc.get("/api/v1/auth/me/organization-invites").json()
            assert len(pending) == 1
            assert pending[0]["needs_profile_on_accept"] is True
            assert len(pending[0]["accept_shift_groups"]) == 1
            invite_id = pending[0]["id"]
            acc = tc.post(
                f"/api/v1/auth/me/organization-invites/{invite_id}/accept",
                json={
                    "first_name": "Pat",
                    "last_name": "Doc",
                    "shift_group_ids": [1],
                    "employment_percentage": 80,
                },
            )
            assert acc.status_code == 200
            me = tc.get("/api/v1/auth/me").json()
            assert me["organization_id"] == 1
            assert me["role"] == "team_member"
    finally:
        app.dependency_overrides.clear()


def test_organization_membership_invite_team_member_precreated_accept_without_body():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Host Org", slug="host-org", plan_tier="team"))
        db.add(Organization(id=2, name="Other Org", slug="other-org", plan_tier="team"))
        db.flush()
        sg = ShiftGroup(organization_id=1, code="g1", name="G1", display_order=0)
        db.add(sg)
        db.flush()
        acc_inv = Account(email="preacc@example.com", hashed_password=hash_password("invpw"))
        db.add(acc_inv)
        db.flush()
        db.add(User(account_id=acc_inv.id, organization_id=2, role="team_member", locale="de"))
        _seed_membership(db, "hostadmin3@example.com", "hostpw", 1, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            tc.post(
                "/api/v1/auth/login",
                json={"email": "hostadmin3@example.com", "password": "hostpw", "organization_slug": "host-org"},
            )
            inv = tc.post(
                "/api/v1/organization/invites",
                json={
                    "invitee_email": "preacc@example.com",
                    "role": "team_member",
                    "prepare_team_member_profile": True,
                    "first_name": "Pre",
                    "last_name": "Created",
                    "shift_group_ids": [1],
                },
            )
            assert inv.status_code == 200
            assert inv.json()["has_precreated_team_member"] is True
            tc.post(
                "/api/v1/auth/login",
                json={"email": "preacc@example.com", "password": "invpw", "organization_slug": "other-org"},
            )
            pending = tc.get("/api/v1/auth/me/organization-invites").json()
            assert pending[0]["needs_profile_on_accept"] is False
            assert pending[0]["has_precreated_team_member"] is True
            invite_id = pending[0]["id"]
            acc = tc.post(f"/api/v1/auth/me/organization-invites/{invite_id}/accept", json={})
            assert acc.status_code == 200
            me = tc.get("/api/v1/auth/me").json()
            assert me["organization_id"] == 1
            assert me["role"] == "team_member"
    finally:
        app.dependency_overrides.clear()


def test_organization_invite_revoke_deletes_precreated_team_member():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="R", slug="org-rv", plan_tier="team"))
        db.flush()
        sg = ShiftGroup(organization_id=1, code="g1", name="G1", display_order=0)
        db.add(sg)
        db.flush()
        acc = Account(email="preclean@example.com", hashed_password=hash_password("x"))
        db.add(acc)
        db.flush()
        _seed_membership(db, "rv_admin@example.com", "x", 1, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            tc.post(
                "/api/v1/auth/login",
                json={"email": "rv_admin@example.com", "password": "x", "organization_slug": "org-rv"},
            )
            inv = tc.post(
                "/api/v1/organization/invites",
                json={
                    "invitee_email": "preclean@example.com",
                    "role": "team_member",
                    "prepare_team_member_profile": True,
                    "first_name": "Or",
                    "last_name": "Phan",
                    "shift_group_ids": [1],
                },
            )
            assert inv.status_code == 200
            members_before = tc.get("/api/v1/team-members").json()
            assert len(members_before) == 1
            iid = inv.json()["id"]
            assert tc.delete(f"/api/v1/organization/invites/{iid}").status_code == 204
            members_after = tc.get("/api/v1/team-members").json()
            assert members_after == []
    finally:
        app.dependency_overrides.clear()


def test_organization_delete_wrong_name():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=2, name="Exact Name", slug="exact-slug", plan_tier="team"))
        db.flush()
        _seed_membership(db, "deladmin@example.com", "d", 2, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            tc.post(
                "/api/v1/auth/login",
                json={"email": "deladmin@example.com", "password": "d", "organization_slug": "exact-slug"},
            )
            r = tc.request(
                "DELETE",
                "/api/v1/organization",
                json={"confirm_organization_name": "Wrong"},
            )
            assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_organization_delete_success():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=2, name="Wipe Co", slug="wipe-co", plan_tier="team"))
        db.flush()
        _seed_membership(db, "wipe@example.com", "w", 2, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            tc.post(
                "/api/v1/auth/login",
                json={"email": "wipe@example.com", "password": "w", "organization_slug": "wipe-co"},
            )
            r = tc.request(
                "DELETE",
                "/api/v1/organization",
                json={"confirm_organization_name": "Wipe Co"},
            )
            assert r.status_code == 204
            assert tc.get("/api/v1/auth/me").status_code == 401
    finally:
        app.dependency_overrides.clear()


def _week_parity_pattern_payload(*, severity: str = "warning") -> dict:
    return {
        "patterns": [
            {
                "label": "Even weeks",
                "is_active": True,
                "severity": severity,
                "display_order": 0,
                "rule": {"type": "allowed_calendar_week_parity", "parity": "even"},
            }
        ]
    }


def test_team_member_planning_patterns_self_service(team_member_client: TestClient):
    login_team_member(team_member_client)
    team_member_id = team_member_client.get("/api/v1/auth/me").json()["team_member_id"]
    response = team_member_client.put(
        f"/api/v1/team-members/{team_member_id}/planning-patterns",
        json=_week_parity_pattern_payload(),
    )
    assert response.status_code == 200
    assert response.json()[0]["rule"]["parity"] == "even"
    assert response.json()[0]["rule"]["status"] == "frei"
    listed = team_member_client.get(f"/api/v1/team-members/{team_member_id}/planning-patterns")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_planner_planning_patterns_read_only(planner_client: TestClient):
    login_planner(planner_client)
    member_id = next(
        member["id"]
        for member in planner_client.get("/api/v1/team-members").json()
        if member["email"] == "ingroup@example.com"
    )
    assert planner_client.get(f"/api/v1/team-members/{member_id}/planning-patterns").status_code == 200
    denied = planner_client.put(
        f"/api/v1/team-members/{member_id}/planning-patterns",
        json=_week_parity_pattern_payload(),
    )
    assert denied.status_code == 403


def test_admin_member_pattern_policy_caps_error_severity(client: TestClient):
    login(client)
    policy = client.get("/api/v1/organization/member-pattern-policy")
    assert policy.status_code == 200
    assert policy.json()["hard_types"] == []
    team_member_id = client.post(
        "/api/v1/team-members",
        json={"first_name": "Pat", "last_name": "Tern", "email": "pat@example.com", "employment_percentage": 100},
    ).json()["id"]
    rejected = client.put(
        f"/api/v1/team-members/{team_member_id}/planning-patterns",
        json=_week_parity_pattern_payload(severity="error"),
    )
    assert rejected.status_code == 400
    updated = client.patch(
        "/api/v1/organization/member-pattern-policy",
        json={"hard_types": ["allowed_calendar_week_parity"]},
    )
    assert updated.status_code == 200
    assert updated.json()["hard_types"] == ["allowed_calendar_week_parity"]
    accepted = client.put(
        f"/api/v1/team-members/{team_member_id}/planning-patterns",
        json=_week_parity_pattern_payload(severity="error"),
    )
    assert accepted.status_code == 200
    assert accepted.json()[0]["severity"] == "error"


def test_team_member_property_definitions_admin_crud(client: TestClient):
    login(client)
    created = client.post(
        "/api/v1/team-member-property-definitions",
        json={
            "name": "Training years",
            "type": "number",
            "options": [],
            "editable_by_team_member": True,
            "display_order": 0,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    definition_id = created.json()["id"]
    listed = client.get("/api/v1/team-member-property-definitions")
    assert listed.status_code == 200
    assert any(row["id"] == definition_id for row in listed.json())
    patched = client.patch(
        f"/api/v1/team-member-property-definitions/{definition_id}",
        json={"name": "Years in training"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Years in training"


def test_team_member_property_values_member_self_service(team_member_client: TestClient):
    login(team_member_client)
    defn = team_member_client.post(
        "/api/v1/team-member-property-definitions",
        json={
            "name": "Zusatz",
            "type": "select",
            "options": ["A", "B"],
            "editable_by_team_member": True,
        },
    ).json()
    login_team_member(team_member_client)
    team_member_id = team_member_client.get("/api/v1/auth/me").json()["team_member_id"]
    put = team_member_client.put(
        f"/api/v1/team-members/{team_member_id}/property-values",
        json={"values": [{"property_definition_id": defn["id"], "value": "A"}]},
    )
    assert put.status_code == 200
    assert put.json()[0]["value"] == "A"
    denied = team_member_client.post(
        "/api/v1/team-member-property-definitions",
        json={"name": "X", "type": "text"},
    )
    assert denied.status_code == 403


def test_team_member_property_values_admin_only_field(team_member_client: TestClient):
    login(team_member_client)
    defn = team_member_client.post(
        "/api/v1/team-member-property-definitions",
        json={
            "name": "Internal",
            "type": "text",
            "editable_by_team_member": False,
        },
    ).json()
    login_team_member(team_member_client)
    team_member_id = team_member_client.get("/api/v1/auth/me").json()["team_member_id"]
    denied = team_member_client.put(
        f"/api/v1/team-members/{team_member_id}/property-values",
        json={"values": [{"property_definition_id": defn["id"], "value": "nope"}]},
    )
    assert denied.status_code == 403
    login(team_member_client)
    ok = team_member_client.put(
        f"/api/v1/team-members/{team_member_id}/property-values",
        json={"values": [{"property_definition_id": defn["id"], "value": "admin ok"}]},
    )
    assert ok.status_code == 200
    assert ok.json()[0]["value"] == "admin ok"
