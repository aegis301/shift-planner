import json
import os
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Organization,
    PlanningCell,
    PlanningDayStatusDefinition,
    PlanningPeriod,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftTemplate,
    ShiftVariant,
    TeamMember,
    TeamMemberPlanningPattern,
    TeamMemberPropertyDefinition,
    TeamMemberPropertyValue,
)
from app.models.base import Base
from app.schemas.domain import ValidationWarning
from app.services.constraints import evaluate_assignment_constraints, resolve_slot_constraints
from app.services.team_member_property_values import property_value_maps_for_members
from app.services.validation import validate_roster

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "constraints_golden.json"


def _warning_snapshot(warning: ValidationWarning) -> dict:
    return {
        "code": warning.code,
        "severity": warning.severity,
        "team_member_id": warning.team_member_id,
        "date": warning.date.isoformat() if warning.date is not None else None,
        "details": json.loads(json.dumps(warning.details, default=str)),
    }


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.fixture()
def golden_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = testing_session()
    seed_constraints_golden_fixture(db)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def seed_constraints_golden_fixture(db: Session) -> None:
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.add(ShiftGroup(id=1, organization_id=1, code="icu", name="ICU", display_order=0))
    db.add(
        PlanningDayStatusDefinition(
            organization_id=1,
            code="urlaub",
            label="Urlaub",
            color_preset="sky",
            blocks_roster_assignment=True,
        )
    )
    alice = TeamMember(
        id=1,
        organization_id=1,
        first_name="Alice",
        last_name="Gold",
        email="alice.gold@example.com",
        employment_percentage=100,
        is_active=True,
    )
    bob = TeamMember(
        id=2,
        organization_id=1,
        first_name="Bob",
        last_name="Gold",
        email="bob.gold@example.com",
        employment_percentage=100,
        is_active=True,
    )
    db.add_all([alice, bob])
    grade = TeamMemberPropertyDefinition(
        id=1,
        organization_id=1,
        name="grade",
        type="number",
        options=[],
    )
    db.add(grade)
    db.flush()
    db.add(
        TeamMemberPropertyValue(
            organization_id=1,
            team_member_id=1,
            property_definition_id=1,
            value=1,
        )
    )
    db.add(
        TeamMemberPlanningPattern(
            organization_id=1,
            team_member_id=1,
            label="Avoid Monday nights",
            is_active=True,
            rule={
                "type": "avoid_time_window",
                "weekdays": ["mon"],
                "window_start": "20:00",
                "window_end": "06:00",
                "match_mode": "overlap",
                "anchor": "any_overlap_day",
            },
            severity="error",
            display_order=0,
        )
    )

    same = ShiftTemplate(
        id=1,
        organization_id=1,
        code="SAME",
        name="Same day",
        category="other",
        constraints=[{"type": "no_additional_same_day", "severity": "error"}],
    )
    rest = ShiftTemplate(
        id=2,
        organization_id=1,
        code="REST",
        name="Rest",
        category="bereitschaftsdienst",
        constraints=[],
    )
    monthly = ShiftTemplate(
        id=3,
        organization_id=1,
        code="MAX",
        name="Monthly cap",
        category="other",
        constraints=[],
    )
    couple = ShiftTemplate(
        id=4,
        organization_id=1,
        code="COUPLE",
        name="Coupled",
        category="other",
        constraints=[],
    )
    prop = ShiftTemplate(
        id=5,
        organization_id=1,
        code="PROP",
        name="Property",
        category="other",
        constraints=[],
    )
    overlap = ShiftTemplate(
        id=6,
        organization_id=1,
        code="OVER",
        name="Overlap",
        category="other",
        constraints=[],
    )
    db.add_all([same, rest, monthly, couple, prop, overlap])
    db.flush()

    v_same = ShiftVariant(
        id=1,
        shift_template_id=1,
        label="Day",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(16, 0),
        required_count=2,
        constraints=[],
    )
    v_rest = ShiftVariant(
        id=2,
        shift_template_id=2,
        label="24h",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(8, 0),
        end_day_offset=1,
        required_count=1,
        constraints=[{"type": "min_rest_hours", "severity": "warning", "min_rest_hours": 11}],
    )
    v_rest_day = ShiftVariant(
        id=3,
        shift_template_id=2,
        label="Follow-on",
        start_day_class="any",
        starts_at=time(10, 0),
        ends_at=time(18, 0),
        required_count=1,
        constraints=[{"type": "min_rest_hours", "severity": "warning", "min_rest_hours": 11}],
    )
    v_max = ShiftVariant(
        id=4,
        shift_template_id=3,
        label="Cap",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(16, 0),
        required_count=2,
        constraints=[
            {"type": "max_assignments_per_month", "severity": "warning", "max_assignments_per_month": 1}
        ],
    )
    v_early = ShiftVariant(
        id=5,
        shift_template_id=4,
        label="Early",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(12, 0),
        required_count=1,
        constraints=[],
    )
    v_late = ShiftVariant(
        id=6,
        shift_template_id=4,
        label="Late",
        start_day_class="any",
        starts_at=time(18, 0),
        ends_at=time(22, 0),
        required_count=1,
        constraints=[],
    )
    v_prop = ShiftVariant(
        id=7,
        shift_template_id=5,
        label="Main",
        start_day_class="any",
        starts_at=time(8, 0),
        ends_at=time(16, 0),
        required_count=1,
        constraints=[
            {
                "type": "team_member_property_requirement",
                "severity": "warning",
                "property_requirement": {
                    "kind": "atom",
                    "property_definition_id": 1,
                    "op": "gte",
                    "value": 3,
                },
            }
        ],
    )
    v_over = ShiftVariant(
        id=8,
        shift_template_id=6,
        label="Night",
        start_day_class="any",
        starts_at=time(20, 0),
        ends_at=time(6, 0),
        end_day_offset=1,
        required_count=1,
        constraints=[],
    )
    db.add_all([v_same, v_rest, v_rest_day, v_max, v_early, v_late, v_prop, v_over])
    db.flush()
    v_early.constraints = [
        {
            "type": "requires_coupled_shift",
            "severity": "warning",
            "paired_shift_variant_id": 6,
            "partner_day_offset": 1,
        }
    ]

    june = PlanningPeriod(id=1, organization_id=1, year=2026, month=6, status="draft")
    july = PlanningPeriod(id=2, organization_id=1, year=2026, month=7, status="draft")
    db.add_all([june, july])
    db.flush()

    def add_slot(
        *,
        slot_id: int,
        period_id: int,
        template_id: int,
        variant_id: int,
        slot_date: date,
        position: int,
        starts_at: datetime,
        ends_at: datetime,
    ) -> RosterSlot:
        slot = RosterSlot(
            id=slot_id,
            planning_period_id=period_id,
            shift_template_id=template_id,
            shift_variant_id=variant_id,
            slot_date=slot_date,
            position=position,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        db.add(slot)
        return slot

    add_slot(
        slot_id=1,
        period_id=1,
        template_id=1,
        variant_id=1,
        slot_date=date(2026, 6, 5),
        position=1,
        starts_at=_utc(2026, 6, 5, 8),
        ends_at=_utc(2026, 6, 5, 16),
    )
    add_slot(
        slot_id=2,
        period_id=1,
        template_id=1,
        variant_id=1,
        slot_date=date(2026, 6, 5),
        position=2,
        starts_at=_utc(2026, 6, 5, 8),
        ends_at=_utc(2026, 6, 5, 16),
    )
    add_slot(
        slot_id=3,
        period_id=1,
        template_id=2,
        variant_id=2,
        slot_date=date(2026, 6, 12),
        position=1,
        starts_at=_utc(2026, 6, 12, 8),
        ends_at=_utc(2026, 6, 13, 8),
    )
    add_slot(
        slot_id=4,
        period_id=1,
        template_id=2,
        variant_id=3,
        slot_date=date(2026, 6, 13),
        position=1,
        starts_at=_utc(2026, 6, 13, 10),
        ends_at=_utc(2026, 6, 13, 18),
    )
    add_slot(
        slot_id=5,
        period_id=1,
        template_id=3,
        variant_id=4,
        slot_date=date(2026, 6, 8),
        position=1,
        starts_at=_utc(2026, 6, 8, 8),
        ends_at=_utc(2026, 6, 8, 16),
    )
    add_slot(
        slot_id=6,
        period_id=1,
        template_id=3,
        variant_id=4,
        slot_date=date(2026, 6, 8),
        position=2,
        starts_at=_utc(2026, 6, 8, 8),
        ends_at=_utc(2026, 6, 8, 16),
    )
    add_slot(
        slot_id=7,
        period_id=1,
        template_id=4,
        variant_id=5,
        slot_date=date(2026, 6, 10),
        position=1,
        starts_at=_utc(2026, 6, 10, 8),
        ends_at=_utc(2026, 6, 10, 12),
    )
    add_slot(
        slot_id=8,
        period_id=1,
        template_id=4,
        variant_id=6,
        slot_date=date(2026, 6, 11),
        position=1,
        starts_at=_utc(2026, 6, 11, 18),
        ends_at=_utc(2026, 6, 11, 22),
    )
    add_slot(
        slot_id=9,
        period_id=1,
        template_id=5,
        variant_id=7,
        slot_date=date(2026, 6, 20),
        position=1,
        starts_at=_utc(2026, 6, 20, 8),
        ends_at=_utc(2026, 6, 20, 16),
    )
    add_slot(
        slot_id=10,
        period_id=1,
        template_id=6,
        variant_id=8,
        slot_date=date(2026, 6, 15),
        position=1,
        starts_at=_utc(2026, 6, 15, 20),
        ends_at=_utc(2026, 6, 16, 6),
    )
    add_slot(
        slot_id=11,
        period_id=1,
        template_id=2,
        variant_id=2,
        slot_date=date(2026, 6, 30),
        position=1,
        starts_at=_utc(2026, 6, 30, 8),
        ends_at=_utc(2026, 7, 1, 8),
    )
    add_slot(
        slot_id=12,
        period_id=1,
        template_id=4,
        variant_id=5,
        slot_date=date(2026, 6, 30),
        position=1,
        starts_at=_utc(2026, 6, 30, 8),
        ends_at=_utc(2026, 6, 30, 12),
    )
    add_slot(
        slot_id=13,
        period_id=2,
        template_id=2,
        variant_id=3,
        slot_date=date(2026, 7, 1),
        position=1,
        starts_at=_utc(2026, 7, 1, 10),
        ends_at=_utc(2026, 7, 1, 18),
    )
    add_slot(
        slot_id=14,
        period_id=2,
        template_id=4,
        variant_id=6,
        slot_date=date(2026, 7, 1),
        position=1,
        starts_at=_utc(2026, 7, 1, 18),
        ends_at=_utc(2026, 7, 1, 22),
    )
    db.flush()

    db.add(
        PlanningCell(
            planning_period_id=1,
            shift_group_id=1,
            team_member_id=1,
            cell_date=date(2026, 6, 16),
            status="urlaub",
        )
    )
    db.add(
        PlanningShiftIntent(
            planning_period_id=1,
            team_member_id=1,
            cell_date=date(2026, 6, 20),
            shift_group_id=1,
            shift_template_id=5,
            kind="no_go",
        )
    )

    for slot_id in (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 13):
        db.add(RosterSlotAssignment(roster_slot_id=slot_id, team_member_id=1))
    db.add(RosterSlotAssignment(roster_slot_id=8, team_member_id=2))
    db.add(RosterSlotAssignment(roster_slot_id=12, team_member_id=2))
    db.commit()


def capture_constraint_snapshots(db: Session) -> dict:
    from app.services.matrix import list_planning_cells
    from app.services.roster_matrix import list_roster_slot_assignments

    june_assignments = list_roster_slot_assignments(db, planning_period_id=1)
    july_assignments = list_roster_slot_assignments(db, planning_period_id=2)
    june_cells = list_planning_cells(db, planning_period_id=1)
    member_ids = {1, 2}
    value_maps = property_value_maps_for_members(db, organization_id=1, team_member_ids=member_ids)
    per_assignment: list[dict] = []
    for assignment in [*june_assignments, *july_assignments]:
        slot = assignment.roster_slot
        period_id = slot.planning_period_id
        member_assignments = [
            row
            for row in (june_assignments if period_id == 1 else july_assignments)
            if row.team_member_id == assignment.team_member_id
        ]
        member_cells = [row for row in june_cells if row.team_member_id == assignment.team_member_id]
        resolved = resolve_slot_constraints(db, slot)
        warnings = evaluate_assignment_constraints(
            db=db,
            slot=slot,
            team_member_id=assignment.team_member_id,
            resolved_constraints=resolved,
            assigned_slots_for_member=member_assignments,
            planning_cells_for_member=member_cells,
            assignment_id=assignment.id,
            member_property_values=value_maps.get(assignment.team_member_id, {}),
        )
        per_assignment.append(
            {
                "roster_slot_id": slot.id,
                "assignment_id": assignment.id,
                "planning_period_id": period_id,
                "warnings": [_warning_snapshot(row) for row in warnings],
            }
        )
    return {
        "notes": [
            "Baseline snapshot of month-scoped evaluate_assignment_constraints and validate_roster.",
            "Issue #02 / #57: ROSTER_CONSTRAINT_MIN_REST_HOURS now includes the 24h June 30 duty vs July 1 follow-on (slots 11 and 13).",
            "Issue #02 / #57: ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED now evaluates a partner date in the following month (slot 12 -> 2026-07-01).",
            "Issue #03 / #58: in-month MEMBER_PATTERN_AVOID_TIME_WINDOW on slot 10 and ROSTER_TEMPLATE_NO_GO_CONFLICT on slot 9.",
        ],
        "per_assignment": per_assignment,
        "validate_june": [_warning_snapshot(row) for row in validate_roster(db, 1, organization_id=1)],
        "validate_july": [_warning_snapshot(row) for row in validate_roster(db, 2, organization_id=1)],
    }


def test_constraints_golden_matches_current_evaluation(golden_db):
    actual = capture_constraint_snapshots(golden_db)
    if os.environ.get("UPDATE_CONSTRAINTS_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(actual, indent=2, sort_keys=False) + "\n")
    expected = json.loads(GOLDEN_PATH.read_text())
    assert actual == expected


def _warnings_for_slot(snapshot: dict, slot_id: int) -> list[dict]:
    for row in snapshot["per_assignment"]:
        if row["roster_slot_id"] == slot_id:
            return row["warnings"]
    raise AssertionError(f"slot {slot_id} missing from snapshot")


def test_min_rest_hours_considers_assignment_outside_planning_period(golden_db):
    snapshot = capture_constraint_snapshots(golden_db)
    june_duty = _warnings_for_slot(snapshot, 11)
    rest = [row for row in june_duty if row["code"] == "ROSTER_CONSTRAINT_MIN_REST_HOURS"]
    assert len(rest) == 1
    assert rest[0]["details"]["related_roster_slot_id"] == 13
    assert rest[0]["details"]["direction"] == "after"
    july_follow_on = _warnings_for_slot(snapshot, 13)
    rest_july = [row for row in july_follow_on if row["code"] == "ROSTER_CONSTRAINT_MIN_REST_HOURS"]
    assert len(rest_july) == 1
    assert rest_july[0]["details"]["related_roster_slot_id"] == 11


def test_requires_coupled_shift_evaluates_partner_in_following_month(golden_db):
    snapshot = capture_constraint_snapshots(golden_db)
    warnings = _warnings_for_slot(snapshot, 12)
    coupled = [row for row in warnings if row["code"] == "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED"]
    assert len(coupled) == 1
    assert coupled[0]["details"]["partner_date"] == "2026-07-01"
    assert coupled[0]["team_member_id"] == 2


def test_max_assignments_and_coupled_warnings_still_merge(golden_db):
    snapshot = capture_constraint_snapshots(golden_db)
    max_rows = [
        row for row in snapshot["validate_june"] if row["code"] == "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH"
    ]
    assert len(max_rows) == 1
    assert max_rows[0]["details"]["violating_roster_slot_ids"] == [5, 6]
    in_month_coupled = [
        row
        for row in snapshot["validate_june"]
        if row["code"] == "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED"
        and row["details"].get("partner_date") == "2026-06-11"
    ]
    assert len(in_month_coupled) == 1
    assert in_month_coupled[0]["details"]["source_roster_slot_ids"] == [7]


def test_golden_in_month_pattern_and_builtin_codes(golden_db):
    snapshot = capture_constraint_snapshots(golden_db)
    june = snapshot["validate_june"]
    codes = {row["code"] for row in june}
    assert "ROSTER_TEMPLATE_NO_GO_CONFLICT" in codes
    assert "ROSTER_MATRIX_DUPLICATE_DAY" in codes
    assert "ROSTER_CONSECUTIVE_WEEKENDS" in codes
    assert "MEMBER_PATTERN_AVOID_TIME_WINDOW" in codes
    no_go = [row for row in june if row["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT"]
    assert len(no_go) == 1
    assert no_go[0]["date"] == "2026-06-20"
    assert no_go[0]["details"]["roster_slot_id"] == 9
    avoid = [row for row in june if row["code"] == "MEMBER_PATTERN_AVOID_TIME_WINDOW"]
    assert len(avoid) == 1
    assert avoid[0]["severity"] == "info"
    assert avoid[0]["date"] == "2026-06-15"
    assert avoid[0]["details"]["roster_slot_id"] == 10
    cons = [row for row in june if row["code"] == "ROSTER_CONSECUTIVE_WEEKENDS"]
    assert len(cons) == 1
    assert cons[0]["details"]["pairs"] == [
        {
            "first_weekend_saturday": "2026-06-13",
            "second_weekend_saturday": "2026-06-20",
        }
    ]
    assert cons[0]["details"]["roster_slot_ids"] == [4, 9]


def test_consecutive_weekends_last_saturday_of_month_and_first_of_next(golden_db):
    db = golden_db
    june_slot = RosterSlot(
        id=15,
        planning_period_id=1,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 6, 27),
        position=1,
        starts_at=_utc(2026, 6, 27, 8),
        ends_at=_utc(2026, 6, 27, 16),
    )
    july_slot = RosterSlot(
        id=16,
        planning_period_id=2,
        shift_template_id=1,
        shift_variant_id=1,
        slot_date=date(2026, 7, 4),
        position=1,
        starts_at=_utc(2026, 7, 4, 8),
        ends_at=_utc(2026, 7, 4, 16),
    )
    db.add_all([june_slot, july_slot])
    db.flush()
    db.add(RosterSlotAssignment(roster_slot_id=15, team_member_id=2))
    db.add(RosterSlotAssignment(roster_slot_id=16, team_member_id=2))
    db.commit()

    def weekend_pairs(warnings: list[ValidationWarning], member_id: int) -> list[dict]:
        return [
            row.details["pairs"]
            for row in warnings
            if row.code == "ROSTER_CONSECUTIVE_WEEKENDS" and row.team_member_id == member_id
        ]

    expected = [
        {
            "first_weekend_saturday": "2026-06-27",
            "second_weekend_saturday": "2026-07-04",
        }
    ]
    june_pairs = weekend_pairs(validate_roster(db, 1, organization_id=1), 2)
    july_pairs = weekend_pairs(validate_roster(db, 2, organization_id=1), 2)
    assert june_pairs == [expected]
    assert july_pairs == [expected]


def test_template_no_go_respects_manual_override(golden_db):
    db = golden_db
    assignment = db.get(RosterSlotAssignment, 8)
    assert assignment is not None
    assignment.manual_override = True
    db.commit()
    snapshot = capture_constraint_snapshots(db)
    no_go = [row for row in snapshot["validate_june"] if row["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT"]
    assert no_go == []

