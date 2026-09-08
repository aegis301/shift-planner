import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, ShiftGroup, User, UserShiftGroup
from app.models.base import Base
from app.services.ai.providers import ProviderTurn
from app.services.ai.runtime import set_provider_override
from app.services.ai_credentials import decrypt_api_key, encrypt_api_key
from app.services.authz import ROLE_PLANNER


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    em = email.lower()
    acc = db.scalar(select(Account).where(Account.email == em))
    if acc is None:
        acc = Account(email=em, hashed_password=hash_password(password))
        db.add(acc)
        db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    return user


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.session_cookie_secure", False)
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
        planner = _seed_membership(db, "planner@example.com", "secret", 1, ROLE_PLANNER)
        db.flush()
        group = ShiftGroup(organization_id=1, code="default_sg", name="Default SG", display_order=0)
        db.add(group)
        db.flush()
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=group.id))
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
    set_provider_override(None)


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    )
    assert response.status_code == 200


def login_planner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "planner@example.com", "password": "secret", "organization_slug": "default"},
    )
    assert response.status_code == 200


def test_encrypt_api_key_round_trip():
    token = encrypt_api_key("sk-live-example-key")
    assert "sk-live" not in token
    assert decrypt_api_key(token) == "sk-live-example-key"


def test_ai_settings_never_echo_secret(client: TestClient):
    login_admin(client)
    response = client.put(
        "/api/v1/organization/ai-settings",
        json={
            "provider": "openai",
            "default_model": "gpt-4o-mini",
            "api_key": "sk-secret-value-9999",
            "enabled_task_ids": ["summarize_wishes", "explain_validation", "draft_fair_roster"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_api_key"] is True
    assert body["key_last4"] == "9999"
    assert "sk-secret" not in response.text
    assert body.get("api_key") is None
    listed = client.get("/api/v1/organization/ai-settings")
    assert listed.status_code == 200
    assert "sk-secret" not in listed.text


def test_planner_cannot_write_ai_settings(client: TestClient):
    login_planner(client)
    response = client.put(
        "/api/v1/organization/ai-settings",
        json={"api_key": "sk-planner"},
    )
    assert response.status_code == 403


class _ImmediateProvider:
    def complete(self, **kwargs):
        payload = {
            "summary": "Kurzfassung",
            "coverage_gaps": [],
            "vacation_clusters": [],
            "conflicts": [],
        }
        return ProviderTurn(
            assistant_text='{"summary":"Kurzfassung","coverage_gaps":[],"vacation_clusters":[],"conflicts":[]}',
            tool_calls=[],
            parsed_json=payload,
            prompt_tokens=11,
            completion_tokens=7,
        )


def test_summarize_wishes_run(client: TestClient):
    login_admin(client)
    set_provider_override(_ImmediateProvider())
    put = client.put(
        "/api/v1/organization/ai-settings",
        json={"api_key": "sk-test-aaaa", "provider": "anthropic", "default_model": "claude-sonnet-4-5"},
    )
    assert put.status_code == 200
    groups = client.get("/api/v1/shift-groups").json()
    shift_group_id = groups[0]["id"]
    period = client.post("/api/v1/planning-periods", json={"year": 2033, "month": 4})
    assert period.status_code == 200
    run = client.post(
        "/api/v1/ai/tasks/summarize_wishes/runs",
        json={"planning_period_id": period.json()["id"], "shift_group_id": shift_group_id},
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "succeeded"
    assert body["output"]["summary"] == "Kurzfassung"
    assert "current_validation" in body["output"]
    fetched = client.get(f"/api/v1/ai/runs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["prompt_tokens"] == 11


def test_planner_ai_settings_hides_last4(client: TestClient):
    login_admin(client)
    client.put(
        "/api/v1/organization/ai-settings",
        json={"api_key": "sk-test-bbbb"},
    )
    login_planner(client)
    response = client.get("/api/v1/ai/settings")
    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert response.json().get("key_last4") is None
