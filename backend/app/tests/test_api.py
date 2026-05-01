from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Doctor, DoctorShiftGroup, Organization, ShiftGroup, User, UserShiftGroup
from app.services.authz import ROLE_PLANNER
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
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        db.add(
            User(
                email="admin@example.com",
                hashed_password=hash_password("secret"),
                role="admin",
                locale="de",
                organization_id=1,
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def doctor_client():
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
        db.add(
            User(
                email="admin@example.com",
                hashed_password=hash_password("secret"),
                role="admin",
                locale="de",
                organization_id=1,
            )
        )
        doc_user = User(
            email="doc@example.com",
            hashed_password=hash_password("docsecret"),
            role="doctor",
            locale="de",
            organization_id=1,
        )
        db.add(doc_user)
        db.flush()
        doctor = Doctor(
            organization_id=1,
            first_name="Seeded",
            last_name="Doctor",
            email="docperson@example.com",
            employment_percentage=100,
            user_id=doc_user.id,
        )
        db.add(doctor)
        db.flush()
        sg = ShiftGroup(organization_id=1, code="docsg", name_de="Doc G", name_en="Doc G", display_order=0)
        db.add(sg)
        db.flush()
        db.add(DoctorShiftGroup(doctor_id=doctor.id, shift_group_id=sg.id))
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
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "secret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def login_doctor(cl: TestClient) -> None:
    response = cl.post(
        "/api/v1/auth/login",
        json={
            "email": "doc@example.com",
            "password": "docsecret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_delete_own_account_wrong_password(client: TestClient):
    login(client)
    response = client.post("/api/v1/auth/delete-account", json={"password": "wrong"})
    assert response.status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_own_account_sole_admin_forbidden(client: TestClient):
    login(client)
    response = client.post("/api/v1/auth/delete-account", json={"password": "secret"})
    assert response.status_code == 400
    assert "only" in response.json()["detail"].lower() and "admin" in response.json()["detail"].lower()
    assert client.get("/api/v1/auth/me").status_code == 200


def test_delete_own_account_doctor_user(doctor_client: TestClient):
    login_doctor(doctor_client)
    response = doctor_client.post("/api/v1/auth/delete-account", json={"password": "docsecret"})
    assert response.status_code == 204
    assert doctor_client.get("/api/v1/auth/me").status_code == 401


def test_auth_me_includes_organization(client: TestClient):
    login(client)
    data = client.get("/api/v1/auth/me").json()
    assert data["organization_id"] == 1
    assert data["organization"]["id"] == 1
    assert data["organization"]["name"] == "Default"
    assert data["organization"]["slug"] == "default"
    assert data["organization"]["plan_tier"] == "team"


def test_organization_users_list_for_admin(client: TestClient):
    login(client)
    response = client.get("/api/v1/organization/users")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    admin_row = next(r for r in rows if r["email"] == "admin@example.com")
    assert admin_row["role"] == "admin"
    assert admin_row["id"] >= 1


def test_organization_users_forbidden_for_doctor(doctor_client: TestClient):
    login_doctor(doctor_client)
    assert doctor_client.get("/api/v1/organization/users").status_code == 403


def test_register_create_organization(client: TestClient):
    response = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "New Hospital",
            "organization_slug": "new-hospital-test",
            "email": "founder@regtest.example",
            "password": "founderpass1",
            "locale": "en",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"
    assert data["organization"]["slug"] == "new-hospital-test"
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == "founder@regtest.example"


def test_register_join_and_approve_create_doctor(client: TestClient):
    r0 = client.post(
        "/api/v1/auth/register/create-organization",
        json={
            "organization_name": "Join Flow Org",
            "organization_slug": "join-flow-org",
            "email": "owner@joinflow.example",
            "password": "ownerpass12",
            "locale": "de",
        },
    )
    assert r0.status_code == 200
    client.post("/api/v1/auth/logout")
    r1 = client.post(
        "/api/v1/auth/register/join-organization",
        json={
            "organization_slug": "join-flow-org",
            "email": "joiner@joinflow.example",
            "password": "joinerpass12",
            "first_name": "Join",
            "last_name": "Er",
            "locale": "de",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["role"] == "applicant"
    client.post("/api/v1/auth/logout")
    login_owner = client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@joinflow.example",
            "password": "ownerpass12",
            "organization_slug": "join-flow-org",
        },
    )
    assert login_owner.status_code == 200
    pending = client.get("/api/v1/organization/join-requests?status=pending").json()
    assert len(pending) == 1
    rid = pending[0]["id"]
    approve = client.post(
        f"/api/v1/organization/join-requests/{rid}/approve-create-doctor",
        json={
            "first_name": "Join",
            "last_name": "Er",
            "email": "joiner@joinflow.example",
            "employment_percentage": 100,
            "shift_group_ids": [],
        },
    )
    assert approve.status_code == 200
    client.post("/api/v1/auth/logout")
    login_joiner = client.post(
        "/api/v1/auth/login",
        json={
            "email": "joiner@joinflow.example",
            "password": "joinerpass12",
            "organization_slug": "join-flow-org",
        },
    )
    assert login_joiner.status_code == 200
    assert login_joiner.json()["role"] == "doctor"
    assert login_joiner.json()["capabilities"]["doctor_portal"] is True


def test_auth_and_doctor_crud(client: TestClient):
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    response = client.post(
        "/api/v1/doctors",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "employment_percentage": 80},
    )
    assert response.status_code == 200
    assert response.json()["employment_percentage"] == 80
    assert client.get("/api/v1/doctors").json()[0]["email"] == "ada@example.com"


def test_roster_validation_no_go_conflict(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"first_name": "Max", "last_name": "Planck", "email": "max@example.com", "employment_percentage": 100},
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
        json={"doctor_id": doctor_id, "cell_date": request_date, "status": "frei"},
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
        json={"first_name": "Matrix", "last_name": "Doctor", "email": "matrix@example.com", "employment_percentage": 100},
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
        json={"first_name": "Bulk", "last_name": "Doctor", "email": "bulk@example.com", "employment_percentage": 80},
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 8}).json()["id"]

    response = client.put(
        f"/api/v1/matrix/{period_id}/cells/bulk",
        json={
            "cells": [
                {"doctor_id": doctor_id, "cell_date": "2026-08-01", "status": "frei"},
                {
                    "doctor_id": doctor_id,
                    "cell_date": "2026-08-02",
                    "status": "lehre",
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
    assert matrix["cells"][0]["status"] == "lehre"


def test_roster_matrix_assignment_validation_and_csv(client: TestClient):
    login(client)
    doctor_id = client.post(
        "/api/v1/doctors",
        json={"first_name": "Roster", "last_name": "Doctor", "email": "roster@example.com", "employment_percentage": 100},
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
    assert "Roster Doctor" in csv_response.text
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
        json={"first_name": "Reset", "last_name": "Doctor", "email": "reset@example.com", "employment_percentage": 100},
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
        json={"first_name": "Variant", "last_name": "Delete", "email": "variant-delete@example.com", "employment_percentage": 100},
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
        json={"first_name": "Delete", "last_name": "Doctor", "email": "delete@example.com", "employment_percentage": 100},
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
        json={"first_name": "Template", "last_name": "Delete", "email": "template-delete@example.com", "employment_percentage": 100},
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
        json={"first_name": "Purge", "last_name": "Doctor", "email": "purge@example.com", "employment_percentage": 80},
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


def test_shift_group_filters_matrix_and_assignment_eligibility(client: TestClient):
    login(client)
    doc_in = client.post(
        "/api/v1/doctors",
        json={"first_name": "In", "last_name": "Group", "email": "ingroup@example.com", "employment_percentage": 100},
    ).json()
    doc_out = client.post(
        "/api/v1/doctors",
        json={"first_name": "Out", "last_name": "Group", "email": "outgroup@example.com", "employment_percentage": 100},
    ).json()
    template = client.post(
        "/api/v1/shift-templates",
        json={"code": "SGT", "name_de": "Sg Test", "name_en": "Sg Test", "category": "other"},
    ).json()
    client.post(
        f"/api/v1/shift-templates/{template['id']}/variants",
        json={
            "label": "Slot",
            "start_day_class": "any",
            "starts_at": "08:00:00",
            "ends_at": "16:00:00",
            "end_day_offset": 0,
            "required_count": 1,
        },
    )
    group = client.post(
        "/api/v1/shift-groups",
        json={"code": "SG", "name_de": "Gruppe", "name_en": "Group", "display_order": 0},
    ).json()
    gid = group["id"]
    client.put(f"/api/v1/shift-groups/{gid}/doctors", json={"doctor_ids": [doc_in["id"]]})
    client.put(f"/api/v1/shift-groups/{gid}/shift-templates", json={"shift_template_ids": [template["id"]]})
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3}).json()["id"]
    full = client.get(f"/api/v1/matrix/{period_id}").json()
    assert len(full["doctors"]) == 2
    assert len(full["shift_templates"]) == 1
    assert len(full["template_slot_days"]) > 0
    filtered = client.get(f"/api/v1/matrix/{period_id}?shift_group_id={gid}").json()
    assert len(filtered["doctors"]) == 1
    assert filtered["doctors"][0]["id"] == doc_in["id"]
    assert len(filtered["shift_templates"]) == 1
    assert filtered["shift_templates"][0]["id"] == template["id"]
    assert len(filtered["template_slot_days"]) > 0
    assert filtered["shift_intents"] == []
    roster = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(s for s in roster["slots"] if s["shift_template_id"] == template["id"])
    bad = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doc_out["id"]})
    assert bad.status_code == 400
    good = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doc_in["id"]})
    assert good.status_code == 200
    intent_put = client.put(
        f"/api/v1/matrix/{period_id}/shift-intents/bulk",
        json={
            "intents": [
                {
                    "doctor_id": doc_in["id"],
                    "cell_date": slot["slot_date"],
                    "shift_group_id": gid,
                    "shift_template_id": template["id"],
                    "kind": "no_go",
                }
            ]
        },
    )
    assert intent_put.status_code == 200
    warnings_conflict = client.get(f"/api/v1/validation/{period_id}").json()
    assert any(warning["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT" for warning in warnings_conflict)
    client.put("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    denied = client.put("/api/v1/roster-matrix/assignments", json={"roster_slot_id": slot["id"], "doctor_id": doc_in["id"]})
    assert denied.status_code == 400
    override = client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "doctor_id": doc_in["id"], "manual_override": True},
    )
    assert override.status_code == 200
    warnings_after = client.get(f"/api/v1/validation/{period_id}").json()
    assert all(warning["code"] != "ROSTER_TEMPLATE_NO_GO_CONFLICT" for warning in warnings_after)


def test_publish_planning_period(client: TestClient):
    login(client)
    pid = client.post("/api/v1/planning-periods", json={"year": 2028, "month": 1}).json()["id"]
    pub = client.post(f"/api/v1/planning-periods/{pid}/publish")
    assert pub.status_code == 200
    body = pub.json()
    assert body["status"] == "published"
    assert body.get("published_at") is not None

    unpub = client.post(f"/api/v1/planning-periods/{pid}/unpublish")
    assert unpub.status_code == 200
    body2 = unpub.json()
    assert body2["status"] == "draft"
    assert body2.get("published_at") is None


def test_doctor_shift_templates_forbidden(doctor_client: TestClient):
    login_doctor(doctor_client)
    assert doctor_client.get("/api/v1/shift-templates").status_code == 403


@pytest.fixture()
def planner_client():
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
        db.add(
            User(
                email="admin@example.com",
                hashed_password=hash_password("secret"),
                role="admin",
                locale="de",
                organization_id=1,
            )
        )
        planner_user = User(
            email="planner@example.com",
            hashed_password=hash_password("plannersecret"),
            role=ROLE_PLANNER,
            locale="de",
            organization_id=1,
        )
        db.add(planner_user)
        db.flush()
        sg = ShiftGroup(organization_id=1, code="sg1", name_de="SG", name_en="SG", display_order=0)
        db.add(sg)
        db.flush()
        db.add(UserShiftGroup(user_id=planner_user.id, shift_group_id=sg.id))
        doctor = Doctor(
            organization_id=1,
            first_name="In",
            last_name="Group",
            email="ingroup@example.com",
            employment_percentage=100,
        )
        db.add(doctor)
        db.flush()
        db.add(DoctorShiftGroup(doctor_id=doctor.id, shift_group_id=sg.id))
        other = Doctor(
            organization_id=1,
            first_name="Out",
            last_name="Group",
            email="outgroup@example.com",
            employment_percentage=100,
        )
        db.add(other)
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


def login_planner(cl: TestClient) -> None:
    response = cl.post(
        "/api/v1/auth/login",
        json={
            "email": "planner@example.com",
            "password": "plannersecret",
            "organization_slug": "default",
        },
    )
    assert response.status_code == 200


def test_planner_cannot_post_shift_template(planner_client: TestClient):
    login_planner(planner_client)
    response = planner_client.post(
        "/api/v1/shift-templates",
        json={"code": "X", "name_de": "X", "name_en": "X", "category": "other"},
    )
    assert response.status_code == 403


def test_planner_cannot_post_planning_period(planner_client: TestClient):
    login_planner(planner_client)
    response = planner_client.post("/api/v1/planning-periods", json={"year": 2050, "month": 1})
    assert response.status_code == 403


def test_planner_doctors_list_scoped(planner_client: TestClient):
    login_planner(planner_client)
    doctors = planner_client.get("/api/v1/doctors").json()
    assert len(doctors) == 1
    assert doctors[0]["email"] == "ingroup@example.com"


def test_planner_matrix_requires_shift_group(planner_client: TestClient):
    login(planner_client)
    pid = planner_client.post("/api/v1/planning-periods", json={"year": 2040, "month": 1}).json()["id"]
    login_planner(planner_client)
    assert planner_client.get(f"/api/v1/matrix/{pid}").status_code == 403
    assert planner_client.get(f"/api/v1/matrix/{pid}?shift_group_id=1").status_code == 200


def test_doctor_matrix_requires_shift_group(doctor_client: TestClient):
    login(doctor_client)
    pid = doctor_client.post("/api/v1/planning-periods", json={"year": 2030, "month": 1}).json()["id"]
    login_doctor(doctor_client)
    assert doctor_client.get(f"/api/v1/matrix/{pid}").status_code == 400
    matrix = doctor_client.get(f"/api/v1/matrix/{pid}?shift_group_id=1")
    assert matrix.status_code == 200
    body = matrix.json()
    assert len(body["doctors"]) == 1
    assert body["doctors"][0]["id"] == 1


def test_doctor_roster_requires_publish(doctor_client: TestClient):
    login(doctor_client)
    pid = doctor_client.post("/api/v1/planning-periods", json={"year": 2031, "month": 1}).json()["id"]
    login_doctor(doctor_client)
    assert doctor_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 403
    login(doctor_client)
    assert doctor_client.post(f"/api/v1/planning-periods/{pid}/publish").status_code == 200
    login_doctor(doctor_client)
    assert doctor_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 200
    login(doctor_client)
    assert doctor_client.post(f"/api/v1/planning-periods/{pid}/unpublish").status_code == 200
    login_doctor(doctor_client)
    assert doctor_client.get(f"/api/v1/roster-matrix/{pid}?shift_group_id=1").status_code == 403
