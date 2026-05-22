import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Organization, TeamMember
from app.models.base import Base
from app.services.team_members import planning_display_name, team_member_planning_display_name


@pytest.fixture()
def nick_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_planning_display_name_uses_nickname(nick_db):
    assert planning_display_name(nickname="Max", last_name="Mustermann") == "Max"
    assert planning_display_name(nickname="  ", last_name="Mustermann") == "Mustermann"
    assert planning_display_name(nickname=None, last_name="Mustermann") == "Mustermann"


def test_team_member_planning_display_name_from_model(nick_db):
    db = nick_db
    member = TeamMember(
        organization_id=1,
        first_name="Anna",
        last_name="Schmidt",
        nickname="AS",
        email="a@example.com",
        employment_percentage=100,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    assert team_member_planning_display_name(member) == "AS"
    member.nickname = None
    assert team_member_planning_display_name(member) == "Schmidt"
