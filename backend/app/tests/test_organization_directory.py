from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, TeamMember, User
from app.models.base import Base
from app.services.organization_directory import list_organization_staff_directory


def _mk_user(db, email: str, role: str = "team_member", password: str = "x") -> User:
    em = email.lower()
    acc = db.scalar(select(Account).where(Account.email == em))
    if acc is None:
        acc = Account(email=em, hashed_password=hash_password(password))
        db.add(acc)
        db.flush()
    u = User(account_id=acc.id, organization_id=1, role=role, locale="de")
    db.add(u)
    return u


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return TestingSessionLocal


def test_list_organization_staff_directory_link_statuses():
    SessionLocal = _session_factory()
    with SessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _mk_user(db, "admin@example.com", role="admin")
        u_same = _mk_user(db, "same@example.com")
        u_other = _mk_user(db, "other@example.com")
        u_foreign = _mk_user(db, "foreign-login@example.com")
        _mk_user(db, "wronglink@example.com")
        db.flush()
        d_linked = TeamMember(
            organization_id=1,
            first_name="A",
            last_name="Linked",
            email="same@example.com",
            employment_percentage=100,
            user_id=u_same.id,
        )
        d_only = TeamMember(
            organization_id=1,
            first_name="B",
            last_name="Only",
            email="only@example.com",
            employment_percentage=100,
            user_id=None,
        )
        d_unlinked = TeamMember(
            organization_id=1,
            first_name="C",
            last_name="Unlinked",
            email="unlinked@example.com",
            employment_percentage=100,
            user_id=None,
        )
        _mk_user(db, "unlinked@example.com")
        d_wrong = TeamMember(
            organization_id=1,
            first_name="D",
            last_name="Wrong",
            email="wronglink@example.com",
            employment_percentage=100,
            user_id=u_other.id,
        )
        d_foreign = TeamMember(
            organization_id=1,
            first_name="E",
            last_name="Foreign",
            email="foreign-doc@example.com",
            employment_percentage=100,
            user_id=u_foreign.id,
        )
        db.add_all([d_linked, d_only, d_unlinked, d_wrong, d_foreign])
        db.commit()

    with SessionLocal() as db:
        rows = list_organization_staff_directory(db, organization_id=1)
        by_email = {r.email.lower(): r for r in rows}

    assert by_email["admin@example.com"].link_status == "login_only"
    assert by_email["same@example.com"].link_status == "linked_ok"
    assert by_email["only@example.com"].link_status == "team_member_only"
    assert by_email["unlinked@example.com"].link_status == "login_unlinked"
    assert by_email["wronglink@example.com"].link_status == "linked_wrong_user"
    assert by_email["foreign-doc@example.com"].link_status == "linked_foreign_user"
    assert by_email["foreign-doc@example.com"].linked_user_id == u_foreign.id
    assert by_email["foreign-doc@example.com"].user_id is None
    assert by_email["other@example.com"].link_status == "login_only"


def test_organization_staff_directory_api_admin():
    SessionLocal = _session_factory()
    with SessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _mk_user(db, "admin@example.com", role="admin", password="secret")
        db.commit()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.post(
                "/api/v1/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "secret",
                    "organization_slug": "default",
                },
            )
            r = test_client.get("/api/v1/organization/staff-directory")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 1
            assert data[0]["email"] == "admin@example.com"
            assert data[0]["link_status"] == "login_only"
            assert data[0]["user_id"] >= 1
    finally:
        app.dependency_overrides.clear()


def test_organization_staff_directory_forbidden_for_team_member():
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
        _mk_user(db, "admin@example.com", role="admin", password="secret")
        du = _mk_user(db, "doc@example.com", password="docsecret")
        db.flush()
        db.add(
            TeamMember(
                organization_id=1,
                first_name="S",
                last_name="D",
                email="docperson@example.com",
                employment_percentage=100,
                user_id=du.id,
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
        with TestClient(app) as test_client:
            test_client.post(
                "/api/v1/auth/login",
                json={
                    "email": "doc@example.com",
                    "password": "docsecret",
                    "organization_slug": "default",
                },
            )
            assert test_client.get("/api/v1/organization/staff-directory").status_code == 403
    finally:
        app.dependency_overrides.clear()
