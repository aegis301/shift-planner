from __future__ import annotations

import calendar
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Organization,
    PlanningPeriod,
    PlanningPlanVersion,
    RosterSlot,
    RosterSlotAssignment,
    ShiftTemplate,
    TeamMember,
    TimeEntry,
)
from app.schemas import (
    ContractCategoryRule,
    ContractGroupCreate,
    ContractStatusMapping,
    EmploymentPeriodWrite,
    PlanningCellBulkUpsert,
    PlanningCellUpsert,
    PlanningPeriodCreate,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentUpsert,
    RegularWeekPatternDay,
    RosterSlotAssignmentUpsert,
    ShiftConstraint,
    ShiftGroupCreate,
    ShiftGroupMembershipWrite,
    ShiftTemplateCreate,
    ShiftTemplateUpdate,
    ShiftVariantCreate,
    TeamMemberCreate,
    TeamMemberPropertyDefinitionCreate,
    TeamMemberPropertyRequirementAtom,
    TeamMemberPropertyValuesReplace,
    TeamMemberPropertyValueUpsertItem,
    TimeEntryCreate,
    WorkTimeConsentCreate,
)
from app.services.audit import record_audit
from app.services.contract_group_defaults import (
    OPEN_ENDED_EMPLOYMENT_START,
    default_regular_week_pattern,
    default_status_mappings,
)
from app.services.contract_groups import create_contract_group
from app.services.employment_periods import list_employment_periods, replace_employment_periods
from app.services.matrix import (
    bulk_upsert_planning_cells,
    bulk_upsert_planning_shift_intents,
    list_planning_cells,
    list_planning_shift_intents,
)
from app.services.organizations import create_organization_record, get_organization_by_slug
from app.services.planning import (
    create_planning_period,
    publish_shift_group_planning,
    set_shift_group_planning_to_preliminary,
)
from app.services.planning_day_status_definitions import cell_status_blocks_roster_assignment
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.roster_matrix import (
    list_roster_slot_assignments,
    list_roster_slots,
    sync_roster_slots_for_period,
    upsert_roster_slot_assignment,
)
from app.services.shift_groups import (
    create_shift_group,
    list_shift_groups,
    replace_group_shift_templates,
    replace_group_team_member_memberships,
    shift_group_ids_for_template,
    team_member_may_cover_template,
)
from app.services.shift_intervals import overlap_calendar_days, resolve_slot_interval
from app.services.shift_templates import (
    create_shift_template,
    create_shift_variant,
    list_shift_templates,
    update_shift_template,
)
from app.services.team_member_property_definitions import (
    create_team_member_property_definition,
    list_team_member_property_definitions,
)
from app.services.team_member_property_requirements import evaluate_property_requirement_expr
from app.services.team_member_property_values import (
    property_value_maps_for_members,
    replace_team_member_property_values,
)
from app.services.team_members import create_team_member, list_team_members
from app.services.time_entries import create_manual_entry, derive_entries
from app.services.work_time_consents import list_work_time_consents, record_work_time_consent
from app.services.work_time_preset_catalog import (
    PRESET_CODE_ARBZG,
    PRESET_CODE_TDL,
    _tv_aerzte_category_rules,
)
from app.services.work_time_presets import adopt_work_time_rule_set_preset, ensure_work_time_presets

SolverProfile = Literal["comfortable", "tight", "infeasible", "arbzg"]

ACTOR = "seed_solver_fixture"
SOURCE = "script"
DAY_STATUS_DENSITY = 0.08
WISH_DENSITY = 0.10
DAY_STATUS_CODES = ("urlaub", "forschung", "lehre")
PROFILES: tuple[SolverProfile, ...] = ("comfortable", "tight", "infeasible", "arbzg")
ARBZG_WEEKLY_CAP_HOURS = 48
ARBZG_REFERENCE_MONTHS = 6
ARBZG_JUST_UNDER_SLACK_MINUTES = 60


class SolverFixtureError(ValueError):
    pass


class SolverFixtureSafetyError(SolverFixtureError):
    pass


@dataclass(frozen=True)
class SolverFixtureResult:
    organization_id: int
    organization_slug: str
    profile: SolverProfile
    rng_seed: int
    year: int
    month: int
    history_months: int
    target_period_id: int
    history_period_ids: tuple[int, ...]
    member_ids: tuple[int, ...]
    shift_group_ids: tuple[int, ...]


@dataclass(frozen=True)
class _ProfileSpec:
    member_count: int
    no_go_density: float
    leave_count: int
    facharzt_ja_count: int | None


_PROFILE_SPECS: dict[SolverProfile, _ProfileSpec] = {
    "comfortable": _ProfileSpec(20, 0.10, 0, None),
    "tight": _ProfileSpec(20, 0.30, 6, None),
    "infeasible": _ProfileSpec(10, 0.50, 0, 3),
    "arbzg": _ProfileSpec(10, 0.10, 0, None),
}


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def default_target_year_month() -> tuple[int, int]:
    today = date.today()
    return _shift_month(today.year, today.month, 1)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _month_days(year: int, month: int) -> list[date]:
    start, end = _month_bounds(year, month)
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _subtract_months(value: date, months: int) -> date:
    year, month = _shift_month(value.year, value.month, -months)
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _minutes_for_weekly_average(days: int, target_average: int) -> int:
    if days <= 0:
        raise SolverFixtureError("weekly average window must contain at least one day")
    center = (target_average * days) // 7
    for delta in range(0, days * 2 + 1):
        for total in (center - delta, center + delta):
            if total < 0:
                continue
            average = int(
                (Decimal(total) * Decimal(7) / Decimal(days)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            if average == target_average:
                return total
    raise SolverFixtureError(
        f"Could not reach weekly average {target_average} over {days} days"
    )


def _sum_statutory_minutes(
    db: Session,
    *,
    organization_id: int,
    member_id: int,
    start_date: date,
    end_date: date,
) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.statutory_minutes), 0)).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.team_member_id == member_id,
            TimeEntry.entry_date >= start_date,
            TimeEntry.entry_date <= end_date,
        )
    )
    return int(total or 0)


@dataclass(frozen=True)
class _ArbzgRoles:
    rest_id: int
    over_id: int
    under_id: int
    documentation_id: int


@dataclass(frozen=True)
class _ArbzgDates:
    boundary_prev: date
    boundary_next: date
    within_duty: date
    within_follow: date
    documentation: date


def _arbzg_roles(members: list[TeamMember]) -> _ArbzgRoles:
    ordered = sorted(members, key=lambda row: row.id)
    if len(ordered) < 4:
        raise SolverFixtureError("arbzg profile requires at least 4 team members")
    return _ArbzgRoles(
        rest_id=ordered[0].id,
        over_id=ordered[1].id,
        under_id=ordered[2].id,
        documentation_id=ordered[3].id,
    )


def _arbzg_dates(year: int, month: int) -> _ArbzgDates:
    start, end = _month_bounds(year, month)
    prev_year, prev_month = _shift_month(year, month, -1)
    _, prev_end = _month_bounds(prev_year, prev_month)
    within_duty = start + timedelta(days=9)
    if within_duty >= end:
        within_duty = start + timedelta(days=2)
    within_follow = within_duty + timedelta(days=1)
    documentation = end
    reserved_target = {start, within_duty, within_follow}
    if documentation in reserved_target:
        documentation = start + timedelta(days=5)
    if documentation in reserved_target or documentation > end:
        raise SolverFixtureError("arbzg profile could not place a documentation day")
    return _ArbzgDates(
        boundary_prev=prev_end,
        boundary_next=start,
        within_duty=within_duty,
        within_follow=within_follow,
        documentation=documentation,
    )


def _arbzg_reserved_keys(roles: _ArbzgRoles, dates: _ArbzgDates) -> set[tuple[int, date]]:
    return {
        (roles.rest_id, dates.boundary_next),
        (roles.rest_id, dates.within_duty),
        (roles.rest_id, dates.within_follow),
        (roles.documentation_id, dates.documentation),
    }


def _first_slot_on_date(
    db: Session,
    planning_period_id: int,
    *,
    template_code: str,
    slot_date: date,
) -> RosterSlot:
    slots = [
        slot
        for slot in list_roster_slots(db, planning_period_id=planning_period_id)
        if slot.shift_template is not None
        and slot.shift_template.code == template_code
        and slot.slot_date == slot_date
    ]
    slots = sorted(slots, key=lambda slot: (slot.position, slot.id))
    if not slots:
        raise SolverFixtureError(f"No {template_code} slot on {slot_date.isoformat()}")
    return slots[0]


def _assign_slot_without_preflight(
    db: Session,
    *,
    slot: RosterSlot,
    team_member_id: int,
) -> RosterSlotAssignment:
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot.id)
    )
    previous_member_id = assignment.team_member_id if assignment is not None else None
    if assignment is None:
        assignment = RosterSlotAssignment(
            roster_slot_id=slot.id,
            team_member_id=team_member_id,
            comment=None,
            manual_override=True,
            source=SOURCE,
        )
        db.add(assignment)
        action = "create"
    else:
        assignment.team_member_id = team_member_id
        assignment.manual_override = True
        assignment.source = SOURCE
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=ACTOR,
        source=SOURCE,
        action=action,
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={
            "planning_period_id": slot.planning_period_id,
            "roster_slot_id": slot.id,
            "team_member_id": team_member_id,
            "previous_team_member_id": previous_member_id,
        },
    )
    return assignment


def _employment_percentages(member_count: int) -> list[int]:
    if member_count == 20:
        return [100] * 12 + [75] * 5 + [50] * 3
    if member_count == 10:
        return [100] * 6 + [75] * 3 + [50] * 1
    raise SolverFixtureError(f"Unsupported member count: {member_count}")


def _group_assignments(member_count: int) -> list[tuple[bool, bool]]:
    if member_count == 20:
        a_only, i_only, both = 10, 6, 4
    elif member_count == 10:
        a_only, i_only, both = 5, 3, 2
    else:
        raise SolverFixtureError(f"Unsupported member count: {member_count}")
    if a_only + i_only + both != member_count:
        both = member_count - a_only - i_only
    rows = ([(True, False)] * a_only) + ([(False, True)] * i_only) + ([(True, True)] * both)
    return rows


def _sample_count(size: int, density: float) -> int:
    if size <= 0 or density <= 0:
        return 0
    return min(size, max(1, round(size * density)))


def _org_has_plan_versions(db: Session, organization_id: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(PlanningPlanVersion)
        .join(PlanningPeriod, PlanningPeriod.id == PlanningPlanVersion.planning_period_id)
        .where(PlanningPeriod.organization_id == organization_id)
    )
    return bool(count)


def _assert_safe_target(
    db: Session,
    organization: Organization,
    *,
    force: bool,
) -> None:
    if organization.id == settings.default_organization_id and not force:
        raise SolverFixtureSafetyError(
            "Refusing to write into DEFAULT_ORGANIZATION_ID without --force"
        )
    if _org_has_plan_versions(db, organization.id) and not force:
        raise SolverFixtureSafetyError(
            "Refusing to write into an organization that has plan versions without --force"
        )


def _resolve_organization(
    db: Session,
    *,
    profile: SolverProfile,
    rng_seed: int,
    organization_id: int | None,
    force: bool,
) -> Organization:
    if organization_id is not None:
        organization = db.get(Organization, organization_id)
        if organization is None:
            raise SolverFixtureError(f"Organization {organization_id} not found")
        _assert_safe_target(db, organization, force=force)
        return organization
    slug = f"solver-fixture-{profile}-{rng_seed}"
    existing = get_organization_by_slug(db, slug)
    if existing is not None:
        raise SolverFixtureSafetyError(
            f"Organization slug {slug!r} already exists; pass --organization-id and --force to reuse"
        )
    organization = create_organization_record(
        db,
        name=f"Solver fixture {profile} {rng_seed}",
        slug=slug,
    )
    db.commit()
    db.refresh(organization)
    return organization


def _create_contract_group(db: Session, organization_id: int, *, name: str = "TdL 42h"):
    return create_contract_group(
        db,
        ContractGroupCreate(
            name=name,
            weekly_hours_at_100=Decimal("42"),
            vacation_days_at_100=Decimal("30"),
            regular_week_pattern=[
                RegularWeekPatternDay.model_validate(item) for item in default_regular_week_pattern()
            ],
            category_rules=[
                ContractCategoryRule.model_validate(item)
                for item in _tv_aerzte_category_rules(credit_factor="0.60")
            ],
            status_mappings=[
                ContractStatusMapping.model_validate(item) for item in default_status_mappings()
            ],
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )


def _create_templates(db: Session, organization_id: int) -> dict[str, ShiftTemplate]:
    specs = (
        ("bd24", "Bereitschaft 24h", "bereitschaftsdienst"),
        ("spaet", "Spaetdienst", "spaetdienst"),
        ("ruf", "Rufdienst", "rufdienst"),
    )
    templates: dict[str, ShiftTemplate] = {}
    for index, (code, name, category) in enumerate(specs):
        templates[code] = create_shift_template(
            db,
            ShiftTemplateCreate(code=code, name=name, category=category, display_order=index),
            organization_id=organization_id,
            actor=ACTOR,
            source=SOURCE,
        )
    overnight = time(8, 0)
    create_shift_variant(
        db,
        templates["bd24"].id,
        ShiftVariantCreate(
            label="weekday",
            start_weekdays=["mon", "tue", "wed", "thu"],
            include_holidays=False,
            starts_at=overnight,
            ends_at=overnight,
            end_day_offset=1,
            required_count=1,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    create_shift_variant(
        db,
        templates["bd24"].id,
        ShiftVariantCreate(
            label="weekend",
            start_weekdays=["fri", "sat", "sun"],
            include_holidays=False,
            starts_at=overnight,
            ends_at=overnight,
            end_day_offset=1,
            required_count=1,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    create_shift_variant(
        db,
        templates["bd24"].id,
        ShiftVariantCreate(
            label="holiday",
            start_day_class="holiday",
            include_holidays=True,
            starts_at=overnight,
            ends_at=overnight,
            end_day_offset=1,
            required_count=1,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    create_shift_variant(
        db,
        templates["spaet"].id,
        ShiftVariantCreate(
            label="weekday",
            start_weekdays=["mon", "tue", "wed", "thu", "fri"],
            include_holidays=False,
            starts_at=time(14, 0),
            ends_at=time(22, 0),
            end_day_offset=0,
            required_count=2,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    create_shift_variant(
        db,
        templates["ruf"].id,
        ShiftVariantCreate(
            label="weekend",
            start_weekdays=["sat", "sun"],
            include_holidays=True,
            starts_at=overnight,
            ends_at=overnight,
            end_day_offset=1,
            required_count=1,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    return templates


def _add_frueh_template(db: Session, organization_id: int) -> ShiftTemplate:
    template = create_shift_template(
        db,
        ShiftTemplateCreate(code="frueh", name="Fruehdienst", category="other", display_order=3),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    create_shift_variant(
        db,
        template.id,
        ShiftVariantCreate(
            label="daily",
            start_day_class="any",
            include_holidays=True,
            starts_at=time(9, 0),
            ends_at=time(17, 0),
            end_day_offset=0,
            required_count=1,
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    return template


def _apply_infeasible_bd24_constraint(
    db: Session,
    *,
    organization_id: int,
    bd24: ShiftTemplate,
    facharzt_id: int,
) -> None:
    update_shift_template(
        db,
        bd24.id,
        ShiftTemplateUpdate(
            constraints=[
                ShiftConstraint(
                    type="team_member_property_requirement",
                    severity="error",
                    property_requirement=TeamMemberPropertyRequirementAtom(
                        kind="atom",
                        property_definition_id=facharzt_id,
                        op="eq",
                        value="ja",
                    ),
                )
            ]
        ),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )


def _intervals_overlap(
    left: tuple[object, object],
    right: tuple[object, object],
) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _error_property_requirement(template: ShiftTemplate | None):
    if template is None:
        return None
    for raw in template.constraints or []:
        rule = ShiftConstraint.model_validate(raw)
        if rule.type == "team_member_property_requirement" and rule.severity == "error":
            return rule.property_requirement
    return None


def eligible_member_ids_for_slot(
    db: Session,
    slot: RosterSlot,
    *,
    organization_id: int,
    member_ids: list[int] | None = None,
) -> list[int]:
    members = list_team_members(db, organization_id=organization_id, active_only=True)
    if member_ids is not None:
        allowed = set(member_ids)
        members = [row for row in members if row.id in allowed]
    members = sorted(members, key=lambda row: row.id)
    group_ids = (
        shift_group_ids_for_template(db, slot.shift_template_id)
        if slot.shift_template_id is not None
        else set()
    )
    roster_ids: set[int] = set()
    for group_id in sorted(group_ids):
        roster_ids |= team_member_ids_for_period_shift_group(
            db, planning_period_id=slot.planning_period_id, shift_group_id=group_id
        )
    no_go_pairs = {
        (row.team_member_id, row.shift_template_id)
        for row in list_planning_shift_intents(db, planning_period_id=slot.planning_period_id)
        if row.kind == "no_go" and row.cell_date == slot.slot_date
    }
    blocking_by_member: dict[int, set[date]] = {}
    for cell in list_planning_cells(db, planning_period_id=slot.planning_period_id):
        if not cell_status_blocks_roster_assignment(
            db, organization_id=organization_id, status=cell.status
        ):
            continue
        blocking_by_member.setdefault(cell.team_member_id, set()).add(cell.cell_date)
    overlap_days = set(overlap_calendar_days(db, slot))
    definitions = {
        row.id: row
        for row in list_team_member_property_definitions(db, organization_id=organization_id)
    }
    values = property_value_maps_for_members(
        db,
        organization_id=organization_id,
        team_member_ids={row.id for row in members},
    )
    requirement = _error_property_requirement(slot.shift_template)
    eligible: list[int] = []
    for member in members:
        if not team_member_may_cover_template(
            db, team_member_id=member.id, shift_template_id=slot.shift_template_id
        ):
            continue
        if group_ids and member.id not in roster_ids:
            continue
        if (member.id, slot.shift_template_id) in no_go_pairs:
            continue
        if blocking_by_member.get(member.id, set()) & overlap_days:
            continue
        if requirement is not None and not evaluate_property_requirement_expr(
            requirement, values.get(member.id, {}), definitions
        ):
            continue
        eligible.append(member.id)
    return eligible


def _dst_fallback_overflow(slot: RosterSlot) -> bool:
    starts_at = slot.starts_at
    ends_at = slot.ends_at
    if starts_at is None or ends_at is None:
        return False
    return ends_at - starts_at > timedelta(hours=24)


def greedy_assign_period(
    db: Session,
    *,
    planning_period_id: int,
    organization_id: int,
    rng: random.Random | None = None,
    require_full: bool = True,
    bypass_preflight: bool = False,
    candidate_member_ids: list[int] | None = None,
) -> list[RosterSlotAssignment]:
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    slots = sorted(
        slots,
        key=lambda slot: (
            slot.slot_date,
            slot.shift_template.code if slot.shift_template is not None else "",
            slot.position,
            slot.id,
        ),
    )
    members = sorted(
        list_team_members(db, organization_id=organization_id, active_only=True),
        key=lambda row: row.id,
    )
    if candidate_member_ids is not None:
        allowed = set(candidate_member_ids)
        members = [row for row in members if row.id in allowed]
    weights = {member.id: 1.0 for member in members}
    if rng is not None:
        for member in members:
            weights[member.id] = 1.0 + rng.random() * 9.0
    assigned_counts = {member.id: 0 for member in members}
    occupied: dict[int, list[tuple[object, object]]] = {member.id: [] for member in members}
    statutory_kinds = {"bereitschaftsdienst", "spaetdienst"}
    got_statutory = {member.id: False for member in members}

    def try_assign(slot: RosterSlot, candidate_ids: list[int]) -> RosterSlotAssignment | None:
        interval = resolve_slot_interval(db, slot)
        ordered = sorted(
            candidate_ids,
            key=lambda member_id: (-weights[member_id], assigned_counts[member_id], member_id),
        )
        free: list[int] = []
        busy: list[int] = []
        for member_id in ordered:
            if interval is not None and any(
                _intervals_overlap(interval, existing) for existing in occupied[member_id]
            ):
                busy.append(member_id)
                continue
            free.append(member_id)
        for member_id in free + busy:
            try:
                if bypass_preflight:
                    assignment = _assign_slot_without_preflight(
                        db, slot=slot, team_member_id=member_id
                    )
                else:
                    assignment = upsert_roster_slot_assignment(
                        db,
                        RosterSlotAssignmentUpsert(
                            roster_slot_id=slot.id,
                            team_member_id=member_id,
                        ),
                        organization_id=organization_id,
                        actor=ACTOR,
                        source=SOURCE,
                    )
            except ValueError:
                continue
            assigned_counts[member_id] += 1
            if interval is not None:
                occupied[member_id].append(interval)
            category = slot.shift_template.category if slot.shift_template is not None else ""
            if category in statutory_kinds:
                got_statutory[member_id] = True
            return assignment
        return None

    assignments: list[RosterSlotAssignment] = []
    remaining = list(slots)
    if rng is not None:
        seed_slots = [
            slot
            for slot in remaining
            if slot.shift_template is not None and slot.shift_template.category in statutory_kinds
        ]
        for member in members:
            if got_statutory[member.id]:
                continue
            for slot in seed_slots:
                if any(row.roster_slot_id == slot.id for row in assignments):
                    continue
                if member.id not in eligible_member_ids_for_slot(
                    db,
                    slot,
                    organization_id=organization_id,
                    member_ids=candidate_member_ids,
                ):
                    continue
                filled = try_assign(slot, [member.id])
                if filled is None:
                    continue
                assignments.append(filled)
                break

    assigned_slot_ids = {row.roster_slot_id for row in assignments}
    for slot in remaining:
        if slot.id in assigned_slot_ids:
            continue
        eligible = eligible_member_ids_for_slot(
            db,
            slot,
            organization_id=organization_id,
            member_ids=candidate_member_ids,
        )
        filled = try_assign(slot, eligible)
        if filled is None:
            if require_full and not _dst_fallback_overflow(slot):
                code = slot.shift_template.code if slot.shift_template is not None else "?"
                raise SolverFixtureError(
                    f"Could not assign slot {slot.id} ({code} {slot.slot_date} #{slot.position})"
                )
            continue
        assignments.append(filled)
        assigned_slot_ids.add(slot.id)
    return assignments


def _fill_and_publish_history_month(
    db: Session,
    *,
    organization_id: int,
    year: int,
    month: int,
    rng: random.Random,
    shift_group_ids: list[int],
    bypass_preflight: bool = False,
    candidate_member_ids: list[int] | None = None,
    boundary_bd24_member_id: int | None = None,
) -> int:
    period = create_planning_period(
        db,
        PlanningPeriodCreate(year=year, month=month),
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    sync_roster_slots_for_period(
        db,
        period.id,
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    greedy_assign_period(
        db,
        planning_period_id=period.id,
        organization_id=organization_id,
        rng=rng,
        require_full=True,
        bypass_preflight=bypass_preflight,
        candidate_member_ids=candidate_member_ids,
    )
    if boundary_bd24_member_id is not None:
        last_day = _month_bounds(year, month)[1]
        slot = _first_slot_on_date(db, period.id, template_code="bd24", slot_date=last_day)
        _assign_slot_without_preflight(db, slot=slot, team_member_id=boundary_bd24_member_id)
    start, end = _month_bounds(year, month)
    derive_entries(db, organization_id=organization_id, start_date=start, end_date=end)
    for group_id in shift_group_ids:
        set_shift_group_planning_to_preliminary(
            db,
            period.id,
            shift_group_id=group_id,
            organization_id=organization_id,
            actor=ACTOR,
            source=SOURCE,
        )
        publish_shift_group_planning(
            db,
            period.id,
            shift_group_id=group_id,
            organization_id=organization_id,
            actor=ACTOR,
            source=SOURCE,
        )
    return period.id


def _member_group_map(memberships: dict[int, list[int]]) -> dict[int, list[int]]:
    return {member_id: sorted(group_ids) for member_id, group_ids in memberships.items()}


def _write_target_month(
    db: Session,
    *,
    organization_id: int,
    period_id: int,
    rng: random.Random,
    spec: _ProfileSpec,
    profile: SolverProfile,
    templates: dict[str, ShiftTemplate],
    memberships: dict[int, list[int]],
    members: list[TeamMember],
    facharzt_ids: set[int],
    reserved_keys: set[tuple[int, date]] | None = None,
) -> None:
    sync_roster_slots_for_period(
        db,
        period_id,
        organization_id=organization_id,
        actor=ACTOR,
        source=SOURCE,
    )
    period = db.get(PlanningPeriod, period_id)
    if period is None:
        raise SolverFixtureError("Target planning period not found")
    days = _month_days(period.year, period.month)
    member_ids = [row.id for row in sorted(members, key=lambda item: item.id)]
    reserved = reserved_keys or set()
    member_days = [(member_id, day) for member_id in member_ids for day in days]
    status_pool = [key for key in member_days if key not in reserved]
    status_keys = _sample_keys(rng, status_pool, DAY_STATUS_DENSITY)
    status_by_key: dict[tuple[int, date], str] = {}
    for key in status_keys:
        status_by_key[key] = rng.choice(list(DAY_STATUS_CODES))
    leave_ids: set[int] = set()
    if spec.leave_count:
        leave_ids = set(rng.sample(member_ids, spec.leave_count))
        for member_id in sorted(leave_ids):
            for day in days:
                key = (member_id, day)
                if key in reserved:
                    continue
                status_by_key[key] = "urlaub"
    group_map = _member_group_map(memberships)
    for group_id in sorted({gid for groups in group_map.values() for gid in groups}):
        cells = [
            PlanningCellUpsert(team_member_id=member_id, cell_date=day, status=status)
            for (member_id, day), status in sorted(status_by_key.items())
            if group_id in group_map.get(member_id, [])
        ]
        if cells:
            bulk_upsert_planning_cells(
                db,
                period_id,
                PlanningCellBulkUpsert(cells=cells),
                organization_id=organization_id,
                shift_group_id=group_id,
                actor=ACTOR,
                source=SOURCE,
            )
    remaining = [key for key in member_days if key not in status_by_key and key not in reserved]
    no_go_keys = _sample_keys(rng, remaining, spec.no_go_density)
    no_go_set = set(no_go_keys)
    wish_pool = [key for key in remaining if key not in no_go_set]
    wish_keys = _sample_keys(rng, wish_pool, WISH_DENSITY)
    template_codes = ["bd24", "spaet", "ruf"]
    if "frueh" in templates:
        template_codes.append("frueh")
    template_ids = [templates[code].id for code in template_codes]
    intents: list[PlanningShiftIntentUpsert] = []
    for member_id, day in no_go_keys:
        template_id = rng.choice(template_ids)
        group_id = _intent_group_id(group_map, member_id)
        if group_id is None:
            continue
        intents.append(
            PlanningShiftIntentUpsert(
                team_member_id=member_id,
                cell_date=day,
                shift_group_id=group_id,
                shift_template_id=template_id,
                kind="no_go",
            )
        )
    for member_id, day in wish_keys:
        template_id = rng.choice(template_ids)
        group_id = _intent_group_id(group_map, member_id)
        if group_id is None:
            continue
        intents.append(
            PlanningShiftIntentUpsert(
                team_member_id=member_id,
                cell_date=day,
                shift_group_id=group_id,
                shift_template_id=template_id,
                kind="wish",
            )
        )
    if profile == "infeasible":
        bd24_slots = [
            slot
            for slot in list_roster_slots(db, planning_period_id=period_id)
            if slot.shift_template is not None and slot.shift_template.code == "bd24"
        ]
        bd24_slots = sorted(bd24_slots, key=lambda slot: (slot.slot_date, slot.position, slot.id))
        if bd24_slots and facharzt_ids:
            blocked_date = bd24_slots[0].slot_date
            for member_id in sorted(facharzt_ids):
                member_group = _intent_group_id(group_map, member_id)
                if member_group is None:
                    continue
                intents.append(
                    PlanningShiftIntentUpsert(
                        team_member_id=member_id,
                        cell_date=blocked_date,
                        shift_group_id=member_group,
                        shift_template_id=templates["bd24"].id,
                        kind="no_go",
                    )
                )
    if intents:
        bulk_upsert_planning_shift_intents(
            db,
            period_id,
            PlanningShiftIntentBulkUpsert(intents=intents),
            organization_id=organization_id,
            actor=ACTOR,
            source=SOURCE,
        )


def _sample_keys(
    rng: random.Random,
    keys: list[tuple[int, date]],
    density: float,
) -> list[tuple[int, date]]:
    count = _sample_count(len(keys), density)
    if count == 0:
        return []
    return rng.sample(keys, count)


def _intent_group_id(group_map: dict[int, list[int]], member_id: int) -> int | None:
    groups = group_map.get(member_id, [])
    return groups[0] if groups else None


def _plant_arbzg_target_assignments(
    db: Session,
    *,
    target_period_id: int,
    roles: _ArbzgRoles,
    dates: _ArbzgDates,
) -> None:
    follow = _first_slot_on_date(
        db, target_period_id, template_code="frueh", slot_date=dates.boundary_next
    )
    _assign_slot_without_preflight(db, slot=follow, team_member_id=roles.rest_id)
    within_duty = _first_slot_on_date(
        db, target_period_id, template_code="bd24", slot_date=dates.within_duty
    )
    within_follow = _first_slot_on_date(
        db, target_period_id, template_code="frueh", slot_date=dates.within_follow
    )
    _assign_slot_without_preflight(db, slot=within_duty, team_member_id=roles.rest_id)
    _assign_slot_without_preflight(db, slot=within_follow, team_member_id=roles.rest_id)
    documentation = _first_slot_on_date(
        db, target_period_id, template_code="bd24", slot_date=dates.documentation
    )
    _assign_slot_without_preflight(db, slot=documentation, team_member_id=roles.documentation_id)
    db.commit()


def _top_up_arbzg_weekly_averages(
    db: Session,
    *,
    organization_id: int,
    year: int,
    month: int,
    roles: _ArbzgRoles,
) -> None:
    end_date = _month_bounds(year, month)[1]
    period_start = _subtract_months(end_date, ARBZG_REFERENCE_MONTHS)
    days = (end_date - period_start).days + 1
    cap_minutes = ARBZG_WEEKLY_CAP_HOURS * 60
    targets = (
        (roles.over_id, cap_minutes + 1),
        (roles.under_id, cap_minutes),
    )
    for member_id, target_average in targets:
        current = _sum_statutory_minutes(
            db,
            organization_id=organization_id,
            member_id=member_id,
            start_date=period_start,
            end_date=end_date,
        )
        desired = _minutes_for_weekly_average(days, target_average)
        needed = desired - current
        if needed < 0:
            raise SolverFixtureError(
                f"Team member {member_id} already has {current} statutory minutes; "
                f"cannot top up to weekly average {target_average}"
            )
        if needed == 0:
            continue
        create_manual_entry(
            db,
            TimeEntryCreate(
                team_member_id=member_id,
                entry_date=period_start,
                kind="work",
                all_day=True,
                duration_minutes=needed,
                statutory_minutes=needed,
                credited_minutes=needed,
            ),
            organization_id=organization_id,
            actor=ACTOR,
            source=SOURCE,
        )


def fixture_digest(db: Session, organization_id: int) -> str:
    members = sorted(
        list_team_members(db, organization_id=organization_id, active_only=False),
        key=lambda row: row.email,
    )
    email_by_id = {row.id: row.email for row in members}
    groups = sorted(list_shift_groups(db, organization_id=organization_id), key=lambda row: row.code)
    templates = sorted(
        list_shift_templates(db, organization_id=organization_id),
        key=lambda row: row.code,
    )
    definitions = sorted(
        list_team_member_property_definitions(db, organization_id=organization_id),
        key=lambda row: row.name,
    )
    periods = list(
        db.scalars(
            select(PlanningPeriod)
            .where(PlanningPeriod.organization_id == organization_id)
            .order_by(PlanningPeriod.year, PlanningPeriod.month, PlanningPeriod.id)
        )
    )
    member_rows = []
    for member in members:
        periods_emp = list_employment_periods(db, member.id, organization_id=organization_id)
        consents = list_work_time_consents(db, member.id, organization_id=organization_id)
        values = property_value_maps_for_members(
            db, organization_id=organization_id, team_member_ids={member.id}
        ).get(member.id, {})
        named_values = {
            definition.name: values.get(definition.id)
            for definition in definitions
            if definition.id in values
        }
        member_rows.append(
            {
                "email": member.email,
                "first_name": member.first_name,
                "last_name": member.last_name,
                "employment": [
                    {
                        "percentage": row.employment_percentage,
                        "start": row.start_date.isoformat(),
                        "end": row.end_date.isoformat() if row.end_date else None,
                    }
                    for row in periods_emp
                ],
                "properties": named_values,
                "consents": [
                    {"tier": row.tier, "valid_from": row.valid_from.isoformat()}
                    for row in sorted(consents, key=lambda item: (item.valid_from, item.tier))
                ],
            }
        )
    group_rows = []
    for group in groups:
        member_emails = sorted(
            email_by_id[link.team_member_id]
            for link in group.team_member_links
            if link.team_member_id in email_by_id
        )
        template_codes = sorted(
            next(template.code for template in templates if template.id == link.shift_template_id)
            for link in group.template_links
        )
        group_rows.append({"code": group.code, "members": member_emails, "templates": template_codes})
    template_rows = []
    for template in templates:
        variants = sorted(template.variants, key=lambda row: row.label)
        template_rows.append(
            {
                "code": template.code,
                "category": template.category,
                "constraints": template.constraints or [],
                "variants": [
                    {
                        "label": variant.label,
                        "start_weekdays": variant.start_weekdays,
                        "start_day_class": variant.start_day_class,
                        "include_holidays": variant.include_holidays,
                        "starts_at": variant.starts_at.isoformat(),
                        "ends_at": variant.ends_at.isoformat(),
                        "end_day_offset": variant.end_day_offset,
                        "required_count": variant.required_count,
                    }
                    for variant in variants
                ],
            }
        )
    period_rows = []
    for period in periods:
        cells = [
            {
                "member": email_by_id.get(cell.team_member_id),
                "date": cell.cell_date.isoformat(),
                "group_id": cell.shift_group_id,
                "status": cell.status,
            }
            for cell in list_planning_cells(db, planning_period_id=period.id)
        ]
        intents = [
            {
                "member": email_by_id.get(intent.team_member_id),
                "date": intent.cell_date.isoformat(),
                "template_id": intent.shift_template_id,
                "kind": intent.kind,
            }
            for intent in list_planning_shift_intents(db, planning_period_id=period.id)
        ]
        slots = [
            {
                "date": slot.slot_date.isoformat(),
                "template": slot.shift_template.code if slot.shift_template is not None else None,
                "position": slot.position,
            }
            for slot in list_roster_slots(db, planning_period_id=period.id)
        ]
        assignments = [
            {
                "date": assignment.roster_slot.slot_date.isoformat()
                if assignment.roster_slot is not None
                else None,
                "template": assignment.roster_slot.shift_template.code
                if assignment.roster_slot is not None and assignment.roster_slot.shift_template is not None
                else None,
                "position": assignment.roster_slot.position if assignment.roster_slot is not None else None,
                "member": email_by_id.get(assignment.team_member_id),
            }
            for assignment in list_roster_slot_assignments(db, planning_period_id=period.id)
        ]
        period_rows.append(
            {
                "year": period.year,
                "month": period.month,
                "status": period.status,
                "cells": sorted(cells, key=lambda row: (row["date"], row["member"] or "", row["status"])),
                "intents": sorted(
                    intents,
                    key=lambda row: (row["date"], row["member"] or "", row["kind"], row["template_id"]),
                ),
                "slots": sorted(slots, key=lambda row: (row["date"], row["template"] or "", row["position"])),
                "assignments": sorted(
                    assignments,
                    key=lambda row: (
                        row["date"] or "",
                        row["template"] or "",
                        row["position"] or 0,
                        row["member"] or "",
                    ),
                ),
            }
        )
    entries = list(
        db.scalars(
            select(TimeEntry)
            .where(TimeEntry.organization_id == organization_id)
            .order_by(TimeEntry.entry_date, TimeEntry.team_member_id, TimeEntry.kind, TimeEntry.id)
        )
    )
    entry_rows = [
        {
            "member": email_by_id.get(row.team_member_id),
            "date": row.entry_date.isoformat(),
            "kind": row.kind,
            "source": row.source,
            "statutory_minutes": row.statutory_minutes,
            "credited_minutes": row.credited_minutes,
        }
        for row in entries
    ]
    payload = {
        "members": member_rows,
        "groups": group_rows,
        "templates": template_rows,
        "periods": period_rows,
        "time_entries": entry_rows,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def seed_solver_fixture(
    db: Session,
    *,
    profile: SolverProfile,
    rng_seed: int = 1,
    history_months: int = 6,
    year: int | None = None,
    month: int | None = None,
    organization_id: int | None = None,
    force: bool = False,
) -> SolverFixtureResult:
    if profile not in _PROFILE_SPECS:
        raise SolverFixtureError(f"Unknown profile: {profile}")
    if history_months < 0:
        raise SolverFixtureError("history_months must be >= 0")
    if year is None or month is None:
        year, month = default_target_year_month()
    if profile == "arbzg" and history_months < 1:
        raise SolverFixtureError("arbzg profile requires history_months >= 1")
    spec = _PROFILE_SPECS[profile]
    rng = random.Random(rng_seed)
    organization = _resolve_organization(
        db,
        profile=profile,
        rng_seed=rng_seed,
        organization_id=organization_id,
        force=force,
    )
    ensure_work_time_presets(db)
    preset_code = PRESET_CODE_ARBZG if profile == "arbzg" else PRESET_CODE_TDL
    adopted = adopt_work_time_rule_set_preset(
        db,
        preset_code,
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
        is_active=True,
    )
    if adopted is None:
        preset_name = "ArbZG-Grundmodell" if profile == "arbzg" else "TV-Ärzte (TdL)"
        raise SolverFixtureError(f"{preset_name} preset is not available")
    contract_name = "ArbZG 42h" if profile == "arbzg" else "TdL 42h"
    contract = _create_contract_group(db, organization.id, name=contract_name)
    anaesthesie = create_shift_group(
        db,
        ShiftGroupCreate(code="anaesthesie", name="Anaesthesie", display_order=0),
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    intensiv = create_shift_group(
        db,
        ShiftGroupCreate(code="intensiv", name="Intensiv", display_order=1),
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    templates = _create_templates(db, organization.id)
    template_ids = [templates[code].id for code in ("bd24", "spaet", "ruf")]
    for group in (anaesthesie, intensiv):
        replace_group_shift_templates(
            db,
            group.id,
            template_ids,
            organization_id=organization.id,
            actor=ACTOR,
            source=SOURCE,
        )
    facharzt = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(
            name="facharzt",
            type="select",
            options=["ja", "nein"],
            editable_by_team_member=False,
            display_order=0,
        ),
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    sonografie = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(
            name="sonografie_zertifikat",
            type="select",
            options=["ja", "nein"],
            editable_by_team_member=False,
            display_order=1,
        ),
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    percentages = _employment_percentages(spec.member_count)
    group_flags = _group_assignments(spec.member_count)
    members: list[TeamMember] = []
    for index in range(spec.member_count):
        member = create_team_member(
            db,
            TeamMemberCreate(
                first_name=f"M{index + 1:02d}",
                last_name="Fixture",
                email=f"solver-m{index + 1:02d}@example.com",
                employment_percentage=percentages[index],
            ),
            organization_id=organization.id,
            actor=ACTOR,
            source=SOURCE,
            transactional=False,
        )
        replace_employment_periods(
            db,
            member.id,
            [
                EmploymentPeriodWrite(
                    contract_group_id=contract.id,
                    employment_percentage=percentages[index],
                    start_date=OPEN_ENDED_EMPLOYMENT_START,
                    end_date=None,
                )
            ],
            organization_id=organization.id,
            actor=ACTOR,
            source=SOURCE,
        )
        members.append(member)
    members = sorted(members, key=lambda row: row.id)
    member_ids = [row.id for row in members]
    facharzt_count = spec.facharzt_ja_count if spec.facharzt_ja_count is not None else round(
        spec.member_count * 0.50
    )
    sono_count = round(spec.member_count * 0.30)
    facharzt_yes = set(rng.sample(member_ids, facharzt_count))
    sono_yes = set(rng.sample(member_ids, sono_count))
    history_start_year, history_start_month = _shift_month(year, month, -max(history_months, 1))
    consent_from, _ = _month_bounds(history_start_year, history_start_month)
    for member in members:
        replace_team_member_property_values(
            db,
            team_member_id=member.id,
            organization_id=organization.id,
            payload=TeamMemberPropertyValuesReplace(
                values=[
                    TeamMemberPropertyValueUpsertItem(
                        property_definition_id=facharzt.id,
                        value="ja" if member.id in facharzt_yes else "nein",
                    ),
                    TeamMemberPropertyValueUpsertItem(
                        property_definition_id=sonografie.id,
                        value="ja" if member.id in sono_yes else "nein",
                    ),
                ]
            ),
            actor=ACTOR,
            source=SOURCE,
        )
    if profile != "arbzg":
        consent_count = round(spec.member_count * 0.60)
        consent_ids = rng.sample(member_ids, consent_count)
        for index, member_id in enumerate(sorted(consent_ids)):
            record_work_time_consent(
                db,
                member_id,
                WorkTimeConsentCreate(
                    consent_type="opt_out",
                    tier="stufe_i" if index % 2 == 0 else "stufe_ii",
                    valid_from=consent_from,
                ),
                organization_id=organization.id,
                recorded_by_user_id=None,
                actor=ACTOR,
                source=SOURCE,
            )
    memberships: dict[int, list[int]] = {member.id: [] for member in members}
    ana_memberships: list[ShiftGroupMembershipWrite] = []
    intensiv_memberships: list[ShiftGroupMembershipWrite] = []
    for member, flags in zip(members, group_flags, strict=True):
        in_ana, in_intensiv = flags
        if in_ana:
            memberships[member.id].append(anaesthesie.id)
            ana_memberships.append(
                ShiftGroupMembershipWrite(
                    team_member_id=member.id,
                    start_date=OPEN_ENDED_EMPLOYMENT_START,
                    end_date=None,
                )
            )
        if in_intensiv:
            memberships[member.id].append(intensiv.id)
            intensiv_memberships.append(
                ShiftGroupMembershipWrite(
                    team_member_id=member.id,
                    start_date=OPEN_ENDED_EMPLOYMENT_START,
                    end_date=None,
                )
            )
    replace_group_team_member_memberships(
        db,
        anaesthesie.id,
        ana_memberships,
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    replace_group_team_member_memberships(
        db,
        intensiv.id,
        intensiv_memberships,
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    shift_group_ids = [anaesthesie.id, intensiv.id]
    arbzg_roles = _arbzg_roles(members) if profile == "arbzg" else None
    arbzg_dates = _arbzg_dates(year, month) if profile == "arbzg" else None
    reserved_member_ids: list[int] | None = None
    if arbzg_roles is not None:
        reserved_member_ids = [
            arbzg_roles.rest_id,
            arbzg_roles.over_id,
            arbzg_roles.under_id,
            arbzg_roles.documentation_id,
        ]
    history_candidates = (
        [member_id for member_id in member_ids if member_id not in set(reserved_member_ids)]
        if reserved_member_ids is not None
        else None
    )
    history_period_ids: list[int] = []
    for offset in range(history_months, 0, -1):
        history_year, history_month = _shift_month(year, month, -offset)
        boundary_member_id = None
        if arbzg_roles is not None and offset == 1:
            boundary_member_id = arbzg_roles.rest_id
        history_period_ids.append(
            _fill_and_publish_history_month(
                db,
                organization_id=organization.id,
                year=history_year,
                month=history_month,
                rng=rng,
                shift_group_ids=shift_group_ids,
                bypass_preflight=profile == "arbzg",
                candidate_member_ids=history_candidates,
                boundary_bd24_member_id=boundary_member_id,
            )
        )
    if profile == "infeasible":
        _apply_infeasible_bd24_constraint(
            db,
            organization_id=organization.id,
            bd24=templates["bd24"],
            facharzt_id=facharzt.id,
        )
        templates["bd24"] = db.get(ShiftTemplate, templates["bd24"].id) or templates["bd24"]
    if profile == "arbzg":
        templates["frueh"] = _add_frueh_template(db, organization.id)
        template_ids = [templates[code].id for code in ("bd24", "spaet", "ruf", "frueh")]
        for group in (anaesthesie, intensiv):
            replace_group_shift_templates(
                db,
                group.id,
                template_ids,
                organization_id=organization.id,
                actor=ACTOR,
                source=SOURCE,
            )
    target = create_planning_period(
        db,
        PlanningPeriodCreate(year=year, month=month),
        organization_id=organization.id,
        actor=ACTOR,
        source=SOURCE,
    )
    reserved_keys = (
        _arbzg_reserved_keys(arbzg_roles, arbzg_dates)
        if arbzg_roles is not None and arbzg_dates is not None
        else None
    )
    _write_target_month(
        db,
        organization_id=organization.id,
        period_id=target.id,
        rng=rng,
        spec=spec,
        profile=profile,
        templates=templates,
        memberships=memberships,
        members=members,
        facharzt_ids=facharzt_yes,
        reserved_keys=reserved_keys,
    )
    if arbzg_roles is not None and arbzg_dates is not None:
        _plant_arbzg_target_assignments(
            db,
            target_period_id=target.id,
            roles=arbzg_roles,
            dates=arbzg_dates,
        )
        _top_up_arbzg_weekly_averages(
            db,
            organization_id=organization.id,
            year=year,
            month=month,
            roles=arbzg_roles,
        )
    return SolverFixtureResult(
        organization_id=organization.id,
        organization_slug=organization.slug,
        profile=profile,
        rng_seed=rng_seed,
        year=year,
        month=month,
        history_months=history_months,
        target_period_id=target.id,
        history_period_ids=tuple(history_period_ids),
        member_ids=tuple(member_ids),
        shift_group_ids=tuple(shift_group_ids),
    )
