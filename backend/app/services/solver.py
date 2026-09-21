from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RosterSlot, SolverRun
from app.services.roster_matrix import ensure_roster_slots_for_period, list_roster_slots
from app.services.shift_groups import shift_template_ids_in_shift_group


@dataclass
class SolverSolveResult:
    proposed_assignments: list[dict] = field(default_factory=list)
    unfilled_slots: list[dict] = field(default_factory=list)
    objective_breakdown: dict = field(default_factory=dict)
    post_check_findings: list = field(default_factory=list)


def list_solver_target_slots(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> list[RosterSlot]:
    ensure_roster_slots_for_period(db, planning_period_id, organization_id)
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    return [
        slot
        for slot in slots
        if slot.shift_template_id is not None and slot.shift_template_id in template_ids
    ]


def solve_roster(
    db: Session,
    run: SolverRun,
    *,
    is_cancelled: Callable[[], bool],
    deadline: datetime,
) -> SolverSolveResult:
    if is_cancelled() or datetime.now(deadline.tzinfo) >= deadline:
        return SolverSolveResult()
    slots = list_solver_target_slots(
        db,
        planning_period_id=run.planning_period_id,
        shift_group_id=run.shift_group_id,
        organization_id=run.organization_id,
    )
    unfilled = [
        {
            "roster_slot_id": slot.id,
            "slot_date": slot.slot_date.isoformat(),
            "label": slot.label,
            "binding_constraints": [],
        }
        for slot in slots
    ]
    return SolverSolveResult(
        proposed_assignments=[],
        unfilled_slots=unfilled,
        objective_breakdown={"unfilled": len(unfilled)},
        post_check_findings=[],
    )
