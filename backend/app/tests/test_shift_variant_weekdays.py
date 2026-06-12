from datetime import date

from app.services.holidays import classify_day
from fastapi.testclient import TestClient

pytest_plugins = ("app.tests.test_api",)


def login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "secret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def _create_template_with_variant(client: TestClient, variant_payload: dict) -> dict:
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": variant_payload.pop("_code"), "name": "Weekday test", "category": "other"},
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json=variant_payload,
    )
    assert variant.status_code == 200, variant.text
    return template


def test_shift_variant_mon_thu_excludes_friday_and_weekend(client: TestClient):
    login(client)
    _create_template_with_variant(
        client,
        {
            "_code": "MONTHU",
            "label": "Mon-Thu late",
            "start_day_class": "any",
            "start_weekdays": ["mon", "tue", "wed", "thu"],
            "include_holidays": False,
            "starts_at": "18:00:00",
            "ends_at": "22:00:00",
            "required_count": 1,
        },
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 6}).json()
    mon_thu_slots = [slot for slot in preview if slot["variant_label"] == "Mon-Thu late"]
    assert mon_thu_slots
    for slot in mon_thu_slots:
        weekday = date.fromisoformat(slot["slot_date"]).weekday()
        assert weekday in {0, 1, 2, 3}


def test_shift_variant_holiday_on_allowed_weekday_respects_include_holidays(client: TestClient):
    login(client)
    _create_template_with_variant(
        client,
        {
            "_code": "HOLTHU",
            "label": "Mon-Thu holiday",
            "start_day_class": "any",
            "start_weekdays": ["mon", "tue", "wed", "thu"],
            "include_holidays": False,
            "starts_at": "18:00:00",
            "ends_at": "22:00:00",
            "required_count": 1,
        },
    )
    assert classify_day(date(2025, 5, 1)) == "holiday"
    assert date(2025, 5, 1).weekday() == 3

    preview_excluded = client.post("/api/v1/shift-templates/preview", json={"year": 2025, "month": 5}).json()
    excluded = [slot for slot in preview_excluded if slot["slot_date"] == "2025-05-01"]
    assert not excluded

    template = client.get("/api/v1/shift-templates").json()
    match = next(item for item in template if item["code"] == "HOLTHU")
    variant = match["variants"][0]
    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={"include_holidays": True},
    )
    preview_included = client.post("/api/v1/shift-templates/preview", json={"year": 2025, "month": 5}).json()
    included = [slot for slot in preview_included if slot["slot_date"] == "2025-05-01"]
    assert len(included) == 1
    assert included[0]["variant_label"] == "Mon-Thu holiday"


def test_shift_variant_invalid_weekday_code_rejected(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "BADWD", "name": "Bad weekday", "category": "other"},
    ).json()
    response = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Bad",
            "start_day_class": "any",
            "start_weekdays": ["monday"],
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
        },
    )
    assert response.status_code == 422


def test_shift_variant_end_weekdays_enforced_for_overnight(client: TestClient):
    login(client)
    _create_template_with_variant(
        client,
        {
            "_code": "ENDWD",
            "label": "Weekday into weekend end",
            "start_day_class": "weekday",
            "end_day_class": None,
            "end_weekdays": ["sat"],
            "include_holidays": False,
            "starts_at": "20:00:00",
            "ends_at": "08:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 6}).json()
    matched = [slot for slot in preview if slot["variant_label"] == "Weekday into weekend end"]
    assert matched
    for slot in matched:
        start = date.fromisoformat(slot["slot_date"])
        end = start.fromordinal(start.toordinal() + 1)
        assert end.weekday() == 5


def test_shift_variant_empty_weekdays_falls_back_to_day_class(client: TestClient):
    login(client)
    _create_template_with_variant(
        client,
        {
            "_code": "FALLBK",
            "label": "Weekday only",
            "start_day_class": "weekday",
            "start_weekdays": [],
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "required_count": 1,
        },
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 5}).json()
    weekday_slots = [slot for slot in preview if slot["variant_label"] == "Weekday only"]
    assert weekday_slots
    holiday_slots = [slot for slot in weekday_slots if slot["slot_date"] == "2026-05-01"]
    assert not holiday_slots
    saturday_slots = [slot for slot in weekday_slots if slot["slot_date"] == "2026-05-02"]
    assert not saturday_slots
