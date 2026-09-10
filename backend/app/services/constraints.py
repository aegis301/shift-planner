from sqlalchemy.orm import Session

from app.models import PlanningCell, RosterSlot, RosterSlotAssignment
from app.schemas import ValidationWarning
from app.services.rules.shift_constraints import (
    ResolvedConstraint,
    evaluate_shift_constraints_for_slot,
    resolve_slot_constraints,
)

__all__ = [
    "ResolvedConstraint",
    "evaluate_assignment_constraints",
    "find_blocking_constraint",
    "resolve_slot_constraints",
]


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
    del assigned_slots_for_member, planning_cells_for_member
    return evaluate_shift_constraints_for_slot(
        db=db,
        slot=slot,
        team_member_id=team_member_id,
        resolved_constraints=resolved_constraints,
        assignment_id=assignment_id,
        member_property_values=member_property_values,
    )


def find_blocking_constraint(warnings: list[ValidationWarning]) -> ValidationWarning | None:
    for warning in warnings:
        if warning.severity == "error":
            return warning
    return None
