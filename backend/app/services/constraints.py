from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.models import PlanningCell, RosterSlot, RosterSlotAssignment, ShiftTemplate, ShiftVariant
from app.schemas import ShiftConstraint, UNAVAILABLE_STATUSES, ValidationWarning

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


def _severity(enforcement: str) -> Literal["warning", "error"]:
    return "error" if enforcement == "block" else "warning"


def _base_details(
    *,
    slot: RosterSlot,
    source: ConstraintSource,
    constraint_type: str,
    enforcement: str,
) -> dict[str, object]:
    return {
        "constraint_type": constraint_type,
        "constraint_source": source,
        "enforcement": enforcement,
        "roster_slot_id": slot.id,
        "shift_template_id": slot.shift_template_id,
        "shift_variant_id": slot.shift_variant_id,
    }


def evaluate_assignment_constraints(
    *,
    slot: RosterSlot,
    team_member_id: int,
    resolved_constraints: list[ResolvedConstraint],
    assigned_slots_for_member: list[RosterSlotAssignment],
    planning_cells_for_member: list[PlanningCell],
    assignment_id: int | None = None,
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    team_slots = [row.roster_slot for row in assigned_slots_for_member if row.roster_slot is not None]
    unavailable_days = {
        row.cell_date
        for row in planning_cells_for_member
        if row.status in UNAVAILABLE_STATUSES
    }
    for resolved in resolved_constraints:
        rule = resolved.rule
        details = _base_details(
            slot=slot,
            source=resolved.source,
            constraint_type=rule.type,
            enforcement=rule.enforcement,
        )
        if assignment_id is not None:
            details["roster_slot_assignment_id"] = assignment_id
        if rule.type == "no_additional_same_day":
            same_day_slots = [other.id for other in team_slots if other.id != slot.id and other.slot_date == slot.slot_date]
            if same_day_slots:
                warnings.append(
                    ValidationWarning(
                        code="ROSTER_CONSTRAINT_SAME_DAY",
                        severity=_severity(rule.enforcement),
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
                        severity=_severity(rule.enforcement),
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
                        severity=_severity(rule.enforcement),
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
                        severity=_severity(rule.enforcement),
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
    return warnings


def find_blocking_constraint(warnings: list[ValidationWarning]) -> ValidationWarning | None:
    for warning in warnings:
        if warning.details.get("enforcement") == "block":
            return warning
    return None
