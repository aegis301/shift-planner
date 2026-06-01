from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import (
    Account,
    Organization,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftGroupShiftTemplate,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
    TeamMemberShiftGroup,
    User,
    UserShiftGroup,
)
from app.models.base import Base
from app.services.dashboard import _member_upcoming_shifts, get_admin_dashboard
from app.services.team_members import planning_display_name


@pytest.fixture()
def dash_db():
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


def test_planning_display_name_nickname():
    assert planning_display_name(nickname="Max", last_name="Muster") == "Max"
    assert planning_display_name(nickname="  ", last_name="Muster") == "Muster"
    assert planning_display_name(nickname=None, last_name="Muster") == "Muster"


def test_admin_dashboard_kpis(dash_db):
    db = dash_db
    db.add(
        TeamMember(
            organization_id=1,
            first_name="A",
            last_name="B",
            email="ab@example.com",
            employment_percentage=100,
            is_active=True,
        )
    )
    today = date.today()
    db.add(PlanningPeriod(organization_id=1, year=today.year, month=today.month, status="draft"))
    db.commit()
    payload = get_admin_dashboard(db, organization_id=1)
    assert payload.kpis.active_team_members == 1
    assert len(payload.periods) == 1
    assert payload.periods[0].status == "draft"


def _seed_membership(db, email: str, password: str, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=1, role=role, locale="de")
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def dash_client():
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
        _seed_membership(db, "admin@example.com", "secret", "admin")
        planner = _seed_membership(db, "planner@example.com", "secret", "planner")
        sg = ShiftGroup(organization_id=1, code="icu", name_de="ICU", name_en="ICU", display_order=0)
        db.add(sg)
        db.flush()
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=sg.id))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secret", "organization_slug": "default"},
    )


def test_planner_dashboard_defaults_to_all_groups(dash_client: TestClient):
    _login(dash_client, "planner@example.com")
    response = dash_client.get("/api/v1/dashboard/planner")
    assert response.status_code == 200
    payload = response.json()
    assert payload["shift_group_id"] is None
    assert "periods" in payload


def test_admin_dashboard_api(dash_client: TestClient):
    _login(dash_client, "admin@example.com")
    response = dash_client.get("/api/v1/dashboard/admin")
    assert response.status_code == 200
    assert "kpis" in response.json()


def test_member_upcoming_shifts_all_future(dash_db):
    db = dash_db
    today = date.today()
    sg = ShiftGroup(organization_id=1, code="icu", name_de="ICU", name_en="ICU", display_order=0)
    db.add(sg)
    db.flush()
    member = TeamMember(
        organization_id=1,
        first_name="Pat",
        last_name="Nurse",
        email="pat@example.com",
        employment_percentage=100,
        is_active=True,
    )
    db.add(member)
    db.flush()
    db.add(TeamMemberShiftGroup(team_member_id=member.id, shift_group_id=sg.id))
    template = ShiftTemplate(
        organization_id=1,
        code="RD",
        name_de="Rufdienst",
        name_en="Stand-by",
        category="rufdienst",
        display_order=0,
    )
    db.add(template)
    db.flush()
    db.add(ShiftGroupShiftTemplate(shift_group_id=sg.id, shift_template_id=template.id))
    variant = ShiftVariant(
        shift_template_id=template.id,
        label="Tag",
        start_day_class="weekday",
        end_day_class="weekday",
        starts_at=time(8, 0),
        ends_at=time(20, 0),
        end_day_offset=0,
        required_count=1,
    )
    db.add(variant)
    db.flush()
    period = PlanningPeriod(organization_id=1, year=today.year, month=today.month, status="preliminary")
    db.add(period)
    db.flush()
    slot_date = today + timedelta(days=3)
    slot = RosterSlot(
        planning_period_id=period.id,
        shift_template_id=template.id,
        shift_variant_id=variant.id,
        slot_date=slot_date,
        position=1,
        starts_at=datetime.combine(slot_date, datetime.min.time()).replace(tzinfo=timezone.utc),
        ends_at=datetime.combine(slot_date, datetime.max.time()).replace(tzinfo=timezone.utc),
        day_class="weekday",
    )
    db.add(slot)
    db.flush()
    db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
    db.commit()

    rows = _member_upcoming_shifts(
        db,
        organization_id=1,
        team_member_id=member.id,
        template_ids={template.id},
    )
    assert len(rows) == 1
    assert rows[0].slot_date == slot_date
    assert rows[0].template_code == "RD"
    assert rows[0].category == "rufdienst"

    far_period = PlanningPeriod(
        organization_id=1,
        year=(today + timedelta(weeks=20)).year,
        month=(today + timedelta(weeks=20)).month,
        status="preliminary",
    )
    db.add(far_period)
    db.flush()
    far_date = today + timedelta(weeks=20)
    far_slot = RosterSlot(
        planning_period_id=far_period.id,
        shift_template_id=template.id,
        shift_variant_id=variant.id,
        slot_date=far_date,
        position=1,
        day_class="weekday",
    )
    db.add(far_slot)
    db.flush()
    db.add(RosterSlotAssignment(roster_slot_id=far_slot.id, team_member_id=member.id))
    db.commit()

    rows = _member_upcoming_shifts(
        db,
        organization_id=1,
        team_member_id=member.id,
        template_ids={template.id},
    )
    assert len(rows) == 2
    assert {row.slot_date for row in rows} == {slot_date, far_date}
