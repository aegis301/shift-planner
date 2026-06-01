import calendar
from dataclasses import dataclass
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
from app.services.planning_day_status_definitions import cell_status_blocks_roster_assignment
from app.services.team_member_property_requirements import (
    collect_property_requirement_violations,
    evaluate_property_requirement_expr,
    load_property_definitions_map,
)

ConstraintSource = Literal["template", "variant"]


@dataclass(frozen=True)
class ResolvedConstraint:
    source: ConstraintSource
    rule: ShiftConstraint


def _normalize_constraint_list(raw: list | None) -> list[ShiftConstraint]:
    out: list[ShiftConstraint] = []
    for row in raw or []:
        out.append(ShiftConstraint.model_validate(row))
    return out


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
    out: list[ResolvedConstraint] = []
    for rule in _normalize_constraint_list(template.constraints if template is not None else []):
        out.append(ResolvedConstraint(source="template", rule=rule))
    for rule in _normalize_constraint_list(variant.constraints if variant is not None else []):
        out.append(ResolvedConstraint(source="variant", rule=rule))
    return out


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


def evaluate_assignment_constraints(
    *,
    db: Session,
    slot: RosterSlot,
    team_member_id: int,
    resolved_constraints: list[ResolvedConstraint],
    assigned_slots_for_member: list[RosterSlotAssignment],
    planning_cells_for_member: list[PlanningCell],
    assignment_id: int | None = None,
    member_property_values: dict[int, object],
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    team_slots = [row.roster_slot for row in assigned_slots_for_member if row.roster_slot is not None]
    period = slot.planning_period
    if period is None:
        period = db.get(PlanningPeriod, slot.planning_period_id)
    organization_id = period.organization_id if period is not None else 0
    unavailable_days = {
        row.cell_date
        for row in planning_cells_for_member
        if cell_status_blocks_roster_assignment(db, organization_id=organization_id, status=row.status)
    }
    defs_map: dict[int, TeamMemberPropertyDefinition] = {}
    if any(r.rule.type == "team_member_property_requirement" for r in resolved_constraints):
        period = slot.planning_period
        if period is None:
            period = db.get(PlanningPeriod, slot.planning_period_id)
        if period is not None:
            defs_map = load_property_definitions_map(db, organization_id=period.organization_id)
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
            same_day_slots = [other.id for other in team_slots if other.id != slot.id and other.slot_date == slot.slot_date]
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
        if rule.type == "no_cross_day_into_unavailable_day":
            if slot.ends_at is None:
                continue
            end_day: date = slot.ends_at.date()
            if end_day != slot.slot_date and end_day in unavailable_days:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_CROSS_DAY_UNAVAILABLE",
                        severity=rule.severity,
                        message="Constraint violation: shift crosses into an unavailable day.",
                        team_member_id=team_member_id,
                        date=end_day,
                        details={**details, "end_day": end_day.isoformat()},
                    )
                )
            continue
        if rule.type == "max_assignments_per_month":
            if rule.max_assignments_per_month is None:
                continue
            same_template_assignments = [
                other
                for other in team_slots
                if other.id != slot.id and other.shift_template_id == slot.shift_template_id
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
            paired_variant = db.get(ShiftVariant, rule.paired_shift_variant_id)
            if paired_variant is None:
                continue
            period = slot.planning_period
            if period is None:
                period = db.get(PlanningPeriod, slot.planning_period_id)
            if period is None:
                continue
            month_last = calendar.monthrange(period.year, period.month)[1]
            bound_start = date(period.year, period.month, 1)
            bound_end = date(period.year, period.month, month_last)
            partner_date = slot.slot_date + timedelta(days=rule.partner_day_offset)
            if partner_date < bound_start or partner_date > bound_end:
                continue
            source_variant = slot.shift_variant
            if source_variant is None and slot.shift_variant_id is not None:
                source_variant = db.get(ShiftVariant, slot.shift_variant_id)
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


def find_blocking_constraint(warnings: list[ValidationWarning]) -> ValidationWarning | None:
    for warning in warnings:
        if warning.severity == "error":
            return warning
    return None
