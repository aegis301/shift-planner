from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import (
    Account,
    ContractGroup,
    EmploymentPeriod,
    Organization,
    PlanningPeriod,
    PlanningPeriodShiftGroupMember,
    ShiftGroup,
    TeamMember,
    TimeAccountOpening,
    TimeEntry,
    User,
    UserShiftGroup,
)
from app.models.base import Base
from app.schemas import FairnessDimension, FairnessPolicyUpdate
from app.services.authz import ROLE_PLANNER
from app.services.fairness import build_fairness_accounts, update_fairness_policy

FAIRNESS_BUDGET_SECONDS = 2.0


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def _saturdays(year: int, month: int) -> list[date]:
    days: list[date] = []
    for day in range(1, monthrange(year, month)[1] + 1):
        item = date(year, month, day)
        if item.weekday() == 5:
            days.append(item)
    return days


def _add_member(db: Session, *, email: str, first_name: str) -> TeamMember:
    member = TeamMember(
        organization_id=1,
        first_name=first_name,
        last_name="Fair",
        email=email,
        is_active=True,
    )
    db.add(member)
    db.flush()
    return member


def _add_employment(
    db: Session,
    member: TeamMember,
    group: ContractGroup,
    *,
    percentage: int,
    start: date,
    end: date | None = None,
) -> EmploymentPeriod:
    row = EmploymentPeriod(
        team_member_id=member.id,
        contract_group_id=group.id,
        employment_percentage=percentage,
        start_date=start,
        end_date=end,
    )
    db.add(row)
    db.flush()
    return row


def _add_roster_entry(
    db: Session,
    member: TeamMember,
    entry_date: date,
    *,
    hour: int = 8,
    overnight: bool = False,
    statutory_minutes: int = 0,
    category: str = "bereitschaftsdienst",
) -> TimeEntry:
    started = datetime(entry_date.year, entry_date.month, entry_date.day, hour, 0, tzinfo=UTC)
    ended = started + timedelta(hours=16)
    if overnight:
        ended = datetime(entry_date.year, entry_date.month, entry_date.day, 8, 0, tzinfo=UTC) + timedelta(days=1)
    row = TimeEntry(
        organization_id=1,
        team_member_id=member.id,
        entry_date=entry_date,
        kind="work",
        source="roster",
        shift_template_category=category,
        started_at=started,
        ended_at=ended,
        statutory_minutes=statutory_minutes,
    )
    db.add(row)
    return row


def _seed_org(db: Session) -> tuple[ShiftGroup, ContractGroup]:
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.flush()
    group = ShiftGroup(organization_id=1, code="sg1", name="SG1")
    db.add(group)
    db.flush()
    contract = ContractGroup(
        organization_id=1,
        name="Standard",
        weekly_hours_at_100=Decimal("40"),
        vacation_days_at_100=Decimal("30"),
        regular_week_pattern=[],
        category_rules=[],
        status_mappings=[],
    )
    db.add(contract)
    db.flush()
    return group, contract


def _ensure_period(db: Session, year: int, month: int) -> PlanningPeriod:
    period = PlanningPeriod(organization_id=1, year=year, month=month, status="draft")
    db.add(period)
    db.flush()
    return period


def _on_roster(db: Session, period: PlanningPeriod, shift_group: ShiftGroup, member: TeamMember) -> None:
    db.add(
        PlanningPeriodShiftGroupMember(
            planning_period_id=period.id,
            shift_group_id=shift_group.id,
            team_member_id=member.id,
        )
    )


def _dimension(accounts, member_id: int, dimension_id: str):
    member = next(row for row in accounts.members if row.team_member_id == member_id)
    return next(item for item in member.dimensions if item.dimension_id == dimension_id)


@pytest.fixture()
def fairness_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = testing_session()
    try:
        yield db, engine
    finally:
        db.close()
        engine.dispose()


def test_part_time_double_weekend_share_ranks_over_served(fairness_db):
    db, _engine = fairness_db
    shift_group, contract = _seed_org(db)
    part_time = _add_member(db, email="half@example.com", first_name="Half")
    full_time = _add_member(db, email="full@example.com", first_name="Full")
    _add_employment(db, part_time, contract, percentage=50, start=date(2025, 1, 1))
    _add_employment(db, full_time, contract, percentage=100, start=date(2025, 1, 1))
    current = None
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        period = _ensure_period(db, year, month)
        _on_roster(db, period, shift_group, part_time)
        _on_roster(db, period, shift_group, full_time)
        saturdays = _saturdays(year, month)
        if offset < 11:
            _add_roster_entry(db, part_time, saturdays[0])
            _add_roster_entry(db, part_time, saturdays[1])
            _add_roster_entry(db, full_time, saturdays[2])
        else:
            _add_roster_entry(db, full_time, saturdays[0])
            _add_roster_entry(db, full_time, saturdays[1])
            current = period
    db.commit()
    assert current is not None
    accounts = build_fairness_accounts(
        db, current.id, organization_id=1, shift_group_id=shift_group.id
    )
    weekend_half = _dimension(accounts, part_time.id, "weekend_holiday")
    weekend_full = _dimension(accounts, full_time.id, "weekend_holiday")
    assert weekend_half.actual == pytest.approx(2 * weekend_half.expected, rel=0.15)
    assert weekend_half.deviation_normalized > weekend_full.deviation_normalized
    assert accounts.members[0].team_member_id == part_time.id
    current_month_actual_half = 0.0
    current_month_actual_full = 2.0
    assert weekend_half.actual != current_month_actual_half
    assert weekend_full.actual != current_month_actual_full or weekend_half.actual > weekend_full.actual


def test_mid_window_joiner_measured_against_three_months(fairness_db):
    db, _engine = fairness_db
    shift_group, contract = _seed_org(db)
    veteran = _add_member(db, email="vet@example.com", first_name="Vet")
    joiner = _add_member(db, email="new@example.com", first_name="New")
    _add_employment(db, veteran, contract, percentage=100, start=date(2025, 1, 1))
    _add_employment(db, joiner, contract, percentage=100, start=date(2026, 10, 1))
    current = None
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        period = _ensure_period(db, year, month)
        _on_roster(db, period, shift_group, veteran)
        saturdays = _saturdays(year, month)
        _add_roster_entry(db, veteran, saturdays[0])
        if offset >= 9:
            _on_roster(db, period, shift_group, joiner)
            _add_roster_entry(db, joiner, saturdays[1])
        current = period
    db.commit()
    assert current is not None
    accounts = build_fairness_accounts(
        db, current.id, organization_id=1, shift_group_id=shift_group.id
    )
    joiner_duties = _dimension(accounts, joiner.id, "duties")
    veteran_duties = _dimension(accounts, veteran.id, "duties")
    assert joiner_duties.actual == 3
    assert joiner_duties.expected == pytest.approx(3.0)
    assert veteran_duties.actual == 12
    assert veteran_duties.expected == pytest.approx(12.0)
    assert joiner_duties.expected == pytest.approx(veteran_duties.expected * 3 / 12)


def test_opening_balance_shifts_account_exactly(fairness_db):
    db, _engine = fairness_db
    shift_group, contract = _seed_org(db)
    member = _add_member(db, email="open@example.com", first_name="Open")
    other = _add_member(db, email="peer@example.com", first_name="Peer")
    _add_employment(db, member, contract, percentage=100, start=date(2025, 1, 1))
    _add_employment(db, other, contract, percentage=100, start=date(2025, 1, 1))
    current = None
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        period = _ensure_period(db, year, month)
        _on_roster(db, period, shift_group, member)
        _on_roster(db, period, shift_group, other)
        saturdays = _saturdays(year, month)
        _add_roster_entry(db, member, saturdays[0])
        _add_roster_entry(db, other, saturdays[1])
        current = period
    db.add(
        TimeAccountOpening(
            team_member_id=member.id,
            as_of_date=date(2025, 1, 1),
            overtime_minutes=90,
            fairness_balances={"weekend_holiday": 5, "duties": 2},
        )
    )
    db.commit()
    assert current is not None
    accounts = build_fairness_accounts(
        db, current.id, organization_id=1, shift_group_id=shift_group.id
    )
    weekend = _dimension(accounts, member.id, "weekend_holiday")
    peer_weekend = _dimension(accounts, other.id, "weekend_holiday")
    duties = _dimension(accounts, member.id, "duties")
    hours = _dimension(accounts, member.id, "statutory_hours")
    assert weekend.actual == peer_weekend.actual + 5
    assert duties.actual == 12 + 2
    assert hours.actual == 90


def test_adding_dimension_requires_no_schema_change(fairness_db):
    db, _engine = fairness_db
    shift_group, contract = _seed_org(db)
    member = _add_member(db, email="dim@example.com", first_name="Dim")
    _add_employment(db, member, contract, percentage=100, start=date(2025, 1, 1))
    year, month = 2026, 12
    period = _ensure_period(db, year, month)
    _on_roster(db, period, shift_group, member)
    _add_roster_entry(db, member, date(2026, 12, 1), category="spaetdienst")
    db.commit()
    org = db.get(Organization, 1)
    assert org is not None
    update_fairness_policy(
        db,
        org,
        FairnessPolicyUpdate(
            dimensions=[
                FairnessDimension(id="duties", metric="duty_count"),
                FairnessDimension(id="late", metric="duty_count", category="spaetdienst"),
            ]
        ),
        actor="test",
        source="test",
    )
    accounts = build_fairness_accounts(
        db, period.id, organization_id=1, shift_group_id=shift_group.id
    )
    assert [item.id for item in accounts.dimensions] == ["duties", "late"]
    late = _dimension(accounts, member.id, "late")
    assert late.actual == 1


def test_expectation_is_sum_of_monthly_shares_not_window_average(fairness_db):
    db, _engine = fairness_db
    shift_group, contract = _seed_org(db)
    changing = _add_member(db, email="chg@example.com", first_name="Chg")
    stable = _add_member(db, email="st@example.com", first_name="Stab")
    _add_employment(db, changing, contract, percentage=100, start=date(2026, 1, 1), end=date(2026, 6, 30))
    _add_employment(db, changing, contract, percentage=50, start=date(2026, 7, 1))
    _add_employment(db, stable, contract, percentage=100, start=date(2025, 1, 1))
    current = None
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        period = _ensure_period(db, year, month)
        _on_roster(db, period, shift_group, changing)
        _on_roster(db, period, shift_group, stable)
        saturdays = _saturdays(year, month)
        _add_roster_entry(db, changing, saturdays[0])
        _add_roster_entry(db, stable, saturdays[1])
        current = period
    db.commit()
    assert current is not None
    accounts = build_fairness_accounts(
        db, current.id, organization_id=1, shift_group_id=shift_group.id
    )
    expected = _dimension(accounts, changing.id, "duties").expected
    monthly = 0.0
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        percent = 100 if month <= 6 else 50
        weight_chg = (percent / 100) * 40
        weight_st = 40.0
        monthly += 2.0 * weight_chg / (weight_chg + weight_st)
    assert expected == pytest.approx(monthly)
    window_average_weight = ((100 + 50) / 2 / 100) * 40
    wrong = 24.0 * window_average_weight / (window_average_weight + 40.0)
    assert expected != pytest.approx(wrong)


def test_thirty_members_twelve_months_within_budget(fairness_db):
    db, engine = fairness_db
    shift_group, contract = _seed_org(db)
    members = [
        _add_member(db, email=f"m{index}@example.com", first_name=f"M{index}") for index in range(30)
    ]
    for member in members:
        _add_employment(db, member, contract, percentage=100, start=date(2025, 1, 1))
    current = None
    for offset in range(12):
        year, month = _add_months(2026, 1, offset)
        period = _ensure_period(db, year, month)
        saturdays = _saturdays(year, month)
        for index, member in enumerate(members):
            _on_roster(db, period, shift_group, member)
            _add_roster_entry(db, member, saturdays[index % len(saturdays)], statutory_minutes=60)
        current = period
    db.commit()
    assert current is not None
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    started = perf_counter()
    accounts = build_fairness_accounts(
        db, current.id, organization_id=1, shift_group_id=shift_group.id
    )
    elapsed = perf_counter() - started
    event.remove(engine, "before_cursor_execute", before_cursor_execute)
    assert elapsed < FAIRNESS_BUDGET_SECONDS
    assert len(accounts.members) == 30
    slot_loads = [
        statement
        for statement in statements
        if "roster_slots" in statement.lower() and "roster_slot_assignments" not in statement.lower()
    ]
    assignment_loads = [
        statement for statement in statements if "roster_slot_assignments" in statement.lower()
    ]
    assert len(slot_loads) == 1
    assert len(assignment_loads) == 1
    history_entry_loads = [
        statement
        for statement in statements
        if "time_entries" in statement.lower()
    ]
    assert history_entry_loads


def _seed_membership(db, email: str, password: str, org_id: int, role: str) -> User:
    acc = Account(email=email.lower(), hashed_password=hash_password(password))
    db.add(acc)
    db.flush()
    user = User(account_id=acc.id, organization_id=org_id, role=role, locale="de")
    db.add(user)
    return user


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
        db.flush()
        _seed_membership(db, "admin@example.com", "secret", 1, "admin")
        planner = _seed_membership(db, "planner@example.com", "plannersecret", 1, ROLE_PLANNER)
        db.flush()
        group = ShiftGroup(organization_id=1, code="sg1", name="SG1", display_order=0)
        other = ShiftGroup(organization_id=1, code="sg2", name="SG2", display_order=1)
        db.add(group)
        db.add(other)
        db.flush()
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=group.id))
        period = PlanningPeriod(organization_id=1, year=2026, month=12, status="draft")
        db.add(period)
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, testing_session
    app.dependency_overrides.clear()


def test_planner_scope_enforced_on_fairness(client):
    test_client, testing_session = client
    with testing_session() as db:
        period = db.scalar(select(PlanningPeriod))
        assert period is not None
        period_id = period.id
    login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "planner@example.com", "password": "plannersecret", "organization_slug": "default"},
    )
    assert login.status_code == 200, login.text
    missing = test_client.get(f"/api/v1/fairness/{period_id}")
    assert missing.status_code == 403
    other = test_client.get(f"/api/v1/fairness/{period_id}?shift_group_id=2")
    assert other.status_code == 403
    allowed = test_client.get(f"/api/v1/fairness/{period_id}?shift_group_id=1")
    assert allowed.status_code == 200, allowed.text
    policy = test_client.get("/api/v1/organization/fairness-policy")
    assert policy.status_code == 200
    denied_patch = test_client.patch("/api/v1/organization/fairness-policy", json={"window_months": 6})
    assert denied_patch.status_code == 403
    admin_login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    )
    assert admin_login.status_code == 200
    patched = test_client.patch("/api/v1/organization/fairness-policy", json={"window_months": 6})
    assert patched.status_code == 200, patched.text
    assert patched.json()["window_months"] == 6
