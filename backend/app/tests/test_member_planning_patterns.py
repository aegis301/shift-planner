"""Tests for member planning patterns."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Organization,
    PlanningCell,
    PlanningPeriod,
    PlanningPeriodShiftGroupStatus,
    RosterSlot,
    ShiftGroup,
    TeamMember,
    TeamMemberPlanningPattern,
    TeamMemberShiftGroup,
)
from app.models.base import Base
from app.schemas import (
    AllowedCalendarWeekParityMemberPatternRule,
    AvoidTimeWindowMemberPatternRule,
    IsoWeekCycleMemberPatternRule,
    RecurringWeekdayStatusMemberPatternRule,
    TeamMemberPlanningPatternsReplace,
    TeamMemberPlanningPatternUpsertItem,
)
from app.services.member_planning_patterns import (
    evaluate_member_planning_patterns,
    merge_recurring_pattern_cell_target,
    read_organization_member_pattern_policy,
    replace_team_member_planning_patterns,
    validate_pattern_severity,
)
from app.services.shift_intervals import is_iso_week_cycle_on_week


@pytest.fixture()
def pattern_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.add(TeamMember(id=1, organization_id=1, first_name="A", last_name="B", email="a@example.com", employment_percentage=100))
    db.add(ShiftGroup(organization_id=1, code="sg", name="SG", display_order=0))
    db.flush()
    db.add(TeamMemberShiftGroup(team_member_id=1, shift_group_id=1, start_date=date(2000, 1, 1)))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_validate_pattern_severity_rejects_error_without_policy():
    rule = AllowedCalendarWeekParityMemberPatternRule(parity="even")
    policy = read_organization_member_pattern_policy(Organization(id=1, name="x", slug="x", member_pattern_policy={"hard_types": []}))
    with pytest.raises(ValueError):
        validate_pattern_severity(rule, severity="error", policy=policy)


def test_avoid_time_window_matches_saturday_night(pattern_db):
    db = pattern_db
    slot = RosterSlot(
        id=1,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 6),
        position=1,
        starts_at=datetime(2026, 6, 6, 23, 0),
        ends_at=datetime(2026, 6, 7, 7, 0),
    )
    pattern = TeamMemberPlanningPattern(
        id=1,
        organization_id=1,
        team_member_id=1,
        label="No Saturday nights",
        is_active=True,
        rule={
            "type": "avoid_time_window",
            "weekdays": ["sat"],
            "window_start": "22:00",
            "window_end": "06:00",
            "match_mode": "overlap",
            "anchor": "any_overlap_day",
        },
        severity="warning",
        display_order=0,
    )
    warnings = evaluate_member_planning_patterns(db=db, slot=slot, team_member_id=1, patterns=[pattern])
    assert len(warnings) == 1
    assert warnings[0].code == "MEMBER_PATTERN_AVOID_TIME_WINDOW"
    assert warnings[0].severity == "info"


def test_avoid_time_window_matches_timezone_aware_slot_interval(pattern_db):
    db = pattern_db
    slot = RosterSlot(
        id=1,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 6),
        position=1,
        starts_at=datetime(2026, 6, 6, 23, 0, tzinfo=UTC),
        ends_at=datetime(2026, 6, 7, 7, 0, tzinfo=UTC),
    )
    pattern = TeamMemberPlanningPattern(
        id=1,
        organization_id=1,
        team_member_id=1,
        label="No Saturday nights",
        is_active=True,
        rule={
            "type": "avoid_time_window",
            "weekdays": ["sat"],
            "window_start": "22:00",
            "window_end": "06:00",
            "match_mode": "overlap",
            "anchor": "any_overlap_day",
        },
        severity="warning",
        display_order=0,
    )
    warnings = evaluate_member_planning_patterns(db=db, slot=slot, team_member_id=1, patterns=[pattern])
    assert len(warnings) == 1
    assert warnings[0].code == "MEMBER_PATTERN_AVOID_TIME_WINDOW"


def test_avoid_time_window_legacy_json_normalized_to_windows():
    raw = {
        "type": "avoid_time_window",
        "weekdays": ["sat"],
        "window_start": "22:00",
        "window_end": "06:00",
        "match_mode": "overlap",
        "anchor": "any_overlap_day",
    }
    rule = AvoidTimeWindowMemberPatternRule.model_validate(raw)
    assert len(rule.windows) == 1
    assert rule.windows[0].weekdays == ["sat"]


def test_avoid_time_window_multiple_bands_match_respective_weekdays(pattern_db):
    db = pattern_db
    pattern = TeamMemberPlanningPattern(
        id=11,
        organization_id=1,
        team_member_id=1,
        label="Stacked",
        is_active=True,
        rule={
            "type": "avoid_time_window",
            "match_mode": "overlap",
            "windows": [
                {
                    "weekdays": ["wed"],
                    "window_start": "18:00",
                    "window_end": "20:00",
                    "match_mode": "overlap",
                    "anchor": "any_overlap_day",
                },
                {
                    "weekdays": ["fri"],
                    "window_start": "14:00",
                    "window_end": "18:00",
                    "match_mode": "overlap",
                    "anchor": "any_overlap_day",
                },
            ],
        },
        severity="info",
        display_order=0,
    )
    wed_slot = RosterSlot(
        id=11,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 10),
        position=1,
        starts_at=datetime(2026, 6, 10, 19, 0),
        ends_at=datetime(2026, 6, 10, 19, 30),
    )
    w1 = evaluate_member_planning_patterns(db=db, slot=wed_slot, team_member_id=1, patterns=[pattern])
    assert len(w1) == 1
    assert w1[0].details["window_band_index"] == 0
    fri_slot = RosterSlot(
        id=12,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 12),
        position=1,
        starts_at=datetime(2026, 6, 12, 15, 0),
        ends_at=datetime(2026, 6, 12, 16, 0),
    )
    w2 = evaluate_member_planning_patterns(db=db, slot=fri_slot, team_member_id=1, patterns=[pattern])
    assert len(w2) == 1
    assert w2[0].details["window_band_index"] == 1


def test_avoid_time_window_stored_severity_does_not_affect_evaluation(pattern_db):
    db = pattern_db
    slot = RosterSlot(
        id=3,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 6),
        position=1,
        starts_at=datetime(2026, 6, 6, 23, 0),
        ends_at=datetime(2026, 6, 7, 7, 0),
    )
    pattern = TeamMemberPlanningPattern(
        id=3,
        organization_id=1,
        team_member_id=1,
        label="No Saturday nights",
        is_active=True,
        rule={
            "type": "avoid_time_window",
            "weekdays": ["sat"],
            "window_start": "22:00",
            "window_end": "06:00",
            "match_mode": "overlap",
            "anchor": "any_overlap_day",
        },
        severity="error",
        display_order=0,
    )
    warnings = evaluate_member_planning_patterns(db=db, slot=slot, team_member_id=1, patterns=[pattern])
    assert len(warnings) == 1
    assert warnings[0].severity == "info"


def test_week_parity_blocks_odd_week(pattern_db):
    db = pattern_db
    slot = RosterSlot(
        id=2,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 1, 2),
        position=1,
        starts_at=datetime(2026, 1, 2, 8, 0),
        ends_at=datetime(2026, 1, 2, 16, 0),
    )
    pattern = TeamMemberPlanningPattern(
        id=2,
        organization_id=1,
        team_member_id=1,
        label="Even weeks only",
        is_active=True,
        rule={"type": "allowed_calendar_week_parity", "parity": "even"},
        severity="warning",
        display_order=0,
    )
    warnings = evaluate_member_planning_patterns(db=db, slot=slot, team_member_id=1, patterns=[pattern])
    assert len(warnings) == 1
    assert warnings[0].code == "MEMBER_PATTERN_WEEK_PARITY"
    assert warnings[0].details["iso_week"] == slot.slot_date.isocalendar().week


def test_allowed_calendar_week_parity_rule_default_status():
    rule = AllowedCalendarWeekParityMemberPatternRule.model_validate({"type": "allowed_calendar_week_parity", "parity": "odd"})
    assert rule.status == "frei"


def test_sync_week_parity_writes_wishes_for_excluded_iso_weeks(pattern_db):
    db = pattern_db
    _seed_open_period(db, year=2026, month=1)
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="Even weeks roster",
                rule=AllowedCalendarWeekParityMemberPatternRule(parity="even", status="urlaub"),
                severity="warning",
            )
        ]
    )
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    jan_odd_week = db.scalar(
        select(PlanningCell).where(
            PlanningCell.team_member_id == 1,
            PlanningCell.cell_date == date(2026, 1, 1),
        )
    )
    assert jan_odd_week is not None
    assert jan_odd_week.status == "urlaub"
    assert jan_odd_week.source == "recurring_pattern"
    jan_even_week = db.scalar(
        select(PlanningCell).where(
            PlanningCell.team_member_id == 1,
            PlanningCell.cell_date == date(2026, 1, 5),
        )
    )
    assert jan_even_week is None


def test_iso_week_cycle_writes_off_week_wishes_weekdays_only(pattern_db):
    db = pattern_db
    _seed_open_period(db, year=2026, month=1)
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="75 percent",
                rule=IsoWeekCycleMemberPatternRule(
                    cycle_weeks=4,
                    on_weeks=3,
                    anchor_iso_year=2026,
                    anchor_iso_week=1,
                    off_status="forschung",
                    wishes_weekdays=["mon", "tue", "wed", "thu", "fri"],
                ),
                severity="warning",
            )
        ]
    )
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    off_week_weekday = db.scalar(
        select(PlanningCell).where(
            PlanningCell.team_member_id == 1,
            PlanningCell.cell_date == date(2026, 1, 26),
        )
    )
    off_week_saturday = db.scalar(
        select(PlanningCell).where(
            PlanningCell.team_member_id == 1,
            PlanningCell.cell_date == date(2026, 1, 31),
        )
    )
    if off_week_weekday is not None:
        assert off_week_weekday.status == "forschung"
    assert off_week_saturday is None


def test_iso_week_cycle_allow_weekend_roster(pattern_db):
    db = pattern_db
    slot = RosterSlot(
        id=3,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 1, 31),
        position=1,
        starts_at=datetime(2026, 1, 31, 8, 0),
        ends_at=datetime(2026, 1, 31, 16, 0),
    )
    pattern = TeamMemberPlanningPattern(
        id=3,
        organization_id=1,
        team_member_id=1,
        label="75 with weekend",
        is_active=True,
        rule={
            "type": "iso_week_cycle",
            "cycle_weeks": 4,
            "on_weeks": 3,
            "anchor_iso_year": 2026,
            "anchor_iso_week": 1,
            "off_status": "frei",
            "wishes_weekdays": ["mon", "tue", "wed", "thu", "fri"],
            "allow_weekend_roster": True,
        },
        severity="error",
        display_order=0,
    )
    warnings = evaluate_member_planning_patterns(db=db, slot=slot, team_member_id=1, patterns=[pattern])
    assert warnings == []


def test_merge_iso_week_cycle_off_status(pattern_db):
    pattern = TeamMemberPlanningPattern(
        id=4,
        organization_id=1,
        team_member_id=1,
        label="cycle",
        is_active=True,
        rule={
            "type": "iso_week_cycle",
            "cycle_weeks": 2,
            "on_weeks": 1,
            "anchor_iso_year": 2026,
            "anchor_iso_week": 2,
            "off_status": "frei",
        },
        severity="warning",
        display_order=0,
    )
    off_day = date(2026, 1, 12)
    target = merge_recurring_pattern_cell_target(off_day, [pattern])
    if not is_iso_week_cycle_on_week(
        cell_date=off_day,
        anchor_iso_year=2026,
        anchor_iso_week=2,
        cycle_weeks=2,
        on_weeks=1,
    ):
        assert target == "frei"


def _seed_open_period(db, *, year: int, month: int) -> PlanningPeriod:
    period = PlanningPeriod(organization_id=1, year=year, month=month, status="draft")
    db.add(period)
    db.flush()
    db.add(
        PlanningPeriodShiftGroupStatus(
            planning_period_id=period.id,
            shift_group_id=1,
            status="draft",
        )
    )
    db.commit()
    return period


def test_sync_recurring_weekday_status_writes_cells(pattern_db):
    db = pattern_db
    _seed_open_period(db, year=2026, month=1)
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="Wednesdays off",
                rule=RecurringWeekdayStatusMemberPatternRule(weekdays=["wed"], status="frei"),
                severity="warning",
            )
        ]
    )
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    cells = list(db.scalars(select(PlanningCell).where(PlanningCell.team_member_id == 1)))
    assert len(cells) == 4
    assert all(c.status == "frei" and c.source == "recurring_pattern" for c in cells)


def test_sync_recurring_weekday_respects_manual_cell(pattern_db):
    db = pattern_db
    period = _seed_open_period(db, year=2026, month=1)
    db.add(
        PlanningCell(
            planning_period_id=period.id,
            shift_group_id=1,
            team_member_id=1,
            cell_date=date(2026, 1, 7),
            status="urlaub",
            source="manual",
        )
    )
    db.commit()
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="Wednesdays off",
                rule=RecurringWeekdayStatusMemberPatternRule(weekdays=["wed"], status="frei"),
                severity="warning",
            )
        ]
    )
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    manual = db.scalar(
        select(PlanningCell).where(
            PlanningCell.team_member_id == 1,
            PlanningCell.cell_date == date(2026, 1, 7),
        )
    )
    assert manual is not None
    assert manual.status == "urlaub"
    assert manual.source == "manual"
    recurring_weds = list(
        db.scalars(
            select(PlanningCell).where(
                PlanningCell.team_member_id == 1,
                PlanningCell.source == "recurring_pattern",
            )
        )
    )
    assert len(recurring_weds) == 3


def test_sync_recurring_weekday_skips_published_period(pattern_db):
    db = pattern_db
    period = PlanningPeriod(organization_id=1, year=2026, month=2, status="published")
    db.add(period)
    db.flush()
    db.add(
        PlanningPeriodShiftGroupStatus(
            planning_period_id=period.id,
            shift_group_id=1,
            status="published",
        )
    )
    db.commit()
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="Wednesdays off",
                rule=RecurringWeekdayStatusMemberPatternRule(weekdays=["wed"], status="frei"),
                severity="warning",
            )
        ]
    )
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    assert len(list(db.scalars(select(PlanningCell)))) == 0


def test_replace_patterns_roundtrip(pattern_db):
    db = pattern_db
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    payload = TeamMemberPlanningPatternsReplace(
        patterns=[
            TeamMemberPlanningPatternUpsertItem(
                label="Even weeks",
                rule=AllowedCalendarWeekParityMemberPatternRule(parity="even"),
                severity="warning",
            )
        ]
    )
    rows = replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=payload,
        policy=policy,
        actor="test",
        source="test",
    )
    assert len(rows) == 1
    assert rows[0].label == "Even weeks"


def test_create_planning_period_syncs_recurring_weekday_cells(pattern_db):
    from app.schemas import PlanningPeriodCreate
    from app.services.planning import create_planning_period

    db = pattern_db
    org = db.get(Organization, 1)
    policy = read_organization_member_pattern_policy(org)
    replace_team_member_planning_patterns(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPlanningPatternsReplace(
            patterns=[
                TeamMemberPlanningPatternUpsertItem(
                    label="Wednesdays off",
                    rule=RecurringWeekdayStatusMemberPatternRule(weekdays=["wed"], status="frei"),
                    severity="warning",
                )
            ]
        ),
        policy=policy,
        actor="test",
        source="test",
    )
    period = create_planning_period(
        db, PlanningPeriodCreate(year=2026, month=3), organization_id=1, actor="a", source="t"
    )
    cells = list(db.scalars(select(PlanningCell).where(PlanningCell.planning_period_id == period.id)))
    assert len(cells) == 4
    assert all(c.source == "recurring_pattern" for c in cells)
