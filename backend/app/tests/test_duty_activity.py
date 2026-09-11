from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
    User,
    WorkTimeRuleSet,
)
from app.models.base import Base
from app.schemas import DutyActivityCreate, DutyActivityReason, WorkTimeRuleDutyUtilizationBands
from app.schemas.domain import WorkTimeRuleMinRestPeriod
from app.services.duty_activity import record_duty_activity
from app.services.duty_utilization import classify_utilization, period_utilization, slot_utilization
from app.services.rules import build_plan_state
from app.services.rules.statutory import MinRestPeriodRule, _daily_statutory_minutes
from app.services.work_time_valuation import statutory_work_minutes


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
        portal = _seed_membership(db, "doc@example.com", "docsecret", 1, "team_member")
        db.flush()
        db.add(
            TeamMember(
                organization_id=1,
                first_name="Seeded",
                last_name="Member",
                email="docperson@example.com",
                user_id=portal.id,
            )
        )
        db.add(ShiftGroup(organization_id=1, code="default_sg", name="Default SG", display_order=0))
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


@pytest.fixture()
def duty_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = testing_session()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def login_admin(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    ).status_code == 200


def login_team_member(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "doc@example.com", "password": "docsecret", "organization_slug": "default"},
    ).status_code == 200


def set_shift_group_membership(client: TestClient, *, team_member_id: int) -> None:
    response = client.put(
        "/api/v1/shift-groups/1/memberships",
        json={"memberships": [{"team_member_id": team_member_id, "start_date": "2026-01-01", "end_date": None}]},
    )
    assert response.status_code == 200


def create_member(client: TestClient, email: str) -> int:
    response = client.post(
        "/api/v1/team-members",
        json={"first_name": "Pat", "last_name": email.split("@")[0], "email": email, "employment_percentage": 100},
    )
    assert response.status_code == 200
    member_id = response.json()["id"]
    set_shift_group_membership(client, team_member_id=member_id)
    return member_id


def _add_member(db: Session, *, email: str) -> TeamMember:
    member = TeamMember(organization_id=1, first_name="A", last_name="B", email=email, is_active=True)
    db.add(member)
    db.flush()
    return member


def _add_ruf_group(db: Session) -> ContractGroup:
    group = ContractGroup(
        organization_id=1,
        name="Ruf",
        weekly_hours_at_100=Decimal("40"),
        vacation_days_at_100=Decimal("30"),
        regular_week_pattern=[],
        category_rules=[
            {
                "category": "rufdienst",
                "counts_toward_contract": False,
                "credit_mode": "none",
                "holiday_credit_bonus": "0",
                "statutory_factor": "1",
                "call_outs_count_as_work": True,
            },
            {
                "category": "bereitschaftsdienst",
                "counts_toward_contract": True,
                "credit_mode": "factor",
                "credit_factor": "0.6",
                "holiday_credit_bonus": "25",
                "statutory_factor": "1",
                "call_outs_count_as_work": False,
            },
        ],
        status_mappings=[],
    )
    db.add(group)
    db.flush()
    return group


def _employ(db: Session, member: TeamMember, group: ContractGroup) -> None:
    db.add(
        EmploymentPeriod(
            team_member_id=member.id,
            contract_group_id=group.id,
            employment_percentage=100,
            start_date=date(2000, 1, 1),
            end_date=None,
        )
    )


def _add_template(db: Session, *, code: str, category: str) -> tuple[ShiftTemplate, ShiftVariant]:
    template = ShiftTemplate(organization_id=1, code=code, name=code, category=category, constraints=[])
    db.add(template)
    db.flush()
    variant = ShiftVariant(
        shift_template_id=template.id,
        label="duty",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(8, 0),
        required_count=1,
        constraints=[],
    )
    db.add(variant)
    db.flush()
    return template, variant


def _add_period(db: Session, year: int, month: int) -> PlanningPeriod:
    period = PlanningPeriod(organization_id=1, year=year, month=month, status="draft")
    db.add(period)
    db.flush()
    return period


def _add_slot(
    db: Session,
    *,
    period: PlanningPeriod,
    template: ShiftTemplate,
    variant: ShiftVariant,
    slot_date: date,
    starts_at: datetime,
    ends_at: datetime,
    position: int = 1,
) -> RosterSlot:
    slot = RosterSlot(
        planning_period_id=period.id,
        shift_template_id=template.id,
        shift_variant_id=variant.id,
        slot_date=slot_date,
        position=position,
        label=variant.label,
        starts_at=starts_at,
        ends_at=ends_at,
        day_class="weekday",
    )
    db.add(slot)
    db.flush()
    return slot


def _add_assignment(db: Session, slot: RosterSlot, member: TeamMember) -> None:
    db.add(RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id))
    db.flush()


def _activate_bands(db: Session, *, stufe_i: str = "25", on_call: str = "49") -> None:
    db.add(
        WorkTimeRuleSet(
            organization_id=1,
            name="bands",
            version=1,
            is_active=True,
            rules=[
                {
                    "type": "duty_utilization_bands",
                    "severity": "info",
                    "source_note": "TV-Ärzte",
                    "stufe_i_max_percent": stufe_i,
                    "on_call_max_percent": on_call,
                }
            ],
        )
    )
    db.commit()


def _create_category_template(client: TestClient, *, code: str, category: str) -> int:
    template = client.post("/api/v1/shift-templates", json={"code": code, "name": code, "category": category})
    assert template.status_code == 200
    template_id = template.json()["id"]
    assert (
        client.post(
            f"/api/v1/shift-templates/{template_id}/variants",
            json={
                "label": code,
                "start_day_class": "any",
                "starts_at": "08:00:00",
                "ends_at": "08:00:00",
                "end_day_offset": 1,
                "required_count": 1,
            },
        ).status_code
        == 200
    )
    return template_id


def test_call_out_adds_statutory_minutes_and_shortens_rest(duty_db):
    db = duty_db
    member = _add_member(db, email="ruf@example.com")
    group = _add_ruf_group(db)
    _employ(db, member, group)
    period = _add_period(db, 2026, 3)
    ruf_template, ruf_variant = _add_template(db, code="RUF", category="rufdienst")
    day_template, day_variant = _add_template(db, code="DAY", category="other")
    ruf = _add_slot(
        db,
        period=period,
        template=ruf_template,
        variant=ruf_variant,
        slot_date=date(2026, 3, 1),
        starts_at=datetime(2026, 3, 1, 20, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
    )
    follow = _add_slot(
        db,
        period=period,
        template=day_template,
        variant=day_variant,
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 17, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 21, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, ruf, member)
    _add_assignment(db, follow, member)
    db.commit()
    rule = MinRestPeriodRule(
        WorkTimeRuleMinRestPeriod(hours=Decimal("11"), compensation_window_days=2, call_out_handling="interrupt")
    )
    without = rule.evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2)))
    assert [row.code for row in without if row.code == "WORKTIME_MIN_REST"] == []
    row = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=ruf.id,
            kind="call_out",
            started_at=datetime(2026, 3, 2, 6, 0, tzinfo=UTC),
            ended_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
            reason=DutyActivityReason(code="ward", note="station"),
        ),
        organization_id=1,
        team_member_id=member.id,
        actor="test",
        source="test",
    )
    assert row.statutory_minutes == 120
    assert row.counts_toward_contract is True
    assert row.reason == {"code": "ward", "note": "station"}
    state = build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2))
    assert _daily_statutory_minutes(state, member.id, date(2026, 3, 1)) == 120
    rest = [item for item in rule.evaluate(state) if item.code == "WORKTIME_MIN_REST"]
    assert rest
    assert rest[0].details["rest_minutes"] == 9 * 60
    assert rest[0].details["roster_slot_id"] == follow.id


def test_in_duty_activity_reports_band_and_exceeds_flag(duty_db):
    db = duty_db
    member = _add_member(db, email="bd@example.com")
    group = _add_ruf_group(db)
    _employ(db, member, group)
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="BD", category="bereitschaftsdienst")
    _activate_bands(db)
    start = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    slot = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 2),
        starts_at=start,
        ends_at=start + timedelta(hours=24),
    )
    _add_assignment(db, slot, member)
    db.commit()
    quiet = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=slot.id,
            kind="in_duty_activity",
            started_at=start,
            ended_at=start + timedelta(hours=6),
        ),
        organization_id=1,
        team_member_id=member.id,
        actor="test",
        source="test",
    )
    assert quiet.statutory_minutes == 0
    assert quiet.counts_toward_contract is False
    mild = slot_utilization(slot, [quiet], WorkTimeRuleDutyUtilizationBands(stufe_i_max_percent=Decimal("25"), on_call_max_percent=Decimal("49")))
    assert mild.utilization_percent == Decimal("25.00")
    assert mild.band == "stufe_i"
    assert mild.exceeds_on_call_threshold is False
    busy_start = start + timedelta(hours=7)
    busy = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=slot.id,
            kind="in_duty_activity",
            started_at=busy_start,
            ended_at=busy_start + timedelta(minutes=361),
        ),
        organization_id=1,
        team_member_id=member.id,
        actor="test",
        source="test",
    )
    hot = slot_utilization(
        slot,
        [quiet, busy],
        WorkTimeRuleDutyUtilizationBands(stufe_i_max_percent=Decimal("25"), on_call_max_percent=Decimal("49")),
    )
    assert hot.worked_minutes == 6 * 60 + 361
    assert hot.utilization_percent > Decimal("49")
    assert hot.band == "full_work"
    assert hot.exceeds_on_call_threshold is True
    band, exceeds = classify_utilization(Decimal("49.00"), WorkTimeRuleDutyUtilizationBands(stufe_i_max_percent=Decimal("25"), on_call_max_percent=Decimal("49")))
    assert band == "stufe_ii"
    assert exceeds is False


def test_aggregate_includes_coverage_for_thin_data(duty_db):
    db = duty_db
    member = _add_member(db, email="cov@example.com")
    group = _add_ruf_group(db)
    _employ(db, member, group)
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="BD40", category="bereitschaftsdienst")
    _activate_bands(db)
    slots: list[RosterSlot] = []
    start = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    for index in range(40):
        slot = _add_slot(
            db,
            period=period,
            template=template,
            variant=variant,
            slot_date=date(2026, 3, 1),
            starts_at=start,
            ends_at=start + timedelta(hours=24),
            position=index + 1,
        )
        _add_assignment(db, slot, member)
        slots.append(slot)
    db.commit()
    for slot in slots[:3]:
        record_duty_activity(
            db,
            DutyActivityCreate(
                roster_slot_id=slot.id,
                kind="in_duty_activity",
                started_at=start,
                ended_at=start + timedelta(hours=2),
            ),
            organization_id=1,
            team_member_id=member.id,
            actor="test",
            source="test",
        )
    result = period_utilization(db, organization_id=1, planning_period_id=period.id)
    assert result.coverage.recorded_duty_count == 3
    assert result.coverage.duty_count == 40
    assert result.coverage.coverage_ratio == Decimal("0.0750")
    assert result.utilization_ratio == Decimal("0.0833")
    assert result.templates[0].coverage.recorded_duty_count == 3
    assert result.templates[0].coverage.duty_count == 40


def test_episode_requires_assignment_and_rejects_overlap(duty_db):
    db = duty_db
    assigned = _add_member(db, email="assignee@example.com")
    other = _add_member(db, email="other@example.com")
    group = _add_ruf_group(db)
    _employ(db, assigned, group)
    _employ(db, other, group)
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="RUF2", category="rufdienst")
    start = datetime(2026, 3, 4, 20, 0, tzinfo=UTC)
    slot = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 4),
        starts_at=start,
        ends_at=start + timedelta(hours=12),
    )
    _add_assignment(db, slot, assigned)
    db.commit()
    with pytest.raises(ValueError, match="not assigned"):
        record_duty_activity(
            db,
            DutyActivityCreate(
                roster_slot_id=slot.id,
                kind="call_out",
                started_at=start + timedelta(hours=1),
                ended_at=start + timedelta(hours=2),
            ),
            organization_id=1,
            team_member_id=other.id,
            actor="test",
            source="test",
        )
    first = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=slot.id,
            kind="call_out",
            started_at=start + timedelta(hours=1),
            ended_at=start + timedelta(hours=3),
        ),
        organization_id=1,
        team_member_id=assigned.id,
        actor="test",
        source="test",
    )
    assert first.id
    with pytest.raises(ValueError, match="Overlapping"):
        record_duty_activity(
            db,
            DutyActivityCreate(
                roster_slot_id=slot.id,
                kind="call_out",
                started_at=start + timedelta(hours=2),
                ended_at=start + timedelta(hours=4),
            ),
            organization_id=1,
            team_member_id=assigned.id,
            actor="test",
            source="test",
        )
    adjacent = record_duty_activity(
        db,
        DutyActivityCreate(
            roster_slot_id=slot.id,
            kind="call_out",
            started_at=start + timedelta(hours=3),
            ended_at=start + timedelta(hours=4),
        ),
        organization_id=1,
        team_member_id=assigned.id,
        actor="test",
        source="test",
    )
    assert adjacent.duration_minutes == 60
    with pytest.raises(ValueError, match="inside the slot span"):
        record_duty_activity(
            db,
            DutyActivityCreate(
                roster_slot_id=slot.id,
                kind="call_out",
                started_at=start + timedelta(hours=11),
                ended_at=start + timedelta(hours=13),
            ),
            organization_id=1,
            team_member_id=assigned.id,
            actor="test",
            source="test",
        )


def test_in_duty_activity_is_ignored_by_statutory_valuation():
    slot = SimpleNamespace(
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 3, 8, 0, tzinfo=UTC),
    )
    group = SimpleNamespace(
        category_rules=[
            {
                "category": "bereitschaftsdienst",
                "credit_mode": "factor",
                "credit_factor": "0.6",
                "holiday_credit_bonus": "0",
                "statutory_factor": "1",
                "call_outs_count_as_work": False,
            }
        ]
    )
    template = SimpleNamespace(category="bereitschaftsdienst", valuation_override=None)
    episodes = (SimpleNamespace(kind="in_duty_activity", duration_minutes=400),)
    assert statutory_work_minutes(
        slot=slot, contract_group=group, template=template, day_class="weekday", episodes=episodes
    ) == 1440


def test_member_manages_own_episodes_planners_read_aggregates_only(client):
    test_client, _session = client
    login_team_member(test_client)
    own_id = test_client.get("/api/v1/auth/me").json()["team_member_id"]
    login_admin(test_client)
    set_shift_group_membership(test_client, team_member_id=own_id)
    _create_category_template(test_client, code="BD", category="bereitschaftsdienst")
    period = test_client.post("/api/v1/planning-periods", json={"year": 2026, "month": 3})
    assert period.status_code == 200
    period_id = period.json()["id"]
    roster = test_client.get(f"/api/v1/roster-matrix/{period_id}").json()
    slot = next(item for item in roster["slots"] if item["slot_date"] == "2026-03-02")
    assigned = test_client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": slot["id"], "team_member_id": own_id},
    )
    assert assigned.status_code == 200
    test_client.post(
        "/api/v1/work-time-rule-sets",
        json={
            "name": "bands",
            "is_active": True,
            "rules": [
                {
                    "type": "duty_utilization_bands",
                    "severity": "info",
                    "stufe_i_max_percent": "25",
                    "on_call_max_percent": "49",
                }
            ],
        },
    )
    login_team_member(test_client)
    created = test_client.post(
        "/api/v1/duty-activity",
        json={
            "roster_slot_id": slot["id"],
            "kind": "in_duty_activity",
            "started_at": "2026-03-02T08:00:00+00:00",
            "ended_at": "2026-03-02T10:00:00+00:00",
            "reason": {"code": "ward"},
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["kind"] == "in_duty_activity"
    assert created.json()["statutory_minutes"] == 0
    listed = test_client.get("/api/v1/duty-activity")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    denied_util = test_client.get(f"/api/v1/duty-activity/utilization/{period_id}")
    assert denied_util.status_code == 403
    login_admin(test_client)
    individuals = test_client.get("/api/v1/duty-activity")
    assert individuals.status_code == 403
    util = test_client.get(f"/api/v1/duty-activity/utilization/{period_id}")
    assert util.status_code == 200, util.text
    body = util.json()
    assert "coverage" in body
    assert body["coverage"]["recorded_duty_count"] >= 1
    assert body["coverage"]["duty_count"] >= 1
    flagged = next(row for row in body["slots"] if row["roster_slot_id"] == slot["id"])
    assert "exceeds_on_call_threshold" in flagged
    assert flagged["has_activity_record"] is True
