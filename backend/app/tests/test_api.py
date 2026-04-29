from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import User
from app.models.base import Base


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
        db.add(User(email="admin@example.com", hashed_password=hash_password("secret"), role="admin", locale="de"))
        db.commit()

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


def login(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert response.status_code == 200


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_auth_and_doctor_crud(client: TestClient):
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    response = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Ada Lovelace", "email": "ada@example.com", "employment_percentage": 80},
    )
    assert response.status_code == 200
    assert response.json()["employment_percentage"] == 80
    assert client.get("/api/v1/doctors").json()[0]["email"] == "ada@example.com"


def test_roster_validation_no_go_conflict(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Max Planck", "email": "max@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "N",
            "name_de": "Nachtdienst",
            "name_en": "Night shift",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Nacht",
            "start_day_class": "any",
            "starts_at": "20:00:00",
            "ends_at": "08:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    request_date = date(2026, 5, 3).isoformat()
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(slot for slot in roster_matrix["slots"] if slot["slot_date"] == request_date)
    client.put(
        f"/api/v1/matrix/{period_id}/cells",
        json={"doctor_id": doctor_id, "cell_date": request_date, "status": "kein_dienst"},
    )
    client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "doctor_id": doctor_id},
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert warnings[0]["code"] == "ROSTER_MATRIX_UNAVAILABLE_CONFLICT"


def test_matrix_cell_note_and_csv_export(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Matrix", "email": "matrix@example.com", "employment_percentage": 100},
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]

    response = client.put(
        f"/api/v1/matrix/{period_id}/cells",
        json={
            "doctor_id": doctor_id,
            "cell_date": "2026-07-11",
            "status": "urlaub",
            "comment": "Urlaub aus E-Mail",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "urlaub"

    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert matrix["doctors"][0]["email"] == "matrix@example.com"
    assert matrix["cells"][0]["comment"] == "Urlaub aus E-Mail"

    note = client.put(
        f"/api/v1/matrix/{period_id}/notes",
        json={
            "doctor_id": doctor_id,
            "source_text": "Hallo Christian, im Juli Urlaub vom 11.-19.07.",
            "summary": "Urlaub 11.-19.07.",
        },
    )
    assert note.status_code == 200
    assert note.json()["summary"] == "Urlaub 11.-19.07."

    csv_response = client.get(f"/api/v1/exports/matrix/{period_id}.csv")
    assert csv_response.status_code == 200
    assert "2026-07-11" in csv_response.text
    assert "urlaub - Urlaub aus E-Mail" in csv_response.text


def test_matrix_bulk_upsert_and_clear(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Bulk", "email": "bulk@example.com", "employment_percentage": 80},
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]

    response = client.put(
        f"/api/v1/matrix/{period_id}/cells/bulk",
        json={
            "cells": [
                {"doctor_id": doctor_id, "cell_date": "2026-08-01", "status": "tagdienst"},
                {
                    "doctor_id": doctor_id,
                    "cell_date": "2026-08-02",
                    "status": "nachtdienst",
                    "comment": "Wochenendkombination",
                },
            ]
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 2

    clear_response = client.post(
        f"/api/v1/matrix/{period_id}/cells/clear",
        json={"doctor_id": doctor_id, "cell_date": "2026-08-01"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted"] is True

    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert len(matrix["cells"]) == 1
    assert matrix["cells"][0]["status"] == "nachtdienst"


def test_roster_matrix_assignment_validation_and_csv(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Roster", "email": "roster@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "T",
            "name_de": "Tagdienst",
            "name_en": "Day shift",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Tagdienst",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]

    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert roster_matrix["shift_templates"][0]["code"] == "T"
    assert len(roster_matrix["slots"]) == 31
    slot = next(slot for slot in roster_matrix["slots"] if slot["slot_date"] == "2026-07-11")

    assignment_response = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "doctor_id": doctor_id, "comment": "final geplant"},
    )
    assert assignment_response.status_code == 200
    assert assignment_response.json()["doctor_id"] == doctor_id

    client.put(
        f"/api/v1/matrix/{period_id}/cells",
        json={"doctor_id": doctor_id, "cell_date": "2026-07-11", "status": "urlaub"},
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert warnings[0]["code"] == "ROSTER_MATRIX_UNAVAILABLE_CONFLICT"

    csv_response = client.get(f"/api/v1/exports/roster-matrix/{period_id}.csv")
    assert csv_response.status_code == 200
    assert "2026-07-11" in csv_response.text
    assert "Tagdienst" in csv_response.text
    assert "Dr. Roster" in csv_response.text
    assert "final geplant" not in csv_response.text

    clear_response = client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted"] is True


def test_create_shift_template_rejects_duplicate_code(client: TestClient):
    login(client)
    body = {"code": "DUPX", "name_de": "Eins", "name_en": "One", "category": "other"}
    assert client.post("/api/v1/shift-templates", json=body).status_code == 200
    conflict = client.post("/api/v1/shift-templates", json={**body, "name_de": "Zwei"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SHIFT_TEMPLATE_CODE_TAKEN"
    assert conflict.json()["detail"]["value"] == "DUPX"


def test_patch_shift_template_rejects_duplicate_code(client: TestClient):
    login(client)
    first = client.post(
        "/api/v1/shift-templates",
        json={"code": "P1", "name_de": "a", "name_en": "a", "category": "other"},
    ).json()
    client.post(
        "/api/v1/shift-templates",
        json={"code": "P2", "name_de": "b", "name_en": "b", "category": "other"},
    )
    conflict = client.patch(f"/api/v1/shift-templates/{first['id']}", json={"code": "P2"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SHIFT_TEMPLATE_CODE_TAKEN"


def test_shift_template_variants_holidays_and_generated_slots(client: TestClient):
    login(client)
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "BD",
            "name_de": "Bereitschaftsdienst",
            "name_en": "On-call duty",
            "category": "bereitschaftsdienst",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Wochentag",
            "start_day_class": "weekday",
            "end_day_class": "weekend",
            "starts_at": "15:45:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Wochenende Nacht",
            "start_day_class": "weekend",
            "starts_at": "20:00:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 2,
        },
    )
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Feiertag Nacht",
            "start_day_class": "holiday",
            "starts_at": "20:00:00",
            "ends_at": "09:00:00",
            "end_day_offset": 1,
            "required_count": 1,
        },
    )
    preview = client.post("/api/v1/shift-templates/preview", json={"year": 2026, "month": 5}).json()
    holiday_slots = [slot for slot in preview if slot["slot_date"] == "2026-05-01"]
    assert holiday_slots
    assert holiday_slots[0]["day_class"] == "holiday"
    assert [slot["variant_label"] for slot in holiday_slots] == ["Feiertag Nacht"]

    saturday_slots = [
        slot for slot in preview if slot["slot_date"] == "2026-05-02" and slot["variant_label"] == "Wochenende Nacht"
    ]
    assert len(saturday_slots) == 2

    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    generated = [slot for slot in roster_matrix["slots"] if slot["slot_date"] == "2026-05-01"]
    assert generated[0]["starts_at"]
    assert generated[0]["template_code"] == "BD"


def test_regenerate_roster_slots_clears_assignments_and_updates_slots(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Reset", "email": "reset@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "RESET",
            "name_de": "Resetdienst",
            "name_en": "Reset duty",
            "category": "other",
        },
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert len(roster_matrix["slots"]) == 30
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doctor_id})

    client.patch(
        f"/api/v1/shift-templates/variants/{variant['id']}",
        json={"required_count": 2},
    )
    regenerated = client.post(f"/api/v1/planning-periods/{period_id}/regenerate-roster")
    assert regenerated.status_code == 200
    regenerated_json = regenerated.json()
    assert len(regenerated_json["slots"]) == 60
    assert regenerated_json["assignments"] == []


def test_delete_shift_variant_clears_generated_slots_and_assignments(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Variant Delete", "email": "variant-delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "VD",
            "name_de": "Variantendienst",
            "name_en": "Variant duty",
            "category": "other",
        },
    ).json()
    variant = client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 9}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doctor_id})

    delete_response = client.delete(f"/api/v1/shift-templates/variants/{variant['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    templates = client.get("/api/v1/shift-templates").json()
    updated_template = next(item for item in templates if item["id"] == template["id"])
    assert updated_template["variants"] == []

    next_roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert next_roster_matrix["slots"] == []
    assert next_roster_matrix["assignments"] == []


def test_delete_planning_period_removes_period_and_related_data(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Delete", "email": "delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    client.put(
        f"/api/v1/matrix/{period_id}/cells",
        json={"doctor_id": doctor_id, "cell_date": "2026-10-01", "status": "urlaub"},
    )
    client.put(
        f"/api/v1/matrix/{period_id}/notes",
        json={"doctor_id": doctor_id, "source_text": "Quelle", "summary": "Zusammenfassung"},
    )

    delete_response = client.delete(f"/api/v1/planning-periods/{period_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert all(period["id"] != period_id for period in client.get("/api/v1/planning-periods").json())
    assert client.get(f"/api/v1/roster-matrix/{period_id}").status_code == 404


def test_delete_shift_template_clears_generated_slots_and_assignments(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Template Delete", "email": "template-delete@example.com", "employment_percentage": 100},
    ).json()["id"]
    template = client.post(
        "/api/v1/shift-templates",
        json={
            "code": "DEL",
            "name_de": "Löschdienst",
            "name_en": "Delete duty",
            "category": "other",
        },
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Täglich",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 11}).json()["id"]
    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = roster_matrix["slots"][0]
    client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doctor_id})

    delete_response = client.delete(f"/api/v1/shift-templates/{template['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert all(item["id"] != template["id"] for item in client.get("/api/v1/shift-templates").json())
    next_roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert next_roster_matrix["slots"] == []
    assert next_roster_matrix["assignments"] == []


def test_delete_doctor_clears_related_data(client: TestClient):
    login(client)
    doctor = client.post(
        "/api/v1/doctors",
        json={"name": "Dr. Purge", "email": "purge@example.com", "employment_percentage": 80},
    ).json()
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 12}).json()["id"]
    client.put(
        f"/api/v1/matrix/{period_id}/cells",
        json={"doctor_id": doctor["id"], "cell_date": "2026-12-01", "status": "urlaub"},
    )
    client.put(
        f"/api/v1/matrix/{period_id}/notes",
        json={"doctor_id": doctor["id"], "source_text": "mail", "summary": "summary"},
    )

    delete_response = client.delete(f"/api/v1/doctors/{doctor['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    doctors = client.get("/api/v1/doctors").json()
    assert all(item["id"] != doctor["id"] for item in doctors)
    matrix = client.get(f"/api/v1/matrix/{period_id}").json()
    assert matrix["cells"] == []
    notes = client.get(f"/api/v1/matrix/{period_id}/notes").json()
    assert notes == []
