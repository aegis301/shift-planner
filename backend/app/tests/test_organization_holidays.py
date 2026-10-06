from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    ContractGroup,
    EmploymentPeriod,
    Organization,
    OrganizationHoliday,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
)
from app.models.base import Base
from app.schemas import ContractCategoryRule
from app.services.fairness import _day_matches_filter
from app.services.holidays import classify_day
from app.services.organization_holidays import organization_holiday_dates
from app.services.time_entries import derive_entries, list_time_entries
from app.services.workload import (
    WorkloadAssignmentSlice,
    WorkloadMemberSlice,
    WorkloadSlotSlice,
    build_member_workload_rows,
)
from app.tests.test_api import login

pytest_plugins = ("app.tests.test_api",)

# Tuesday, not an NRW holiday.
CONGRESS_DAY = date(2026, 9, 15)

STUFE_I_WITH_BONUS = ContractCategoryRule(
    category="bereitschaftsdienst",
    credit_mode="factor",
    credit_factor=Decimal("0.6"),
    holiday_credit_bonus=Decimal("25"),
    statutory_factor=Decimal("1"),
)


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.add(Organization(id=2, name="Other", slug="other", plan_tier="team"))
    db.commit()
    return db


def _bd_template_with_holiday_variant(client: TestClient) -> dict:
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "BDH", "name": "Bereitschaft", "category": "bereitschaftsdienst"},
    ).json()
    for label, day_class in (("Werktag", "weekday"), ("Wochenende", "weekend"), ("Feiertag", "holiday")):
        response = client.post(
            f"/api/v1/shift-templates/{template['id']}/variants",
            json={
                "label": label,
                "start_day_class": day_class,
                "starts_at": "08:00:00",
                "ends_at": "08:00:00",
                "end_day_offset": 1,
                "required_count": 1,
            },
        )
        assert response.status_code == 200, response.text
    return template


def test_classify_day_honours_extra_holidays():
    assert classify_day(CONGRESS_DAY) == "weekday"
    assert classify_day(CONGRESS_DAY, {CONGRESS_DAY}) == "holiday"
    saturday = date(2026, 9, 19)
    assert classify_day(saturday, {saturday}) == "holiday"
    assert classify_day(date(2026, 5, 1), set()) == "holiday"


def test_organization_holiday_crud(client: TestClient):
    login(client)
    created = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "  DAC Kongress "},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["label"] == "DAC Kongress"
    assert body["holiday_date"] == "2026-09-15"

    duplicate = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Again"},
    )
    assert duplicate.status_code == 400

    second = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": "2026-12-24", "label": "Heiligabend"},
    ).json()
    moved = client.patch(f"/api/v1/organization-holidays/{second['id']}", json={"holiday_date": "2026-09-15"})
    assert moved.status_code == 400
    renamed = client.patch(f"/api/v1/organization-holidays/{second['id']}", json={"label": "Christmas Eve"})
    assert renamed.status_code == 200
    assert renamed.json()["label"] == "Christmas Eve"

    listed = client.get("/api/v1/organization-holidays").json()
    assert [row["holiday_date"] for row in listed] == ["2026-09-15", "2026-12-24"]
    ranged = client.get("/api/v1/organization-holidays?from=2026-12-01&to=2026-12-31").json()
    assert [row["label"] for row in ranged] == ["Christmas Eve"]

    assert client.delete(f"/api/v1/organization-holidays/{second['id']}").status_code == 200
    assert client.delete(f"/api/v1/organization-holidays/{second['id']}").status_code == 404
    assert client.patch("/api/v1/organization-holidays/9999", json={"label": "x"}).status_code == 404


def test_organization_holiday_writes_are_admin_only(team_member_client: TestClient):
    response = team_member_client.post(
        "/api/v1/auth/login", json={"email": "doc@example.com", "password": "docsecret"}
    )
    assert response.status_code == 200
    assert team_member_client.get("/api/v1/organization-holidays").status_code == 200
    denied = team_member_client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    )
    assert denied.status_code == 403


def test_organization_holiday_dates_are_scoped_to_the_organization():
    db = _session()
    db.add(OrganizationHoliday(organization_id=2, holiday_date=CONGRESS_DAY, label="Other org"))
    db.commit()
    assert organization_holiday_dates(db, organization_id=1) == frozenset()
    assert organization_holiday_dates(db, organization_id=2) == frozenset({CONGRESS_DAY})
    assert organization_holiday_dates(
        db, organization_id=2, start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)
    ) == frozenset()


def test_generated_slots_use_holiday_variant_and_sync_moves_existing_month(client: TestClient):
    login(client)
    _bd_template_with_holiday_variant(client)
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    before = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]
    congress_before = [slot for slot in before if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert [slot["day_class"] for slot in congress_before] == ["weekday"]

    client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "DAC Kongress"},
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 9}).json()
    congress_preview = [slot for slot in preview if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert [(slot["day_class"], slot["variant_label"]) for slot in congress_preview] == [("holiday", "Feiertag")]

    # Existing rosters are not rewritten until the planner syncs.
    unchanged = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]
    assert [slot["day_class"] for slot in unchanged if slot["slot_date"] == CONGRESS_DAY.isoformat()] == [
        "weekday"
    ]
    sync = client.post(f"/api/v1/planning-periods/{period_id}/sync-roster")
    assert sync.status_code == 200, sync.text
    assert sync.json()["sync"]["added_count"] == 1
    assert sync.json()["sync"]["removed_count"] == 1
    after = [slot for slot in sync.json()["matrix"]["slots"] if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert [slot["day_class"] for slot in after] == ["holiday"]

    holiday_id = client.get("/api/v1/organization-holidays").json()[0]["id"]
    assert client.delete(f"/api/v1/organization-holidays/{holiday_id}").status_code == 200
    reread = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]
    assert [slot["day_class"] for slot in reread if slot["slot_date"] == CONGRESS_DAY.isoformat()] == [
        "holiday"
    ]
    resync = client.post(f"/api/v1/planning-periods/{period_id}/sync-roster").json()
    restored = [slot for slot in resync["matrix"]["slots"] if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert [slot["day_class"] for slot in restored] == ["weekday"]


def test_holiday_without_holiday_variant_falls_back_to_weekend(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "WE", "name": "Weekend", "category": "other"},
    ).json()
    for label, day_class in (("Werktag", "weekday"), ("Wochenende", "weekend")):
        client.post(
            f"/api/v1/shift-templates/{template['id']}/variants",
            json={"label": label, "start_day_class": day_class, "starts_at": "08:00:00", "ends_at": "16:00:00"},
        )
    client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Klausurtag"},
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 9}).json()
    labels = [slot["variant_label"] for slot in preview if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert labels == ["Wochenende"]


def test_derived_time_entry_gets_holiday_credit_bonus():
    db = _session()
    group = ContractGroup(
        organization_id=1,
        name="Standard",
        weekly_hours_at_100=Decimal("40"),
        vacation_days_at_100=Decimal("30"),
        regular_week_pattern=[],
        category_rules=[STUFE_I_WITH_BONUS.model_dump(mode="json")],
        status_mappings=[],
    )
    member = TeamMember(organization_id=1, first_name="Pat", last_name="Holiday", email="holiday@example.com")
    template = ShiftTemplate(organization_id=1, code="BD", name="BD", category="bereitschaftsdienst")
    db.add_all([group, member, template])
    db.flush()
    db.add(
        EmploymentPeriod(
            team_member_id=member.id,
            contract_group_id=group.id,
            employment_percentage=100,
            start_date=date(2000, 1, 1),
        )
    )
    variant = ShiftVariant(
        shift_template_id=template.id,
        label="24h",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(8, 0),
        end_day_offset=1,
        required_count=1,
    )
    period = PlanningPeriod(organization_id=1, year=2026, month=9, status="draft")
    db.add_all([variant, period])
    db.flush()
    slots = []
    for day in (date(2026, 9, 14), CONGRESS_DAY):
        start = datetime.combine(day, time(6, 0), tzinfo=UTC)
        slot = RosterSlot(
            planning_period_id=period.id,
            shift_template_id=template.id,
            shift_variant_id=variant.id,
            slot_date=day,
            position=1,
            starts_at=start,
            ends_at=start + timedelta(hours=24),
        )
        db.add(slot)
        slots.append(slot)
    db.flush()
    for slot in slots:
        db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
    db.add(OrganizationHoliday(organization_id=1, holiday_date=CONGRESS_DAY, label="Kongress"))
    db.commit()

    derive_entries(
        db, organization_id=1, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30), member_ids=[member.id]
    )
    rows = list_time_entries(
        db, organization_id=1, team_member_id=member.id, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30)
    )
    credited = {row.entry_date: row.credited_minutes for row in rows}
    statutory = {row.entry_date: row.statutory_minutes for row in rows}
    assert credited == {date(2026, 9, 14): 864, CONGRESS_DAY: 1224}
    assert statutory == {date(2026, 9, 14): 1440, CONGRESS_DAY: 1440}


def test_fairness_and_workload_count_organization_holidays():
    assert not _day_matches_filter(CONGRESS_DAY, "weekend_holiday", False, False)
    assert _day_matches_filter(CONGRESS_DAY, "weekend_holiday", False, False, frozenset({CONGRESS_DAY}))

    slots = [
        WorkloadSlotSlice(
            id=1,
            shift_template_id=1,
            category="other",
            slot_date=CONGRESS_DAY,
            starts_at=None,
            ends_at=None,
            organization_holiday=True,
        ),
        WorkloadSlotSlice(
            id=2, shift_template_id=1, category="other", slot_date=date(2026, 9, 14), starts_at=None, ends_at=None
        ),
    ]
    rows, _ = build_member_workload_rows(
        slots=slots,
        assignments=[
            WorkloadAssignmentSlice(roster_slot_id=1, team_member_id=7),
            WorkloadAssignmentSlice(roster_slot_id=2, team_member_id=7),
        ],
        members=[WorkloadMemberSlice(id=7, first_name="A", last_name="B", nickname=None, employment_percentage=100)],
        warnings=[],
    )
    assert rows[0].total == 2
    assert rows[0].weekend_holiday_shifts == 1
