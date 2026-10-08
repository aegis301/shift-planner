from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
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


def _day_slots(client: TestClient, period_id: int, day: date) -> list[dict]:
    slots = client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]
    return [slot for slot in slots if slot["slot_date"] == day.isoformat()]


def _member(client: TestClient, email: str) -> int:
    return client.post(
        "/api/v1/team-members",
        json={"first_name": "Hol", "last_name": email.split("@")[0], "email": email, "employment_percentage": 100},
    ).json()["id"]


def _assign(client: TestClient, slot_id: int, member_id: int) -> None:
    response = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot_id, "team_member_id": member_id},
    )
    assert response.status_code == 200, response.text


def _assignee(client: TestClient, period_id: int, slot_id: int) -> int | None:
    assignments = client.get(f"/api/v1/roster-matrix/{period_id}").json()["assignments"]
    return next((row["team_member_id"] for row in assignments if row["roster_slot_id"] == slot_id), None)


def test_preview_uses_holiday_variant(client: TestClient):
    login(client)
    _bd_template_with_holiday_variant(client)
    client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "DAC Kongress"},
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 9}).json()
    congress_preview = [slot for slot in preview if slot["slot_date"] == CONGRESS_DAY.isoformat()]
    assert [(slot["day_class"], slot["variant_label"]) for slot in congress_preview] == [("holiday", "Feiertag")]


def test_adding_and_deleting_a_holiday_replans_existing_month_and_keeps_assignee(client: TestClient):
    login(client)
    _bd_template_with_holiday_variant(client)
    member_id = _member(client, "keep@example.com")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    [weekday_slot] = _day_slots(client, period_id, CONGRESS_DAY)
    assert weekday_slot["day_class"] == "weekday"
    _assign(client, weekday_slot["id"], member_id)
    untouched_before = {
        slot["id"]: slot for slot in client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]
    }

    created = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "DAC Kongress"},
    )
    assert created.status_code == 201, created.text
    sync = created.json()["roster_sync"]
    assert sync["planning_period_ids"] == [period_id]
    assert sync["slots_updated"] == 1
    assert sync["assignments_kept"] == 1
    assert sync["assignments_cleared"] == 0
    assert sync["slots_added"] == sync["slots_removed"] == 0
    [holiday_slot] = _day_slots(client, period_id, CONGRESS_DAY)
    assert holiday_slot["id"] == weekday_slot["id"]
    assert holiday_slot["day_class"] == "holiday"
    assert holiday_slot["variant_label"] == "Feiertag"
    assert _assignee(client, period_id, holiday_slot["id"]) == member_id

    # Every other day is exactly as before.
    for slot in client.get(f"/api/v1/roster-matrix/{period_id}").json()["slots"]:
        if slot["slot_date"] != CONGRESS_DAY.isoformat():
            assert slot == untouched_before[slot["id"]]

    deleted = client.delete(f"/api/v1/organization-holidays/{created.json()['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["roster_sync"]["assignments_kept"] == 1
    [restored] = _day_slots(client, period_id, CONGRESS_DAY)
    assert (restored["id"], restored["day_class"], restored["variant_label"]) == (
        weekday_slot["id"],
        "weekday",
        "Werktag",
    )
    assert _assignee(client, period_id, restored["id"]) == member_id


def test_moving_a_holiday_replans_old_and_new_day(client: TestClient):
    login(client)
    _bd_template_with_holiday_variant(client)
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    assert _day_slots(client, period_id, CONGRESS_DAY)
    created = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    ).json()
    next_day = CONGRESS_DAY + timedelta(days=1)
    moved = client.patch(f"/api/v1/organization-holidays/{created['id']}", json={"holiday_date": next_day.isoformat()})
    assert moved.status_code == 200, moved.text
    assert moved.json()["roster_sync"]["slots_updated"] == 2
    assert [slot["day_class"] for slot in _day_slots(client, period_id, CONGRESS_DAY)] == ["weekday"]
    assert [slot["day_class"] for slot in _day_slots(client, period_id, next_day)] == ["holiday"]

    renamed = client.patch(f"/api/v1/organization-holidays/{created['id']}", json={"label": "Renamed"})
    assert renamed.json()["roster_sync"]["planning_period_ids"] == []


def test_replan_clears_positions_without_counterpart(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "TWO", "name": "Two", "category": "other"},
    ).json()
    for label, day_class, count in (("Werktag", "weekday", 2), ("Wochenende", "weekend", 1), ("Feiertag", "holiday", 1)):
        client.post(
            f"/api/v1/shift-templates/{template['id']}/variants",
            json={
                "label": label,
                "start_day_class": day_class,
                "starts_at": "08:00:00",
                "ends_at": "16:00:00",
                "required_count": count,
            },
        )
    first, second = _member(client, "first@example.com"), _member(client, "second@example.com")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    slots = sorted(_day_slots(client, period_id, CONGRESS_DAY), key=lambda slot: slot["position"])
    _assign(client, slots[0]["id"], first)
    _assign(client, slots[1]["id"], second)

    sync = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    ).json()["roster_sync"]
    assert (sync["assignments_kept"], sync["assignments_cleared"], sync["slots_removed"]) == (1, 1, 1)
    [kept] = _day_slots(client, period_id, CONGRESS_DAY)
    assert (kept["id"], kept["position"], kept["day_class"]) == (slots[0]["id"], 1, "holiday")
    assert _assignee(client, period_id, kept["id"]) == first

    holiday_id = client.get("/api/v1/organization-holidays").json()[0]["id"]
    back = client.delete(f"/api/v1/organization-holidays/{holiday_id}").json()["roster_sync"]
    assert (back["slots_updated"], back["slots_added"]) == (1, 1)
    assert sorted(slot["position"] for slot in _day_slots(client, period_id, CONGRESS_DAY)) == [1, 2]


def test_replan_covers_overnight_slots_ending_on_the_holiday(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "NIGHT", "name": "Night", "category": "bereitschaftsdienst"},
    ).json()
    for label, end_class in (("Nacht vor Werktag", "weekday"), ("Nacht vor Feiertag", "holiday")):
        client.post(
            f"/api/v1/shift-templates/{template['id']}/variants",
            json={
                "label": label,
                "start_day_class": "weekday",
                "end_day_class": end_class,
                "starts_at": "20:00:00",
                "ends_at": "08:00:00",
                "end_day_offset": 1,
            },
        )
    member_id = _member(client, "night@example.com")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    eve = CONGRESS_DAY - timedelta(days=1)
    [eve_slot] = _day_slots(client, period_id, eve)
    assert eve_slot["variant_label"] == "Nacht vor Werktag"
    _assign(client, eve_slot["id"], member_id)

    client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    )
    [eve_after] = _day_slots(client, period_id, eve)
    assert (eve_after["id"], eve_after["variant_label"]) == (eve_slot["id"], "Nacht vor Feiertag")
    assert _assignee(client, period_id, eve_after["id"]) == member_id


def test_replan_leaves_published_groups_alone_and_reports_them(client: TestClient):
    login(client)
    template = _bd_template_with_holiday_variant(client)
    client.put("/api/v1/shift-groups/1/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    [before] = _day_slots(client, period_id, CONGRESS_DAY)
    assert client.post(f"/api/v1/planning-periods/{period_id}/publish?shift_group_id=1").status_code == 200

    sync = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    ).json()["roster_sync"]
    assert sync["slots_updated"] == 0
    assert [(row["planning_period_id"], row["shift_group_id"], row["shift_group_name"]) for row in sync["skipped_published"]] == [
        (period_id, 1, "Default SG")
    ]
    assert _day_slots(client, period_id, CONGRESS_DAY) == [before]


def test_same_variant_reclassified_counts_the_kept_assignee(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "ANY", "name": "Any day", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={"label": "Täglich", "start_day_class": "any", "starts_at": "08:00:00", "ends_at": "16:00:00"},
    )
    member_id = _member(client, "anyday@example.com")
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    [slot] = _day_slots(client, period_id, CONGRESS_DAY)
    _assign(client, slot["id"], member_id)

    sync = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    ).json()["roster_sync"]
    assert (sync["slots_updated"], sync["assignments_kept"], sync["assignments_cleared"]) == (1, 1, 0)
    [after] = _day_slots(client, period_id, CONGRESS_DAY)
    assert (after["id"], after["day_class"]) == (slot["id"], "holiday")
    assert _assignee(client, period_id, after["id"]) == member_id


def test_replan_skips_a_month_whose_roster_was_never_generated(client: TestClient):
    login(client)
    _bd_template_with_holiday_variant(client)
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    sync = client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    ).json()["roster_sync"]
    assert sync["planning_period_ids"] == []
    assert [slot["day_class"] for slot in _day_slots(client, period_id, CONGRESS_DAY)] == ["holiday"]


def test_replan_does_not_apply_unsynced_template_changes_to_other_days(client: TestClient):
    login(client)
    template = _bd_template_with_holiday_variant(client)
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    weekday_variant = next(
        variant for variant in client.get("/api/v1/shift-templates").json()[0]["variants"] if variant["label"] == "Werktag"
    )
    client.patch(f"/api/v1/shift-templates/variants/{weekday_variant['id']}", json={"starts_at": "07:00:00"})
    other_day = date(2026, 9, 22)
    [before] = _day_slots(client, period_id, other_day)

    client.post(
        "/api/v1/organization-holidays",
        json={"holiday_date": CONGRESS_DAY.isoformat(), "label": "Kongress"},
    )
    assert _day_slots(client, period_id, other_day) == [before]
    assert template["id"] == before["shift_template_id"]


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


def test_concurrent_duplicate_date_is_a_validation_error(monkeypatch):
    from app.schemas import OrganizationHolidayCreate, OrganizationHolidayUpdate
    from app.services import organization_holidays as service

    db = _session()
    db.add(OrganizationHoliday(organization_id=1, holiday_date=CONGRESS_DAY, label="First"))
    db.commit()
    other, _sync = service.create_organization_holiday(
        db,
        OrganizationHolidayCreate(holiday_date=date(2026, 9, 16), label="Second"),
        organization_id=1,
        actor="test",
        source="test",
    )
    # Simulate the race: the pre-check misses the row another request just committed.
    monkeypatch.setattr(service, "_date_taken", lambda *args, **kwargs: False)
    with pytest.raises(ValueError, match="already"):
        service.create_organization_holiday(
            db,
            OrganizationHolidayCreate(holiday_date=CONGRESS_DAY, label="Race"),
            organization_id=1,
            actor="test",
            source="test",
        )
    with pytest.raises(ValueError, match="already"):
        service.update_organization_holiday(
            db,
            other.id,
            OrganizationHolidayUpdate(holiday_date=CONGRESS_DAY),
            organization_id=1,
            actor="test",
            source="test",
        )
    assert sorted(service.organization_holiday_dates(db, organization_id=1)) == [CONGRESS_DAY, date(2026, 9, 16)]


def test_replan_revalues_time_entries_both_ways():
    from app.schemas import OrganizationHolidayCreate
    from app.services.organization_holidays import (
        create_organization_holiday,
        delete_organization_holiday,
    )
    from app.services.roster_matrix import ensure_roster_slots_for_period

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
    member = TeamMember(organization_id=1, first_name="Pat", last_name="Revalue", email="revalue@example.com")
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
    for label, day_class in (("Werktag", "weekday"), ("Wochenende", "weekend"), ("Feiertag", "holiday")):
        db.add(
            ShiftVariant(
                shift_template_id=template.id,
                label=label,
                start_day_class=day_class,
                starts_at=time(8, 0),
                ends_at=time(8, 0),
                end_day_offset=1,
                required_count=1,
            )
        )
    period = PlanningPeriod(organization_id=1, year=2026, month=9, status="draft")
    db.add(period)
    db.commit()
    slots = ensure_roster_slots_for_period(db, period.id, 1)
    db.commit()
    [slot] = [row for row in slots if row.slot_date == CONGRESS_DAY]
    db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
    db.commit()
    window = {"start_date": date(2026, 9, 1), "end_date": date(2026, 9, 30)}
    derive_entries(db, organization_id=1, member_ids=[member.id], **window)

    def entry():
        [row] = list_time_entries(db, organization_id=1, team_member_id=member.id, **window)
        return row.roster_slot_id, row.statutory_minutes, row.credited_minutes

    assert entry() == (slot.id, 1440, 864)
    holiday, sync = create_organization_holiday(
        db,
        OrganizationHolidayCreate(holiday_date=CONGRESS_DAY, label="Kongress"),
        organization_id=1,
        actor="test",
        source="test",
    )
    assert sync.assignments_kept == 1
    assert entry() == (slot.id, 1440, 1224)
    delete_organization_holiday(db, holiday.id, organization_id=1, actor="test", source="test")
    assert entry() == (slot.id, 1440, 864)
