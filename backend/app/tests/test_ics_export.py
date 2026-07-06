from datetime import date, datetime, time, timedelta, timezone

import pytest
from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import (Account, Organization, PlanningPeriod,
                        PlanningPeriodShiftGroupStatus, RosterSlot,
                        RosterSlotAssignment, ShiftGroup,
                        ShiftGroupShiftTemplate, ShiftTemplate, ShiftVariant,
                        TeamMember, TeamMemberShiftGroup, User)
from app.models.base import Base
from app.services.ics_export import (ShiftCalendarEvent, build_ics_calendar,
                                     event_uid)
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_build_ics_calendar_timed_event():
    start = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, 20, 0, tzinfo=timezone.utc)
    event = ShiftCalendarEvent(
        roster_slot_id=1,
        slot_date=date(2026, 5, 1),
        starts_at=start,
        ends_at=end,
        all_day=False,
        summary="Rufdienst · Tag",
        description="Default",
        uid=event_uid(organization_id=1, roster_slot_id=1),
    )
    body = build_ics_calendar([event], calendar_name="Test")
    cal = Calendar.from_ical(body)
    components = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(components) == 1
    assert str(components[0].get("summary")) == "Rufdienst · Tag"


@pytest.fixture()
def ics_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    ctx: dict = {}
    with TestingSessionLocal() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        acc = Account(email="doc@example.com", hashed_password=hash_password("docsecret"))
        db.add(acc)
        db.flush()
        portal_user = User(account_id=acc.id, organization_id=1, role="team_member", locale="de")
        db.add(portal_user)
        db.flush()
        other_acc = Account(email="other@example.com", hashed_password=hash_password("docsecret"))
        db.add(other_acc)
        db.flush()
        other_user = User(account_id=other_acc.id, organization_id=1, role="team_member", locale="de")
        db.add(other_user)
        db.flush()
        member = TeamMember(
            organization_id=1,
            first_name="Pat",
            last_name="Nurse",
            email="pat@example.com",
            employment_percentage=100,
            user_id=portal_user.id,
        )
        other_member = TeamMember(
            organization_id=1,
            first_name="Other",
            last_name="Nurse",
            email="other@example.com",
            employment_percentage=100,
            user_id=other_user.id,
        )
        db.add(member)
        db.add(other_member)
        db.flush()
        sg = ShiftGroup(organization_id=1, code="icu", name="ICU", display_order=0)
        db.add(sg)
        db.flush()
        db.add(TeamMemberShiftGroup(team_member_id=member.id, shift_group_id=sg.id))
        db.add(TeamMemberShiftGroup(team_member_id=other_member.id, shift_group_id=sg.id))
        template = ShiftTemplate(
            organization_id=1,
            code="RD",
            name="Rufdienst",
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
        today = date.today()
        period = PlanningPeriod(organization_id=1, year=today.year, month=today.month, status="preliminary")
        db.add(period)
        db.flush()
        db.add(
            PlanningPeriodShiftGroupStatus(
                planning_period_id=period.id,
                shift_group_id=sg.id,
                status="preliminary",
            )
        )
        slot_date = today + timedelta(days=3)
        slot = RosterSlot(
            planning_period_id=period.id,
            shift_template_id=template.id,
            shift_variant_id=variant.id,
            slot_date=slot_date,
            position=1,
            starts_at=datetime.combine(slot_date, time(8, 0), tzinfo=timezone.utc),
            ends_at=datetime.combine(slot_date, time(20, 0), tzinfo=timezone.utc),
            day_class="weekday",
        )
        db.add(slot)
        db.flush()
        db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
        other_slot = RosterSlot(
            planning_period_id=period.id,
            shift_template_id=template.id,
            shift_variant_id=variant.id,
            slot_date=slot_date + timedelta(days=1),
            position=1,
            day_class="weekday",
        )
        db.add(other_slot)
        db.flush()
        db.add(RosterSlotAssignment(roster_slot_id=other_slot.id, team_member_id=other_member.id))
        range_slot = RosterSlot(
            planning_period_id=period.id,
            shift_template_id=template.id,
            shift_variant_id=variant.id,
            slot_date=slot_date + timedelta(days=10),
            position=1,
            starts_at=datetime.combine(slot_date + timedelta(days=10), time(8, 0), tzinfo=timezone.utc),
            ends_at=datetime.combine(slot_date + timedelta(days=10), time(20, 0), tzinfo=timezone.utc),
            day_class="weekday",
        )
        db.add(range_slot)
        db.flush()
        db.add(RosterSlotAssignment(roster_slot_id=range_slot.id, team_member_id=member.id))
        db.commit()
        ctx.update(
            {
                "sg_id": sg.id,
                "period_id": period.id,
                "slot_id": slot.id,
                "other_slot_id": other_slot.id,
                "range_slot_id": range_slot.id,
                "slot_date": slot_date,
                "range_slot_date": slot_date + timedelta(days=10),
            }
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/login",
            json={"email": "doc@example.com", "password": "docsecret", "organization_slug": "default"},
        )
        yield client, ctx
    app.dependency_overrides.clear()


def _parse_ics(response) -> Calendar:
    assert response.status_code == 200
    assert "text/calendar" in response.headers.get("content-type", "")
    return Calendar.from_ical(response.content)


def test_export_single_slot_ics(ics_client):
    client, ctx = ics_client
    response = client.get(f"/api/v1/exports/roster-slots/{ctx['slot_id']}.ics")
    cal = _parse_ics(response)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1
    assert "Rufdienst" in str(events[0].get("summary"))


def test_export_single_slot_forbidden_for_other_member(ics_client):
    client, ctx = ics_client
    response = client.get(f"/api/v1/exports/roster-slots/{ctx['other_slot_id']}.ics")
    assert response.status_code in (403, 404)


def test_export_my_shifts_bulk(ics_client):
    client, ctx = ics_client
    response = client.get(f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}")
    cal = _parse_ics(response)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 2


def test_export_my_shifts_period(ics_client):
    client, ctx = ics_client
    response = client.get(
        f"/api/v1/exports/my-shifts/{ctx['period_id']}.ics?shift_group_id={ctx['sg_id']}"
    )
    cal = _parse_ics(response)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 2


def test_export_my_shifts_requires_shift_group(ics_client):
    client, _ctx = ics_client
    response = client.get("/api/v1/exports/my-shifts.ics")
    assert response.status_code == 422


def test_export_my_shifts_date_range(ics_client):
    client, ctx = ics_client
    slot_date = ctx["slot_date"]
    range_start = slot_date.isoformat()
    range_end = (slot_date + timedelta(days=5)).isoformat()
    response = client.get(
        f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}"
        f"&start_date={range_start}&end_date={range_end}"
    )
    cal = _parse_ics(response)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1


def test_export_my_shifts_date_range_empty(ics_client):
    client, ctx = ics_client
    slot_date = ctx["slot_date"]
    range_start = (slot_date + timedelta(days=20)).isoformat()
    range_end = (slot_date + timedelta(days=25)).isoformat()
    response = client.get(
        f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}"
        f"&start_date={range_start}&end_date={range_end}"
    )
    cal = _parse_ics(response)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 0


def test_export_my_shifts_date_range_requires_both_dates(ics_client):
    client, ctx = ics_client
    slot_date = ctx["slot_date"].isoformat()
    response = client.get(
        f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}&start_date={slot_date}"
    )
    assert response.status_code == 422
    response = client.get(
        f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}&end_date={slot_date}"
    )
    assert response.status_code == 422


def test_export_my_shifts_date_range_invalid_order(ics_client):
    client, ctx = ics_client
    slot_date = ctx["slot_date"]
    response = client.get(
        f"/api/v1/exports/my-shifts.ics?shift_group_id={ctx['sg_id']}"
        f"&start_date={(slot_date + timedelta(days=5)).isoformat()}"
        f"&end_date={slot_date.isoformat()}"
    )
    assert response.status_code == 422
