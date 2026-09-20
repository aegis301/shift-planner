from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from time import perf_counter

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Organization,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
    TimeEntry,
    WorkTimeRuleSet,
)
from app.models.base import Base
from app.schemas.domain import (
    RosterSlotAssignmentUpsert,
    WorkTimeRuleDocumentationRequirement,
    WorkTimeRuleMaxConsecutiveWorkDays,
    WorkTimeRuleMaxDailyWorkingTime,
    WorkTimeRuleMaxDutiesPerPeriod,
    WorkTimeRuleMinRestPeriod,
    WorkTimeRuleOptOutWeeklyCap,
    WorkTimeRuleRestAfterLongDuty,
    WorkTimeRuleWeeklyAverageCap,
)
from app.services.constraints import find_blocking_constraint
from app.services.roster_matrix import _preflight_assignment_warnings, upsert_roster_slot_assignment
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.rules.statutory import (
    DocumentationRequirementRule,
    MaxConsecutiveWorkDaysRule,
    MaxDailyWorkingTimeRule,
    MaxDutiesPerPeriodRule,
    MinRestPeriodRule,
    OptOutWeeklyCapRule,
    RestAfterLongDutyRule,
    WeeklyAverageCapRule,
)
from app.services.validation import validate_roster

BENCHMARK_BUDGET_SECONDS = 3.0


@pytest.fixture()
def plan_db():
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
        yield db, engine
    finally:
        db.close()
        engine.dispose()


def _add_member(db: Session, *, email: str, first_name: str = "A") -> TeamMember:
    member = TeamMember(
        organization_id=1,
        first_name=first_name,
        last_name="B",
        email=email,
        is_active=True,
    )
    db.add(member)
    db.flush()
    return member


def _add_period(db: Session, year: int, month: int) -> PlanningPeriod:
    period = PlanningPeriod(organization_id=1, year=year, month=month, status="draft")
    db.add(period)
    db.flush()
    return period


def _add_template(db: Session, *, code: str, category: str = "bereitschaftsdienst") -> tuple[ShiftTemplate, ShiftVariant]:
    template = ShiftTemplate(
        organization_id=1,
        code=code,
        name=code,
        category=category,
        constraints=[],
    )
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


def _add_assignment(db: Session, *, slot: RosterSlot, member: TeamMember) -> RosterSlotAssignment:
    row = RosterSlotAssignment(roster_slot_id=slot.id, team_member_id=member.id)
    db.add(row)
    db.flush()
    return row


def _activate_rules(db: Session, rules: list[dict]) -> WorkTimeRuleSet:
    row = WorkTimeRuleSet(
        organization_id=1,
        name="statutory-test",
        version=1,
        is_active=True,
        rules=rules,
    )
    db.add(row)
    db.commit()
    return row


def _codes(warnings) -> set[str]:
    return {warning.code for warning in warnings}


def test_max_daily_working_time_flags_statutory_minutes_over_base_cap(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="daily@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="D9")
    slot = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 17, 0, tzinfo=UTC),
    )
    _add_assignment(db, slot=slot, member=member)
    db.commit()
    rule = MaxDailyWorkingTimeRule(
        WorkTimeRuleMaxDailyWorkingTime(
            base_hours=Decimal("8"),
            extended_hours=Decimal("10"),
            extension_requires_duty_hours=Decimal("12"),
        )
    )
    state = build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2))
    warnings = rule.evaluate(state)
    assert [row.code for row in warnings] == ["WORKTIME_MAX_DAILY"]
    assert warnings[0].details["statutory_minutes"] == 9 * 60
    assert warnings[0].details["limit_minutes"] == 8 * 60


def test_min_rest_flags_24h_duty_then_next_day_shift_across_month_boundary(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="rest@example.com")
    june = _add_period(db, 2026, 6)
    july = _add_period(db, 2026, 7)
    template, variant = _add_template(db, code="R24")
    first = _add_slot(
        db,
        period=june,
        template=template,
        variant=variant,
        slot_date=date(2026, 6, 30),
        starts_at=datetime(2026, 6, 30, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
    )
    follow = _add_slot(
        db,
        period=july,
        template=template,
        variant=variant,
        slot_date=date(2026, 7, 1),
        starts_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, slot=first, member=member)
    _add_assignment(db, slot=follow, member=member)
    _activate_rules(
        db,
        [
            {
                "type": "min_rest_period",
                "severity": "error",
                "hours": "11",
                "reducible_to_hours": "10",
                "compensation_window_days": 31,
                "call_out_handling": "interrupt",
            }
        ],
    )
    warnings = evaluate_plan_state(
        build_plan_state(db, organization_id=1, start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)),
        db=db,
    )
    rest = [row for row in warnings if row.code == "WORKTIME_MIN_REST"]
    assert rest
    assert rest[0].team_member_id == member.id
    assert rest[0].date == date(2026, 7, 1)
    assert rest[0].details["roster_slot_id"] == follow.id


def test_call_out_during_rufbereitschaft_restarts_rest(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="ruf@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="RUF", category="rufdienst")
    follow_template, follow_variant = _add_template(db, code="DAY", category="other")
    ruf = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 1),
        starts_at=datetime(2026, 3, 1, 20, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
    )
    follow = _add_slot(
        db,
        period=period,
        template=follow_template,
        variant=follow_variant,
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 19, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, slot=ruf, member=member)
    _add_assignment(db, slot=follow, member=member)
    db.commit()
    rule = MinRestPeriodRule(
        WorkTimeRuleMinRestPeriod(
            hours=Decimal("11"),
            reducible_to_hours=None,
            compensation_window_days=2,
            call_out_handling="interrupt",
        )
    )
    without = rule.evaluate(
        build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2))
    )
    assert [row.code for row in without if row.code == "WORKTIME_MIN_REST"] == []
    db.add(
        TimeEntry(
            organization_id=1,
            team_member_id=member.id,
            entry_date=date(2026, 3, 2),
            kind="call_out",
            source="manual",
            all_day=False,
            started_at=datetime(2026, 3, 2, 7, 0, tzinfo=UTC),
            ended_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
            duration_minutes=120,
            statutory_minutes=120,
            credited_minutes=9999,
            roster_slot_id=ruf.id,
        )
    )
    db.commit()
    with_call_out = rule.evaluate(
        build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2))
    )
    rest = [row for row in with_call_out if row.code == "WORKTIME_MIN_REST"]
    assert rest
    assert rest[0].details["roster_slot_id"] == follow.id
    assert rest[0].details["rest_minutes"] == 10 * 60


def test_min_rest_pending_compensation_code(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="pending@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="PEND")
    first = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 1),
        starts_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 1, 20, 0, tzinfo=UTC),
    )
    second = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 6, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 14, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, slot=first, member=member)
    _add_assignment(db, slot=second, member=member)
    db.commit()
    rule = MinRestPeriodRule(
        WorkTimeRuleMinRestPeriod(
            hours=Decimal("11"),
            reducible_to_hours=Decimal("10"),
            compensation_window_days=14,
        )
    )
    warnings = rule.evaluate(
        build_plan_state(db, organization_id=1, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2))
    )
    assert _codes(warnings) == {"WORKTIME_REST_COMPENSATION_PENDING"}


def test_rest_after_long_duty(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="long@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="LONG")
    first = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 1),
        starts_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 1, 21, 0, tzinfo=UTC),
    )
    second = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 2),
        starts_at=datetime(2026, 3, 2, 6, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 2, 12, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, slot=first, member=member)
    _add_assignment(db, slot=second, member=member)
    db.commit()
    warnings = RestAfterLongDutyRule(
        WorkTimeRuleRestAfterLongDuty(trigger_hours=Decimal("12"), mandatory_rest_hours=Decimal("11"))
    ).evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 2)))
    assert _codes(warnings) == {"WORKTIME_REST_AFTER_LONG_DUTY"}


def test_weekly_average_matches_hand_computed_fixture_to_the_minute(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="avg@example.com")
    end = date(2026, 3, 31)
    start = date(2025, 12, 31)
    days = (end - start).days + 1
    total = 37440
    assert days == 91
    assert total * 7 == 48 * 60 * days
    db.add(
        TimeEntry(
            organization_id=1,
            team_member_id=member.id,
            entry_date=start,
            kind="work",
            source="manual",
            duration_minutes=total,
            statutory_minutes=total,
            credited_minutes=total * 4,
        )
    )
    _activate_rules(
        db,
        [
            {
                "type": "weekly_average_cap",
                "severity": "warning",
                "hours": "48",
                "reference_period_months": 3,
                "rolling": True,
            }
        ],
    )
    rule = WeeklyAverageCapRule(
        WorkTimeRuleWeeklyAverageCap(hours=Decimal("48"), reference_period_months=3, rolling=True)
    )
    state = build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=end)
    assert state.load_start >= date(2026, 1, 20)
    exact = rule.evaluate(state)
    assert [row.code for row in exact if row.code == "WORKTIME_WEEKLY_AVERAGE"] == []
    extra = 13
    assert (total + extra) * 7 == (48 * 60 + 1) * days
    ledger_row = db.scalars(select(TimeEntry)).first()
    assert ledger_row is not None
    ledger_row.statutory_minutes = total + extra
    ledger_row.duration_minutes = total + extra
    db.commit()
    over = rule.evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=end))
    flagged = [row for row in over if row.code == "WORKTIME_WEEKLY_AVERAGE"]
    assert flagged
    assert flagged[0].details["average_weekly_minutes"] == 48 * 60 + 1
    assert flagged[0].details["statutory_minutes"] == total + extra


def test_opt_out_weekly_cap_uses_base_standard_tier(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="opt@example.com")
    db.add(
        TimeEntry(
            organization_id=1,
            team_member_id=member.id,
            entry_date=date(2026, 3, 31),
            kind="work",
            source="manual",
            duration_minutes=60 * 60,
            statutory_minutes=60 * 60,
            credited_minutes=0,
        )
    )
    db.commit()
    warnings = OptOutWeeklyCapRule(
        WorkTimeRuleOptOutWeeklyCap(
            hours_by_tier={"standard": Decimal("8"), "regional_agreement": Decimal("60")},
            reference_period_months=1,
        )
    ).evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)))
    assert _codes(warnings) == {"WORKTIME_WEEKLY_AVERAGE_OPT_OUT"}


def test_max_consecutive_work_days(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="streak@example.com")
    for offset, minutes in enumerate((480, 480, 480)):
        db.add(
            TimeEntry(
                organization_id=1,
                team_member_id=member.id,
                entry_date=date(2026, 3, 1) + timedelta(days=offset),
                kind="work",
                source="manual",
                duration_minutes=minutes,
                statutory_minutes=minutes,
            )
        )
    db.commit()
    warnings = MaxConsecutiveWorkDaysRule(WorkTimeRuleMaxConsecutiveWorkDays(days=2)).evaluate(
        build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 3))
    )
    assert "WORKTIME_CONSECUTIVE_DAYS" in _codes(warnings)


def test_max_duties_per_period_includes_quarterly_allowance(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="duties@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="CAP")
    for index in range(4):
        day = date(2026, 3, 1 + index)
        slot = _add_slot(
            db,
            period=period,
            template=template,
            variant=variant,
            slot_date=day,
            starts_at=datetime(2026, 3, 1 + index, 8, 0, tzinfo=UTC),
            ends_at=datetime(2026, 3, 1 + index, 16, 0, tzinfo=UTC),
            position=index + 1,
        )
        _add_assignment(db, slot=slot, member=member)
    db.commit()
    allowed = MaxDutiesPerPeriodRule(
        WorkTimeRuleMaxDutiesPerPeriod(count=3, period="month", additional_allowance_per_quarter=1)
    ).evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)))
    assert [row.code for row in allowed if row.code == "WORKTIME_MAX_DUTIES"] == []
    over = MaxDutiesPerPeriodRule(
        WorkTimeRuleMaxDutiesPerPeriod(count=2, period="month", additional_allowance_per_quarter=1)
    ).evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)))
    assert "WORKTIME_MAX_DUTIES" in _codes(over)


def test_documentation_requirement(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="docs@example.com")
    period = _add_period(db, 2026, 3)
    template, variant = _add_template(db, code="DOC")
    slot = _add_slot(
        db,
        period=period,
        template=template,
        variant=variant,
        slot_date=date(2026, 3, 4),
        starts_at=datetime(2026, 3, 4, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
    )
    _add_assignment(db, slot=slot, member=member)
    db.commit()
    warnings = DocumentationRequirementRule(
        WorkTimeRuleDocumentationRequirement(threshold_hours=Decimal("8"), retention_months=24)
    ).evaluate(build_plan_state(db, organization_id=1, start_date=date(2026, 3, 4), end_date=date(2026, 3, 4)))
    assert _codes(warnings) == {"WORKTIME_DOCUMENTATION_GAP"}


def test_error_severity_blocks_preflight_warning_does_not(plan_db):
    db, _engine = plan_db
    member = _add_member(db, email="preflight@example.com")
    june = _add_period(db, 2026, 6)
    july = _add_period(db, 2026, 7)
    template, variant = _add_template(db, code="PF")
    first = _add_slot(
        db,
        period=june,
        template=template,
        variant=variant,
        slot_date=date(2026, 6, 30),
        starts_at=datetime(2026, 6, 30, 8, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
    )
    follow = _add_slot(
        db,
        period=july,
        template=template,
        variant=variant,
        slot_date=date(2026, 7, 1),
        starts_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
        position=2,
    )
    _add_assignment(db, slot=first, member=member)
    db.commit()

    def _payload() -> RosterSlotAssignmentUpsert:
        return RosterSlotAssignmentUpsert(roster_slot_id=follow.id, team_member_id=member.id)

    _activate_rules(
        db,
        [
            {
                "type": "min_rest_period",
                "severity": "warning",
                "hours": "11",
                "reducible_to_hours": "10",
                "compensation_window_days": 31,
                "call_out_handling": "interrupt",
            }
        ],
    )
    warning_rows = _preflight_assignment_warnings(
        db, slot=follow, team_member_id=member.id, organization_id=1, manual_override=False
    )
    assert any(row.code == "WORKTIME_MIN_REST" and row.severity == "warning" for row in warning_rows)
    assert find_blocking_constraint(warning_rows) is None
    upsert_roster_slot_assignment(
        db, _payload(), organization_id=1, actor="test", source="test"
    )

    db.query(RosterSlotAssignment).filter(RosterSlotAssignment.roster_slot_id == follow.id).delete()
    db.query(WorkTimeRuleSet).delete()
    _activate_rules(
        db,
        [
            {
                "type": "min_rest_period",
                "severity": "error",
                "hours": "11",
                "reducible_to_hours": "10",
                "compensation_window_days": 31,
                "call_out_handling": "interrupt",
            }
        ],
    )
    error_rows = _preflight_assignment_warnings(
        db, slot=follow, team_member_id=member.id, organization_id=1, manual_override=False
    )
    blocking = find_blocking_constraint(error_rows)
    assert blocking is not None
    assert blocking.code == "WORKTIME_MIN_REST"
    with pytest.raises(ValueError, match="Minimum rest period"):
        upsert_roster_slot_assignment(
            db, _payload(), organization_id=1, actor="test", source="test"
        )


def test_month_validation_30_members_12_month_reference_stays_within_budget(plan_db):
    db, _engine = plan_db
    period = _add_period(db, 2026, 3)
    members = [_add_member(db, email=f"m{index}@example.com", first_name=f"M{index}") for index in range(30)]
    history_start = date(2025, 3, 31)
    for member in members:
        db.add(
            TimeEntry(
                organization_id=1,
                team_member_id=member.id,
                entry_date=history_start,
                kind="work",
                source="manual",
                duration_minutes=2000,
                statutory_minutes=2000,
                credited_minutes=8000,
            )
        )
    _activate_rules(
        db,
        [
            {
                "type": "weekly_average_cap",
                "severity": "warning",
                "hours": "48",
                "reference_period_months": 12,
                "rolling": True,
            }
        ],
    )
    started = perf_counter()
    warnings = validate_roster(db, period.id, organization_id=1)
    elapsed = perf_counter() - started
    state = build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31))
    assert elapsed < BENCHMARK_BUDGET_SECONDS
    assert state.load_start >= date(2026, 1, 15)
    assert state.load_start <= date(2026, 3, 1)
    assert isinstance(warnings, list)
