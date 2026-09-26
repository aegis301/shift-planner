import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import verify_password
from app.models import Organization, ShiftGroup, TeamMember, User, UserShiftGroup
from app.models.base import Base
from app.scripts.seed_e2e import (
    E2E_ADMIN_EMAIL,
    E2E_MEMBER_EMAIL,
    E2E_ORGANIZATION_SLUG,
    E2E_PLANNER_EMAIL,
    main,
    seed_e2e,
)
from app.services.organizations import create_organization_record
from app.services.solver_fixture import SolverFixtureSafetyError
from app.services.users import get_account_by_email, get_user_in_organization


def _memory_db() -> tuple[Session, object]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return testing_session(), engine


@pytest.fixture()
def db():
    session, engine = _memory_db()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_main_refuses_without_password(monkeypatch):
    monkeypatch.delenv("E2E_SEED_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_refuses_default_organization(db, monkeypatch):
    organization = create_organization_record(db, name="Default", slug=E2E_ORGANIZATION_SLUG)
    db.commit()
    monkeypatch.setattr(settings, "default_organization_id", organization.id)
    with pytest.raises(SolverFixtureSafetyError, match="DEFAULT_ORGANIZATION_ID"):
        seed_e2e(db, password="e2e-secret-password")
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.scalar(select(func.count()).select_from(TeamMember)) == 0


def test_seed_e2e_is_idempotent(db, monkeypatch):
    default = create_organization_record(db, name="Default", slug="default")
    db.commit()
    monkeypatch.setattr(settings, "default_organization_id", default.id)
    first = seed_e2e(db, password="password-one-aaaa")
    second = seed_e2e(db, password="password-two-bbbb")
    assert second.organization_id == first.organization_id
    assert second.target_period_id == first.target_period_id
    assert second.shift_group_id == first.shift_group_id
    assert second.linked_team_member_id == first.linked_team_member_id
    organizations = list(db.scalars(select(Organization).where(Organization.slug == E2E_ORGANIZATION_SLUG)))
    assert len(organizations) == 1
    assert organizations[0].id != default.id
    users = list(db.scalars(select(User).where(User.organization_id == first.organization_id)))
    assert {user.email for user in users} == {E2E_ADMIN_EMAIL, E2E_PLANNER_EMAIL, E2E_MEMBER_EMAIL}
    member = db.get(TeamMember, first.linked_team_member_id)
    member_user = get_user_in_organization(db, E2E_MEMBER_EMAIL, first.organization_id)
    assert member is not None
    assert member_user is not None
    assert member.user_id == member_user.id
    account = get_account_by_email(db, E2E_MEMBER_EMAIL)
    assert account is not None
    assert verify_password("password-two-bbbb", account.hashed_password)
    assert not verify_password("password-one-aaaa", account.hashed_password)
    planner = get_user_in_organization(db, E2E_PLANNER_EMAIL, first.organization_id)
    assert planner is not None
    group_count = db.scalar(
        select(func.count()).select_from(ShiftGroup).where(ShiftGroup.organization_id == first.organization_id)
    )
    link_count = db.scalar(
        select(func.count()).select_from(UserShiftGroup).where(UserShiftGroup.user_id == planner.id)
    )
    assert link_count == group_count
    assert group_count == 2
