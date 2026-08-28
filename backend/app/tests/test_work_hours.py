from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Account, Organization, TeamMember, User
from app.models.base import Base
from app.schemas import (
    EmploymentPeriodWrite,
    TimeAccountOpeningUpsert,
    TimeEntryCreate,
    WorkerGroupCreate,
)
from app.services.employment_periods import replace_employment_periods
from app.services.time_entries import create_time_entry, upsert_opening_balance
from app.services.timesheets import fill_regular_week, get_timesheet, month_bounds
from app.services.worker_groups import create_worker_group


@pytest.fixture()
def hours_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = session_local()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_timesheet_expected_hours_and_opening(hours_db) -> None:
    member = TeamMember(
        organization_id=1,
        first_name="Ada",
        last_name="Oncall",
        email="ada@example.com",
        employment_percentage=100,
    )
    hours_db.add(member)
    hours_db.commit()
    group = create_worker_group(
        hours_db,
        WorkerGroupCreate(
            name="Doctors",
            weekly_hours_at_100=40,
            vacation_days_at_100=30,
            regular_week_pattern=[],
            category_rules=[],
            status_mappings=[],
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    replace_employment_periods(
        hours_db,
        team_member_id=member.id,
        organization_id=1,
        periods=[
            EmploymentPeriodWrite(
                worker_group_id=group.id,
                employment_percentage=50,
                start_date=date(2026, 8, 1),
            )
        ],
        actor="test",
        source="test",
    )
    upsert_opening_balance(
        hours_db,
        TimeAccountOpeningUpsert(
            as_of_date=date(2026, 7, 31),
            overtime_minutes=120,
            vacation_days_remaining=10,
            sick_days_used_ytd=0,
        ),
        team_member_id=member.id,
        organization_id=1,
        actor="test",
        source="test",
    )
    create_time_entry(
        hours_db,
        TimeEntryCreate(
            entry_date=date(2026, 8, 3),
            kind="work",
            started_at=datetime(2026, 8, 3, 8, 0),
            ended_at=datetime(2026, 8, 3, 12, 0),
            counts_toward_contract=True,
        ),
        team_member_id=member.id,
        organization_id=1,
        actor="test",
        source="test",
    )
    create_time_entry(
        hours_db,
        TimeEntryCreate(
            entry_date=date(2026, 8, 4),
            kind="absence",
            all_day=True,
            planning_day_status_code="urlaub",
        ),
        team_member_id=member.id,
        organization_id=1,
        actor="test",
        source="test",
    )
    start, end = month_bounds(2026, 8)
    sheet = get_timesheet(
        hours_db, team_member_id=member.id, organization_id=1, from_date=start, to_date=end
    )
    monday = next(day for day in sheet.days if day.date == date(2026, 8, 3))
    assert monday.expected_minutes == 240
    assert monday.worked_contract_minutes == 240
    vacation = next(day for day in sheet.days if day.date == date(2026, 8, 4))
    assert vacation.vacation_days == 1
    assert sheet.vacation_days_remaining == 9
    assert monday.delta_minutes == 0
    assert sheet.overtime_minutes < 120


def test_fill_regular_week_skips_occupied_days(hours_db) -> None:
    member = TeamMember(
        organization_id=1,
        first_name="Bo",
        last_name="Nurse",
        email="bo@example.com",
        employment_percentage=100,
    )
    hours_db.add(member)
    hours_db.commit()
    group = create_worker_group(
        hours_db,
        WorkerGroupCreate(
            name="Nurses",
            weekly_hours_at_100=40,
            vacation_days_at_100=28,
            regular_week_pattern=[
                {"weekday": "mon", "starts_at": time(8, 0), "ends_at": time(16, 0)},
            ],
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    replace_employment_periods(
        hours_db,
        team_member_id=member.id,
        organization_id=1,
        periods=[
            EmploymentPeriodWrite(worker_group_id=group.id, employment_percentage=100, start_date=date(2026, 8, 1))
        ],
        actor="test",
        source="test",
    )
    created = fill_regular_week(
        hours_db,
        team_member_id=member.id,
        organization_id=1,
        from_date=date(2026, 8, 3),
        to_date=date(2026, 8, 3),
        actor="test",
        source="test",
    )
    assert created == 1
    again = fill_regular_week(
        hours_db,
        team_member_id=member.id,
        organization_id=1,
        from_date=date(2026, 8, 3),
        to_date=date(2026, 8, 3),
        actor="test",
        source="test",
    )
    assert again == 0


def test_hours_api_admin_roundtrip() -> None:
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
        acc = Account(email="admin@example.com", hashed_password=hash_password("secret"))
        db.add(acc)
        db.flush()
        db.add(User(account_id=acc.id, organization_id=1, role="admin"))
        db.add(
            TeamMember(
                id=1,
                organization_id=1,
                first_name="Ada",
                last_name="Oncall",
                email="ada@example.com",
                employment_percentage=100,
            )
        )
        db.commit()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret"})
        assert login.status_code == 200
        created = client.post("/api/v1/worker-groups", json={"name": "ICU", "weekly_hours_at_100": 38.5})
        assert created.status_code == 201, created.text
        group_id = created.json()["id"]
        periods = client.put(
            "/api/v1/hours/members/1/employment-periods",
            json={"periods": [{"worker_group_id": group_id, "employment_percentage": 100, "start_date": "2026-08-01"}]},
        )
        assert periods.status_code == 200, periods.text
        opening = client.put(
            "/api/v1/hours/members/1/opening",
            json={"as_of_date": "2026-07-31", "overtime_minutes": 60, "vacation_days_remaining": 12},
        )
        assert opening.status_code == 200
        entry = client.post(
            "/api/v1/hours/members/1/entries",
            json={
                "entry_date": "2026-08-03",
                "kind": "work",
                "started_at": "2026-08-03T08:00:00",
                "ended_at": "2026-08-03T16:00:00",
            },
        )
        assert entry.status_code == 201, entry.text
        sheet = client.get("/api/v1/hours/members/1/timesheet?year=2026&month=8")
        assert sheet.status_code == 200, sheet.text
        body = sheet.json()
        assert body["worked_contract_minutes"] == 480
        csv_body = client.get("/api/v1/hours/members/1/timesheet.csv?year=2026&month=8")
        assert csv_body.status_code == 200
        assert "worked_contract_minutes" in csv_body.text
        summaries = client.get("/api/v1/hours/summaries?year=2026&month=8")
        assert summaries.status_code == 200
        assert summaries.json()[0]["team_member_id"] == 1
    app.dependency_overrides.clear()
