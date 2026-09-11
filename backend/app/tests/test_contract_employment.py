from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, EmploymentPeriod, Organization, TeamMember, User
from app.models.base import Base
from app.schemas import ContractCategoryRule
from app.services.authz import ROLE_PLANNER
from app.services.contract_employment_upgrade import apply_contract_employment_upgrade
from app.services.employment_periods import employment_percentage_on


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    return user


def _valid_group_body(**overrides):
    body = {
        "name": "Extra",
        "weekly_hours_at_100": 40,
        "vacation_days_at_100": 30,
        "regular_week_pattern": [{"weekday": "mon", "start": "08:00:00", "end": "16:30:00"}],
        "category_rules": [
            {
                "category": "bereitschaftsdienst",
                "counts_toward_contract": True,
                "credit_mode": "factor",
                "credit_factor": "0.6",
                "holiday_credit_bonus": "25",
                "statutory_factor": "1",
                "call_outs_count_as_work": False,
            },
            {
                "category": "rufdienst",
                "counts_toward_contract": False,
                "credit_mode": "none",
                "holiday_credit_bonus": "0",
                "statutory_factor": "1",
                "call_outs_count_as_work": True,
            },
        ],
        "status_mappings": [
            {"code": "urlaub", "absence_kind": "vacation", "consumes_vacation": True, "counts_as_work_day": False}
        ],
    }
    body.update(overrides)
    return body


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
        planner = _seed_membership(db, "planner@example.com", "plannersecret", 1, ROLE_PLANNER)
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
        db.commit()
        assert planner.id is not None

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


def login_admin(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    ).status_code == 200


def login_planner(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "planner@example.com", "password": "plannersecret", "organization_slug": "default"},
    ).status_code == 200


def login_team_member(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "doc@example.com", "password": "docsecret", "organization_slug": "default"},
    ).status_code == 200


def test_overlapping_employment_periods_rejected_with_400(client: TestClient) -> None:
    login_admin(client)
    created = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "employment_percentage": 80},
    )
    assert created.status_code == 200
    member_id = created.json()["id"]
    groups = client.get("/api/v1/contract-groups").json()
    group_id = groups[0]["id"]
    response = client.put(
        f"/api/v1/team-members/{member_id}/employment-periods",
        json={
            "periods": [
                {
                    "contract_group_id": group_id,
                    "employment_percentage": 80,
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-30",
                },
                {
                    "contract_group_id": group_id,
                    "employment_percentage": 50,
                    "start_date": "2026-06-01",
                    "end_date": None,
                },
            ]
        },
    )
    assert response.status_code == 400
    assert "overlap" in response.json()["detail"].lower()


def test_employment_percentage_on_resolves_dated_periods() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    member = TeamMember(organization_id=1, first_name="A", last_name="B", email="ab@example.com")
    db.add(member)
    db.flush()
    from app.services.contract_groups import ensure_default_contract_group

    group = ensure_default_contract_group(db, organization_id=1)
    db.add(
        EmploymentPeriod(
            team_member_id=member.id,
            contract_group_id=group.id,
            employment_percentage=80,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
        )
    )
    db.add(
        EmploymentPeriod(
            team_member_id=member.id,
            contract_group_id=group.id,
            employment_percentage=50,
            start_date=date(2026, 7, 1),
            end_date=None,
        )
    )
    db.commit()
    db.refresh(member)
    assert employment_percentage_on(member, date(2026, 3, 15)) == 80
    assert employment_percentage_on(member, date(2026, 7, 1)) == 50
    assert employment_percentage_on(member, date(2025, 12, 31)) == 100
    db.close()
    engine.dispose()


def test_employment_percentage_column_gone_and_upgrade_preserves_values() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE organizations (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    slug VARCHAR(64) NOT NULL,
                    plan_tier VARCHAR(50) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE team_members (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    first_name VARCHAR(255) NOT NULL,
                    last_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    employment_percentage INTEGER NOT NULL DEFAULT 100
                )
                """
            )
        )
        connection.execute(
            text("INSERT INTO organizations (id, name, slug, plan_tier) VALUES (1, 'Default', 'default', 'team')")
        )
        connection.execute(
            text(
                """
                INSERT INTO team_members (id, organization_id, first_name, last_name, email, employment_percentage)
                VALUES (1, 1, 'Ada', 'Lovelace', 'ada@example.com', 80),
                       (2, 1, 'Bob', 'Builder', 'bob@example.com', 50)
                """
            )
        )
        apply_contract_employment_upgrade(connection)
        rows = connection.execute(
            text("SELECT team_member_id, employment_percentage, end_date FROM employment_periods ORDER BY team_member_id")
        ).fetchall()
        assert [(row[0], row[1], row[2]) for row in rows] == [(1, 80, None), (2, 50, None)]
        columns = {col["name"] for col in inspect(connection).get_columns("team_members")}
        assert "employment_percentage" not in columns
    columns_orm = {col.name for col in TeamMember.__table__.columns}
    assert "employment_percentage" not in columns_orm
    engine.dispose()


def test_category_rule_credit_factor_validation() -> None:
    with pytest.raises(ValidationError):
        ContractCategoryRule.model_validate(
            {
                "category": "bereitschaftsdienst",
                "credit_mode": "duration",
                "credit_factor": "0.5",
                "statutory_factor": "1",
            }
        )
    with pytest.raises(ValidationError):
        ContractCategoryRule.model_validate(
            {
                "category": "bereitschaftsdienst",
                "credit_mode": "factor",
                "statutory_factor": "1",
            }
        )
    with pytest.raises(ValidationError):
        ContractCategoryRule.model_validate(
            {
                "category": "bereitschaftsdienst",
                "credit_mode": "factor",
                "credit_factor": "1.2",
                "statutory_factor": "1",
            }
        )
    with pytest.raises(ValidationError):
        ContractCategoryRule.model_validate(
            {
                "category": "bereitschaftsdienst",
                "credit_mode": "none",
                "holiday_credit_bonus": "120",
                "statutory_factor": "1",
            }
        )
    rule = ContractCategoryRule.model_validate(
        {
            "category": "bereitschaftsdienst",
            "credit_mode": "factor",
            "credit_factor": "0.6",
            "holiday_credit_bonus": "25",
            "statutory_factor": Decimal("1"),
        }
    )
    assert rule.credit_factor == Decimal("0.6")


def test_category_rule_payload_rejected_by_api(client: TestClient) -> None:
    login_admin(client)
    response = client.post(
        "/api/v1/contract-groups",
        json=_valid_group_body(
            category_rules=[
                {
                    "category": "bereitschaftsdienst",
                    "credit_mode": "factor",
                    "holiday_credit_bonus": "10",
                    "statutory_factor": "1",
                }
            ]
        ),
    )
    assert response.status_code == 422


def test_delete_referenced_contract_group_refused(client: TestClient) -> None:
    login_admin(client)
    created = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada2@example.com", "employment_percentage": 100},
    )
    member_id = created.json()["id"]
    extra = client.post("/api/v1/contract-groups", json=_valid_group_body())
    assert extra.status_code == 201
    extra_id = extra.json()["id"]
    assigned = client.put(
        f"/api/v1/team-members/{member_id}/employment-periods",
        json={
            "periods": [
                {
                    "contract_group_id": extra_id,
                    "employment_percentage": 100,
                    "start_date": "2026-01-01",
                    "end_date": None,
                }
            ]
        },
    )
    assert assigned.status_code == 200
    blocked = client.delete(f"/api/v1/contract-groups/{extra_id}")
    assert blocked.status_code == 400
    unused = client.post("/api/v1/contract-groups", json=_valid_group_body(name="Unused"))
    unused_id = unused.json()["id"]
    deleted = client.delete(f"/api/v1/contract-groups/{unused_id}")
    assert deleted.status_code == 200


def test_contract_groups_authorization(client: TestClient) -> None:
    login_team_member(client)
    assert client.get("/api/v1/contract-groups").status_code == 403
    login_planner(client)
    listed = client.get("/api/v1/contract-groups")
    assert listed.status_code == 200
    denied = client.post("/api/v1/contract-groups", json=_valid_group_body(name="Planner"))
    assert denied.status_code == 403
    login_admin(client)
    created = client.post("/api/v1/contract-groups", json=_valid_group_body(name="AdminGroup"))
    assert created.status_code == 201
    assert Decimal(str(created.json()["category_rules"][0]["statutory_factor"])) == Decimal("1")


def test_create_member_employment_percentage_comes_from_period(client: TestClient) -> None:
    login_admin(client)
    response = client.post(
        "/api/v1/team-members",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada3@example.com", "employment_percentage": 80},
    )
    assert response.status_code == 200
    assert response.json()["employment_percentage"] == 80
    member_id = response.json()["id"]
    periods = client.get(f"/api/v1/team-members/{member_id}/employment-periods").json()
    assert len(periods) == 1
    assert periods[0]["employment_percentage"] == 80
    assert periods[0]["end_date"] is None
