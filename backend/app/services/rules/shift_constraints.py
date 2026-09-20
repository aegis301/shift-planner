from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftTemplate,
    ShiftVariant,
    TeamMemberPropertyDefinition,
)
from app.schemas import ShiftConstraint, ValidationWarning
from app.services.rules.builder import build_plan_state
from app.services.rules.state import (
    PlanState,
    frozen_mapping,
    index_assignments_by_member,
    index_slots_by_date,
)
from app.services.team_member_property_requirements import (
    collect_property_requirement_violations,
    evaluate_property_requirement_expr,
)

ConstraintSource = Literal["template", "variant"]


@dataclass(frozen=True)
class ResolvedConstraint:
    source: ConstraintSource
    rule: ShiftConstraint


def _normalize_constraint_list(raw: list | None) -> list[ShiftConstraint]:
    return [ShiftConstraint.model_validate(row) for row in raw or []]


def resolve_slot_constraints(db: Session, slot: RosterSlot) -> list[ResolvedConstraint]:
    template: ShiftTemplate | None = None
    variant: ShiftVariant | None = None
    if slot.shift_template is not None:
        template = slot.shift_template
    elif slot.shift_template_id is not None:
        template = db.get(ShiftTemplate, slot.shift_template_id)
    if slot.shift_variant is not None:
        variant = slot.shift_variant
    elif slot.shift_variant_id is not None:
        variant = db.get(ShiftVariant, slot.shift_variant_id)
    template_rules = _normalize_constraint_list(template.constraints if template is not None else [])
    variant_rules = _normalize_constraint_list(variant.constraints if variant is not None else [])
    return [ResolvedConstraint(source="template", rule=rule) for rule in template_rules] + [
        ResolvedConstraint(source="variant", rule=rule) for rule in variant_rules
    ]


def _team_slots_including_hypothetical(slot: RosterSlot, team_slots: list[RosterSlot]) -> list[RosterSlot]:
    out = list(team_slots)
    if not any(s.id == slot.id for s in out):
        out.append(slot)
    return out


def _base_details(
    *,
    slot: RosterSlot,
    source: ConstraintSource,
    constraint_type: str,
    constraint_severity: str,
) -> dict[str, object]:
    return {
        "constraint_type": constraint_type,
        "constraint_source": source,
        "constraint_severity": constraint_severity,
        "roster_slot_id": slot.id,
        "shift_template_id": slot.shift_template_id,
        "shift_variant_id": slot.shift_variant_id,
    }


def _member_slots(state: PlanState, team_member_id: int) -> list[RosterSlot]:
    return [
        row.roster_slot
        for row in state.assignments_by_member_id.get(team_member_id, ())
        if row.roster_slot is not None
    ]


def _variant_in_state(state: PlanState, variant_id: int) -> ShiftVariant | None:
    for slot in state.slots_by_id.values():
        if slot.shift_variant_id == variant_id and slot.shift_variant is not None:
            return slot.shift_variant
    return None


def evaluate_resolved_constraints(
    *,
    slot: RosterSlot,
    team_member_id: int,
    resolved_constraints: list[ResolvedConstraint],
    team_slots: list[RosterSlot],
    assignment_id: int | None,
    member_property_values: dict[int, object],
    defs_map: dict[int, TeamMemberPropertyDefinition],
    state: PlanState | None = None,
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    slot_month = (slot.slot_date.year, slot.slot_date.month)
    for resolved in resolved_constraints:
        rule = resolved.rule
        details = _base_details(
            slot=slot,
            source=resolved.source,
            constraint_type=rule.type,
            constraint_severity=rule.severity,
        )
        if assignment_id is not None:
            details["roster_slot_assignment_id"] = assignment_id
        if rule.type == "no_additional_same_day":
            same_day_slots = [
                other.id for other in team_slots if other.id != slot.id and other.slot_date == slot.slot_date
            ]
            if same_day_slots:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_SAME_DAY",
                        severity=rule.severity,
                        message="Constraint violation: no additional shift assignments allowed on this day.",
                        team_member_id=team_member_id,
                        date=slot.slot_date,
                        details={**details, "conflicting_roster_slot_ids": same_day_slots},
                    )
                )
            continue
        if rule.type == "min_rest_hours":
            if slot.starts_at is None or slot.ends_at is None or rule.min_rest_hours is None:
                continue
            min_required = float(rule.min_rest_hours)
            best_gap: float | None = None
            best_slot: RosterSlot | None = None
            best_direction = "overlap"
            for other in team_slots:
                if other.id == slot.id or other.starts_at is None or other.ends_at is None:
                    continue
                if other.ends_at <= slot.starts_at:
                    gap = (slot.starts_at - other.ends_at).total_seconds() / 3600
                    direction = "before"
                elif slot.ends_at <= other.starts_at:
                    gap = (other.starts_at - slot.ends_at).total_seconds() / 3600
                    direction = "after"
                else:
                    gap = -1.0
                    direction = "overlap"
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_slot = other
                    best_direction = direction
            if best_gap is not None and best_gap < min_required:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_MIN_REST_HOURS",
                        severity=rule.severity,
                        message="Constraint violation: minimum rest time between shifts is not met.",
                        team_member_id=team_member_id,
                        date=slot.slot_date,
                        details={
                            **details,
                            "required_rest_hours": min_required,
                            "actual_rest_hours": round(best_gap, 2),
                            "related_roster_slot_id": best_slot.id if best_slot is not None else None,
                            "direction": best_direction,
                        },
                    )
                )
            continue
        if rule.type == "unavailable_overlap_policy":
            continue
        if rule.type == "max_assignments_per_month":
            if rule.max_assignments_per_month is None:
                continue
            same_template_assignments = [
                other
                for other in team_slots
                if other.id != slot.id
                and other.shift_template_id == slot.shift_template_id
                and (other.slot_date.year, other.slot_date.month) == slot_month
            ]
            total = len(same_template_assignments) + 1
            if total > rule.max_assignments_per_month:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH",
                        severity=rule.severity,
                        message="Constraint violation: maximum assignments per month for this shift template exceeded.",
                        team_member_id=team_member_id,
                        date=slot.slot_date,
                        details={
                            **details,
                            "max_assignments_per_month": rule.max_assignments_per_month,
                            "actual_assignments_per_month": total,
                        },
                    )
                )
            continue
        if rule.type == "requires_coupled_shift":
            if rule.paired_shift_variant_id is None:
                continue
            paired_variant = _variant_in_state(state, rule.paired_shift_variant_id) if state is not None else None
            if paired_variant is None:
                continue
            partner_date = slot.slot_date + timedelta(days=rule.partner_day_offset)
            source_variant = slot.shift_variant
            source_rc = source_variant.required_count if source_variant is not None else 1
            partner_rc = paired_variant.required_count
            strict_position = not (source_rc == 1 and partner_rc == 1)
            slots_for_member = _team_slots_including_hypothetical(slot, team_slots)
            has_partner = False
            for other in slots_for_member:
                if other.id == slot.id:
                    continue
                if other.shift_variant_id != rule.paired_shift_variant_id:
                    continue
                if other.slot_date != partner_date:
                    continue
                if strict_position and other.position != slot.position:
                    continue
                has_partner = True
                break
            if not has_partner:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED",
                        severity=rule.severity,
                        message="Constraint violation: required coupled shift assignment is missing.",
                        team_member_id=team_member_id,
                        date=slot.slot_date,
                        details={
                            **details,
                            "paired_shift_variant_id": rule.paired_shift_variant_id,
                            "partner_date": partner_date.isoformat(),
                            "partner_day_offset": rule.partner_day_offset,
                        },
                    )
                )
            continue
        if rule.type == "team_member_property_requirement":
            if rule.property_requirement is None:
                continue
            ok = evaluate_property_requirement_expr(rule.property_requirement, member_property_values, defs_map)
            if not ok:
                prop_details = dict(details)
                prop_details["violations"] = collect_property_requirement_violations(
                    rule.property_requirement, member_property_values, defs_map
                )
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES",
                        severity=rule.severity,
                        message="Constraint violation: team member does not meet property requirements for this shift.",
                        team_member_id=team_member_id,
                        date=slot.slot_date,
                        details=prop_details,
                    )
                )
            continue
    return warnings


def overlay_candidate_assignment(
    state: PlanState,
    *,
    slot: RosterSlot,
    team_member_id: int,
    assignment_id: int | None,
    manual_override: bool = False,
) -> PlanState:
    slots_by_id = dict(state.slots_by_id)
    slots_by_id[slot.id] = slot
    existing = state.assignments_by_slot_id.get(slot.id)
    assignments = {row.id: row for row in state.assignments_by_id.values()}
    if existing is not None:
        if existing.team_member_id == team_member_id:
            if existing.roster_slot is None:
                existing.roster_slot = slot
            existing.manual_override = existing.manual_override or manual_override
            return replace(
                state,
                slots_by_id=frozen_mapping(slots_by_id),
                slots_by_date=index_slots_by_date(list(slots_by_id.values())),
            )
        assignments.pop(existing.id, None)
    new_id = assignment_id if assignment_id is not None else -slot.id
    row = RosterSlotAssignment(
        id=new_id,
        roster_slot_id=slot.id,
        team_member_id=team_member_id,
        manual_override=manual_override,
    )
    row.roster_slot = slot
    assignments[new_id] = row
    assignment_list = list(assignments.values())
    return replace(
        state,
        slots_by_id=frozen_mapping(slots_by_id),
        slots_by_date=index_slots_by_date(list(slots_by_id.values())),
        assignments_by_id=frozen_mapping(assignments),
        assignments_by_slot_id=frozen_mapping({item.roster_slot_id: item for item in assignment_list}),
        assignments_by_member_id=index_assignments_by_member(assignment_list),
    )


def evaluate_shift_constraints_for_slot(
    *,
    db: Session,
    slot: RosterSlot,
    team_member_id: int,
    resolved_constraints: list[ResolvedConstraint],
    assignment_id: int | None = None,
    member_property_values: dict[int, object],
) -> list[ValidationWarning]:
    if not resolved_constraints:
        return []
    period = slot.planning_period
    if period is None:
        period = db.get(PlanningPeriod, slot.planning_period_id)
    if period is None:
        return []
    state = build_plan_state(
        db,
        organization_id=period.organization_id,
        start_date=slot.slot_date,
        end_date=slot.slot_date,
    )
    state = overlay_candidate_assignment(
        state, slot=slot, team_member_id=team_member_id, assignment_id=assignment_id
    )
    defs_map = dict(state.property_definitions_by_id)
    team_slots = _member_slots(state, team_member_id)
    return evaluate_resolved_constraints(
        slot=slot,
        team_member_id=team_member_id,
        resolved_constraints=resolved_constraints,
        team_slots=team_slots,
        assignment_id=assignment_id,
        member_property_values=member_property_values,
        defs_map=defs_map,
        state=state,
    )


class NoAdditionalSameDayRule:
    code = "ROSTER_CONSTRAINT_SAME_DAY"
    severity = "warning"
    lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        return _evaluate_type_on_state(state, "no_additional_same_day")


class MinRestHoursRule:
    code = "ROSTER_CONSTRAINT_MIN_REST_HOURS"
    severity = "warning"
    lookback = timedelta(hours=48)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        return _evaluate_type_on_state(state, "min_rest_hours")


class UnavailableOverlapPolicyRule:
    code = "ROSTER_MATRIX_UNAVAILABLE_OVERLAP"
    severity = "error"
    lookback = timedelta(days=1)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        warnings: list[ValidationWarning] = []
        for assignment in state.assignments_by_id.values():
            slot = assignment.roster_slot
            if slot is None or not (state.start_date <= slot.slot_date <= state.end_date):
                continue
            resolved = resolve_slot_constraints_from_loaded(slot)
            policy = _resolve_unavailable_overlap_policy(resolved)
            if policy_mode_allow(policy):
                continue
            blocking = _blocking_cells_for_member(state, assignment.team_member_id)
            conflicts: list[dict[str, object]] = []
            for day in _overlap_days(slot):
                cell = blocking.get(day)
                if cell is None:
                    continue
                conflicts.append({"cell_date": day.isoformat(), "unavailable_status": cell.status})
            if not conflicts:
                continue
            severity = "error" if policy == "block" else "warning"
            first_day = date.fromisoformat(str(conflicts[0]["cell_date"]))
            details: dict[str, object] = {
                "roster_slot_id": slot.id,
                "shift_template_id": slot.shift_template_id,
                "shift_variant_id": slot.shift_variant_id,
                "overlap_days": [row["cell_date"] for row in conflicts],
                "conflicts": conflicts,
                "unavailable_overlap_policy": policy,
                "unavailable_status": conflicts[0]["unavailable_status"],
            }
            if assignment.id > 0:
                details["roster_slot_assignment_id"] = assignment.id
            warnings.append(
                ValidationWarning(
                    code="ROSTER_MATRIX_UNAVAILABLE_OVERLAP",
                    severity=severity,
                    message="Final roster assignment overlaps an unavailable wishes matrix status.",
                    team_member_id=assignment.team_member_id,
                    date=first_day,
                    details=details,
                )
            )
        return warnings


class MaxAssignmentsPerMonthRule:
    code = "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH"
    severity = "warning"
    lookback = timedelta(days=31)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        return _evaluate_type_on_state(state, "max_assignments_per_month")


class RequiresCoupledShiftRule:
    code = "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED"
    severity = "warning"
    lookback = timedelta(days=7)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        return _evaluate_type_on_state(state, "requires_coupled_shift")


class TeamMemberPropertyRequirementRule:
    code = "ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES"
    severity = "warning"
    lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        return _evaluate_type_on_state(state, "team_member_property_requirement")


def _overlap_days(slot: RosterSlot) -> list[date]:
    if slot.starts_at is None or slot.ends_at is None:
        return [slot.slot_date]
    out: list[date] = []
    day = slot.starts_at.date()
    last = slot.ends_at.date()
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def _blocking_cells_for_member(state: PlanState, team_member_id: int) -> dict[date, PlanningCell]:
    out: dict[date, PlanningCell] = {}
    for (member_id, day, _group), cell in state.cells_by_member_date_group.items():
        if member_id != team_member_id:
            continue
        definition = state.day_status_by_code.get(cell.status)
        if definition is None or not definition.blocks_roster_assignment:
            continue
        existing = out.get(day)
        if existing is None or cell.id > existing.id:
            out[day] = cell
    return out


def _resolve_unavailable_overlap_policy(resolved_constraints: list[ResolvedConstraint]) -> str:
    for resolved in resolved_constraints:
        if resolved.rule.type == "unavailable_overlap_policy":
            mode = resolved.rule.unavailable_overlap_mode or "inherit"
            if mode == "inherit":
                continue
            return mode
    for resolved in resolved_constraints:
        if resolved.rule.type == "no_cross_day_into_unavailable_day":
            if resolved.rule.severity == "error":
                return "block"
            if resolved.rule.severity == "warning":
                return "warn"
            return "allow"
    return "block"


def policy_mode_allow(policy: str) -> bool:
    return policy == "allow"


def resolve_slot_constraints_from_loaded(slot: RosterSlot) -> list[ResolvedConstraint]:
    template_rules = _normalize_constraint_list(
        slot.shift_template.constraints if slot.shift_template is not None else []
    )
    variant_rules = _normalize_constraint_list(
        slot.shift_variant.constraints if slot.shift_variant is not None else []
    )
    return [ResolvedConstraint(source="template", rule=rule) for rule in template_rules] + [
        ResolvedConstraint(source="variant", rule=rule) for rule in variant_rules
    ]


def _evaluate_type_on_state(state: PlanState, constraint_type: str) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    defs_map = dict(state.property_definitions_by_id)
    for assignment in state.assignments_by_id.values():
        slot = assignment.roster_slot
        if slot is None or not (state.start_date <= slot.slot_date <= state.end_date):
            continue
        resolved = [
            row for row in resolve_slot_constraints_from_loaded(slot) if row.rule.type == constraint_type
        ]
        if not resolved:
            continue
        assignment_id = assignment.id if assignment.id > 0 else None
        values = dict(state.property_values_by_member_id.get(assignment.team_member_id, {}))
        warnings.extend(
            evaluate_resolved_constraints(
                slot=slot,
                team_member_id=assignment.team_member_id,
                resolved_constraints=resolved,
                team_slots=_member_slots(state, assignment.team_member_id),
                assignment_id=assignment_id,
                member_property_values=values,
                defs_map=defs_map,
                state=state,
            )
        )
    return warnings


def shift_constraint_rules() -> tuple[
    NoAdditionalSameDayRule,
    MinRestHoursRule,
    UnavailableOverlapPolicyRule,
    MaxAssignmentsPerMonthRule,
    RequiresCoupledShiftRule,
    TeamMemberPropertyRequirementRule,
]:
    return (
        NoAdditionalSameDayRule(),
        MinRestHoursRule(),
        UnavailableOverlapPolicyRule(),
        MaxAssignmentsPerMonthRule(),
        RequiresCoupledShiftRule(),
        TeamMemberPropertyRequirementRule(),
    )
