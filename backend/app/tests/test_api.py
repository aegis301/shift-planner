from datetime import date, time

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
    shift_type_id = client.post(
        "/api/v1/shift-types",
        json={
            "code": "N",
            "name_de": "Nachtdienst",
            "name_en": "Night shift",
            "starts_at": time(20, 0).isoformat(),
            "ends_at": time(8, 0).isoformat(),
            "category": "night",
        },
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 5}).json()["id"]
    request_date = date(2026, 5, 3).isoformat()
    client.post(
        "/api/v1/requests",
        json={
            "doctor_id": doctor_id,
            "planning_period_id": period_id,
            "request_date": request_date,
            "request_type": "no_go",
        },
    )
    client.post(
        "/api/v1/roster",
        json={
            "doctor_id": doctor_id,
            "planning_period_id": period_id,
            "shift_type_id": shift_type_id,
            "assignment_date": request_date,
        },
    )
    warnings = client.get(f"/api/v1/validation/{period_id}").json()
    assert warnings[0]["code"] == "NO_GO_CONFLICT"


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
    shift_type_id = client.post(
        "/api/v1/shift-types",
        json={
            "code": "T",
            "name_de": "Tagdienst",
            "name_en": "Day shift",
            "starts_at": time(8, 0).isoformat(),
            "ends_at": time(16, 0).isoformat(),
            "category": "day",
        },
    ).json()["id"]
    period_id = client.post("/api/v1/planning-periods", json={"year": 2026, "month": 7}).json()["id"]

    roster_matrix = client.get(f"/api/v1/roster-matrix/{period_id}").json()
    assert roster_matrix["shift_types"][0]["id"] == shift_type_id
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
    assert "Dr. Roster" in csv_response.text
    assert "final geplant" not in csv_response.text

    clear_response = client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": slot["id"]})
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted"] is True
