import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Organization, TeamMember
from app.models.base import Base


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    session.add(Organization(id=1, name="Hospital A", slug="hospital-a", plan_tier="team"))
    session.add(Organization(id=2, name="Hospital B", slug="hospital-b", plan_tier="team"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_same_email_allowed_in_two_organizations(db):
    shared_email = "locum@example.com"
    db.add(
        TeamMember(
            organization_id=1,
            first_name="Alex",
            last_name="Locum",
            email=shared_email,
        )
    )
    db.add(
        TeamMember(
            organization_id=2,
            first_name="Alex",
            last_name="Locum",
            email=shared_email,
        )
    )
    db.commit()
    members = db.scalars(select(TeamMember).order_by(TeamMember.organization_id)).all()
    assert [member.organization_id for member in members] == [1, 2]
    assert {member.email for member in members} == {shared_email}


def test_same_email_rejected_within_one_organization(db):
    db.add(
        TeamMember(
            organization_id=1,
            first_name="Alex",
            last_name="Locum",
            email="locum@example.com",
        )
    )
    db.commit()
    db.add(
        TeamMember(
            organization_id=1,
            first_name="Other",
            last_name="Person",
            email="locum@example.com",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
