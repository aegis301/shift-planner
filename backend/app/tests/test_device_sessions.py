import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_user_session_token, hash_refresh_token
from app.main import app
from app.models import Account, AuthDeviceSession, AuthRefreshToken, Organization, User
from app.models.base import Base
from app.services.users import hash_password


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = db.scalar(select(Account).where(Account.email == email.lower()))
    if acc is None:
        acc = Account(email=email.lower(), hashed_password=hash_password(password))
        db.add(acc)
        db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
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
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Alpha", slug="alpha", plan_tier="team"))
        db.add(Organization(id=2, name="Beta", slug="beta", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@example.com", "secret", 1, "admin")
        _seed_membership(db, "other@example.com", "other-secret", 2, "admin")
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal
    app.dependency_overrides.clear()


def _issue(client: TestClient, email: str, password: str, name: str = "Pixel 8") -> dict:
    response = client.post(
        "/api/v1/auth/token",
        json={"email": email, "password": password, "device_name": name, "platform": "android"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_ttl_seconds
    return body


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _refresh_rows(SessionLocal) -> list[AuthRefreshToken]:
    with SessionLocal() as db:
        return list(db.scalars(select(AuthRefreshToken)).all())


def _device(SessionLocal, device_session_id: int) -> AuthDeviceSession:
    with SessionLocal() as db:
        row = db.get(AuthDeviceSession, device_session_id)
        assert row is not None
        return row


def test_token_issue_uses_bearer_and_stores_only_the_hash(client):
    test_client, SessionLocal = client
    issued = _issue(test_client, "admin@example.com", "secret")
    raw = issued["refresh_token"]
    assert issued["session"]["auth_kind"] == "user"
    assert issued["session"]["email"] == "admin@example.com"
    me = test_client.get("/api/v1/auth/me", headers=_auth(issued["access_token"]))
    assert me.status_code == 200
    assert me.json()["organization_id"] == 1
    rows = _refresh_rows(SessionLocal)
    assert rows
    assert all(row.token_hash == hash_refresh_token(raw) or raw not in row.token_hash for row in rows)
    assert any(row.token_hash == hash_refresh_token(raw) for row in rows)
    assert all(row.token_hash != raw and "." not in row.token_hash for row in rows)


def test_refresh_rotates_and_reuse_revokes_even_if_the_attacker_is_first(client):
    test_client, SessionLocal = client
    issued = _issue(test_client, "admin@example.com", "secret")
    first = issued["refresh_token"]
    rotated = test_client.post("/api/v1/auth/token/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first
    me = test_client.get("/api/v1/auth/me", headers=_auth(rotated.json()["access_token"]))
    assert me.status_code == 200
    reused = test_client.post("/api/v1/auth/token/refresh", json={"refresh_token": first})
    assert reused.status_code == 401
    device_id = int(first.split(".", 1)[0])
    device = _device(SessionLocal, device_id)
    assert device.revoked_reason == "refresh_reuse"
    assert device.revoked_at is not None
    attacker = test_client.post("/api/v1/auth/token/refresh", json={"refresh_token": second})
    assert attacker.status_code == 401
    assert test_client.get("/api/v1/auth/me", headers=_auth(rotated.json()["access_token"])).status_code == 401


def test_unknown_refresh_token_does_not_revoke(client):
    test_client, SessionLocal = client
    issued = _issue(test_client, "admin@example.com", "secret")
    device_id = int(issued["refresh_token"].split(".", 1)[0])
    guessed = test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": f"{device_id}.not-the-secret"},
    )
    assert guessed.status_code == 401
    device = _device(SessionLocal, device_id)
    assert device.revoked_at is None
    still = test_client.post("/api/v1/auth/token/refresh", json={"refresh_token": issued["refresh_token"]})
    assert still.status_code == 200


def test_expired_access_token_and_expired_device_session_are_rejected(client, monkeypatch):
    test_client, SessionLocal = client
    monkeypatch.setattr(settings, "access_token_ttl_seconds", 1)
    issued = _issue(test_client, "admin@example.com", "secret")
    time.sleep(2.2)
    assert test_client.get("/api/v1/auth/me", headers=_auth(issued["access_token"])).status_code == 401
    fresh = _issue(test_client, "admin@example.com", "secret", name="Tablet")
    device_id = int(fresh["refresh_token"].split(".", 1)[0])
    with SessionLocal() as db:
        row = db.get(AuthDeviceSession, device_id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert test_client.get("/api/v1/auth/me", headers=_auth(fresh["access_token"])).status_code == 401
    expired = test_client.post("/api/v1/auth/token/refresh", json={"refresh_token": fresh["refresh_token"]})
    assert expired.status_code == 401
    assert _device(SessionLocal, device_id).revoked_at is None


def test_revoke_takes_effect_on_the_next_request(client):
    test_client, _session_local = client
    issued = _issue(test_client, "admin@example.com", "secret")
    other = _issue(test_client, "admin@example.com", "secret", name="iPhone")
    listed = test_client.get("/api/v1/auth/me/devices", headers=_auth(issued["access_token"]))
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 2
    assert sum(1 for row in body if row["current"]) == 1
    revoked = test_client.post("/api/v1/auth/token/revoke", headers=_auth(issued["access_token"]))
    assert revoked.status_code == 204
    assert test_client.get("/api/v1/auth/me", headers=_auth(issued["access_token"])).status_code == 401
    assert test_client.get("/api/v1/auth/me", headers=_auth(other["access_token"])).status_code == 200
    other_id = int(other["refresh_token"].split(".", 1)[0])
    removed = test_client.delete(
        f"/api/v1/auth/me/devices/{other_id}",
        headers=_auth(other["access_token"]),
    )
    assert removed.status_code == 204
    assert test_client.get("/api/v1/auth/me", headers=_auth(other["access_token"])).status_code == 401
    missing = test_client.delete("/api/v1/auth/me/devices/9999", headers=_auth(issued["access_token"]))
    assert missing.status_code == 401


def test_password_change_and_admin_reset_revoke_device_sessions(client):
    test_client, SessionLocal = client
    login = test_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    issued = _issue(test_client, "admin@example.com", "secret")
    changed = test_client.post(
        "/api/v1/auth/me/change-password",
        json={"current_password": "secret", "password": "new-secret", "password_confirm": "new-secret"},
    )
    assert changed.status_code == 204
    assert test_client.get("/api/v1/auth/me", headers=_auth(issued["access_token"])).status_code == 401
    assert _device(SessionLocal, int(issued["refresh_token"].split(".", 1)[0])).revoked_reason == "password_change"
    assert test_client.get("/api/v1/auth/me").status_code == 200

    with SessionLocal() as db:
        member = Account(email="staff@example.com", hashed_password=hash_password("staff-secret"))
        db.add(member)
        db.flush()
        user = User(account_id=member.id, organization_id=1, role="team_member", locale="de")
        db.add(user)
        db.commit()
        staff_id = user.id
    staff = _issue(test_client, "staff@example.com", "staff-secret", name="Ward phone")
    reset = test_client.post(
        f"/api/v1/organization/users/{staff_id}/reset-password",
        json={"password": "reset-secret", "password_confirm": "reset-secret"},
    )
    assert reset.status_code == 204, reset.text
    assert test_client.get("/api/v1/auth/me", headers=_auth(staff["access_token"])).status_code == 401
    assert _device(SessionLocal, int(staff["refresh_token"].split(".", 1)[0])).revoked_reason == "admin_password_reset"


def test_admin_reset_and_membership_removal_and_account_deletion(client):
    test_client, SessionLocal = client
    with SessionLocal() as db:
        multi = Account(email="multi@example.com", hashed_password=hash_password("multi-secret"))
        db.add(multi)
        db.flush()
        user_a = User(account_id=multi.id, organization_id=1, role="planner", locale="de")
        user_b = User(account_id=multi.id, organization_id=2, role="planner", locale="de")
        db.add(user_a)
        db.add(user_b)
        db.commit()
        user_b_id = user_b.id
    kept = _issue(test_client, "multi@example.com", "multi-secret", name="Home")
    switched_issue = _issue(test_client, "multi@example.com", "multi-secret", name="Travel")
    switched = test_client.post(
        "/api/v1/auth/me/active-organization",
        headers=_auth(switched_issue["access_token"]),
        json={"organization_slug": "beta"},
    )
    assert switched.status_code == 200
    assert switched.json()["organization_id"] == 2
    assert "access_token" in switched.json()
    assert test_client.get("/api/v1/auth/me", headers=_auth(switched_issue["access_token"])).status_code == 401
    travel = switched.json()["access_token"]
    assert test_client.get("/api/v1/auth/me", headers=_auth(travel)).json()["organization_id"] == 2
    assert test_client.get("/api/v1/auth/me", headers=_auth(kept["access_token"])).json()["organization_id"] == 1
    test_client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "other-secret"})
    removed = test_client.delete(f"/api/v1/organization/users/{user_b_id}")
    assert removed.status_code == 204
    assert test_client.get("/api/v1/auth/me", headers=_auth(travel)).status_code == 401
    assert test_client.get("/api/v1/auth/me", headers=_auth(kept["access_token"])).status_code == 200
    assert _device(SessionLocal, int(switched_issue["refresh_token"].split(".", 1)[0])).revoked_reason == (
        "membership_removed"
    )

    with SessionLocal() as db:
        leaver = Account(email="leaver@example.com", hashed_password=hash_password("leaver-secret"))
        db.add(leaver)
        db.flush()
        db.add(User(account_id=leaver.id, organization_id=1, role="team_member", locale="de"))
        db.commit()
    solo = _issue(test_client, "leaver@example.com", "leaver-secret", name="Only phone")
    test_client.cookies.clear()
    deleted = test_client.post(
        "/api/v1/auth/delete-account",
        headers=_auth(solo["access_token"]),
        json={"password": "leaver-secret"},
    )
    assert deleted.status_code == 204, deleted.text
    assert test_client.get("/api/v1/auth/me", headers=_auth(solo["access_token"])).status_code == 401


def test_bearer_wins_over_cookie_and_the_two_token_kinds_do_not_cross(client):
    test_client, _SessionLocal = client
    login = test_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    cookie = test_client.cookies.get("shift_planner_session")
    assert cookie
    other = _issue(test_client, "other@example.com", "other-secret")
    me = test_client.get("/api/v1/auth/me", headers=_auth(other["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "other@example.com"
    test_client.cookies.clear()
    as_bearer = test_client.get("/api/v1/auth/me", headers=_auth(cookie))
    assert as_bearer.status_code == 401
    test_client.cookies.set("shift_planner_session", other["access_token"])
    as_cookie = test_client.get("/api/v1/auth/me")
    assert as_cookie.status_code == 401
    user_cookie = create_user_session_token(1)
    test_client.cookies.set("shift_planner_session", user_cookie)
    restored = test_client.get("/api/v1/auth/me")
    assert restored.status_code == 200
    assert restored.json()["email"] == "admin@example.com"


def test_onboarding_with_account_bearer_returns_a_user_access_token(client):
    test_client, _SessionLocal = client
    registered = test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "pw12345678",
            "password_confirm": "pw12345678",
            "locale": "en",
        },
    )
    assert registered.status_code == 200
    assert registered.json()["auth_kind"] == "account"
    test_client.cookies.clear()
    issued = _issue(test_client, "new@example.com", "pw12345678", name="Setup")
    assert issued["session"]["auth_kind"] == "account"
    created = test_client.post(
        "/api/v1/auth/me/onboarding/create-organization",
        headers=_auth(issued["access_token"]),
        json={"organization_name": "New Org", "organization_slug": "new-org"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["auth_kind"] == "user"
    assert body["organization"]["slug"] == "new-org"
    assert body["access_token"]
    assert test_client.get("/api/v1/auth/me", headers=_auth(issued["access_token"])).status_code == 401
    me = test_client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_concurrent_refresh_of_one_token_revokes_the_loser_as_reuse(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/refresh-race.db",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(Organization(id=1, name="Alpha", slug="alpha", plan_tier="team"))
        db.flush()
        user = _seed_membership(db, "racer@example.com", "race-secret", 1, "admin")
        db.commit()
        account = user.account
    with SessionLocal() as db:
        account = db.get(Account, account.id)
        user = db.get(User, user.id)
        from app.services.device_sessions import issue_device_session

        issued = issue_device_session(
            db, account=account, user=user, device_name="Pixel", platform="android"
        )
        raw = issued.refresh_token
        device_id = issued.device_session_id
    barrier = threading.Barrier(2)
    seen = {"n": 0}
    real_hash = hash_refresh_token

    def hashing(token: str) -> str:
        digest = real_hash(token)
        if token == raw:
            seen["n"] += 1
            if seen["n"] <= 2:
                barrier.wait(timeout=5)
        return digest

    monkeypatch.setattr("app.services.device_sessions.hash_refresh_token", hashing)
    outcomes: list[tuple[str, ...]] = []
    lock = threading.Lock()

    def worker() -> None:
        from app.services.device_sessions import RefreshRejected, refresh_device_session

        db = SessionLocal()
        try:
            try:
                refresh_device_session(db, raw)
            except RefreshRejected as exc:
                with lock:
                    outcomes.append((exc.reason,))
            except Exception as exc:
                with lock:
                    outcomes.append((type(exc).__name__,))
            else:
                with lock:
                    outcomes.append(("ok",))
        finally:
            db.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == [("ok",), ("reused",)]
    with SessionLocal() as db:
        device = db.get(AuthDeviceSession, device_id)
        assert device is not None
        assert device.revoked_reason == "refresh_reuse"
        current = db.scalar(
            select(AuthRefreshToken).where(
                AuthRefreshToken.device_session_id == device_id,
                AuthRefreshToken.rotated_at.is_(None),
            )
        )
        assert current is not None
    with SessionLocal() as db:
        from app.services.device_sessions import RefreshRejected, refresh_device_session

        fresh = db.scalar(
            select(AuthRefreshToken).where(
                AuthRefreshToken.device_session_id == device_id,
                AuthRefreshToken.rotated_at.is_(None),
            )
        )
        assert fresh is not None
        try:
            refresh_device_session(db, raw)
            raise AssertionError("original token was accepted after the race")
        except RefreshRejected as exc:
            assert exc.reason in {"reused", "revoked"}


def test_deleting_an_organization_revokes_that_memberships_device_session(client):
    test_client, SessionLocal = client
    with SessionLocal() as db:
        multi = Account(email="multi-org@example.com", hashed_password=hash_password("multi-secret"))
        db.add(multi)
        db.flush()
        db.add(User(account_id=multi.id, organization_id=1, role="planner", locale="de"))
        db.add(User(account_id=multi.id, organization_id=2, role="planner", locale="de"))
        db.commit()
    home = _issue(test_client, "multi-org@example.com", "multi-secret", name="Home")
    travel_issue = _issue(test_client, "multi-org@example.com", "multi-secret", name="Travel")
    switched = test_client.post(
        "/api/v1/auth/me/active-organization",
        headers=_auth(travel_issue["access_token"]),
        json={"organization_slug": "beta"},
    )
    assert switched.status_code == 200
    assert switched.json()["organization_id"] == 2
    login = test_client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "other-secret"})
    assert login.status_code == 200
    deleted = test_client.request(
        "DELETE",
        "/api/v1/organization",
        json={"confirm_organization_name": "Beta"},
    )
    assert deleted.status_code == 204, deleted.text
    refreshed = test_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": travel_issue["refresh_token"]},
    )
    assert refreshed.status_code == 401
    assert refreshed.json()["detail"] != "account"
    device_id = int(travel_issue["refresh_token"].split(".", 1)[0])
    assert _device(SessionLocal, device_id).revoked_reason == "membership_removed"
    still = test_client.get("/api/v1/auth/me", headers=_auth(home["access_token"]))
    assert still.status_code == 200
    assert still.json()["organization_id"] == 1
    assert still.json()["auth_kind"] == "user"


def test_login_rejects_bad_token_credentials(client):
    test_client, _SessionLocal = client
    denied = test_client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.com", "password": "nope", "device_name": "Pixel", "platform": "ios"},
    )
    assert denied.status_code == 401
