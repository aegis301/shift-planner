from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.models import Organization, PlanningPeriod, RosterSlot, SolverRun
from app.services.fairness import build_fairness_accounts
from app.services.roster_matrix import ensure_roster_slots_for_period, list_roster_slots
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.rules.shift_constraints import overlay_candidate_assignment
from app.services.shift_groups import shift_template_ids_in_shift_group
from app.services.solver.model import build_solver_context, planning_window
from app.services.solver.objective import apply_objective
from app.services.solver.result import SolverSolveResult
from app.services.solver.weights import resolve_solver_objective_weights


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


def _fairness_duty_cost(
    db: Session,
    *,
    planning_period_id: int,
    organization_id: int,
    shift_group_id: int,
) -> dict[int, int]:
    try:
        accounts = build_fairness_accounts(
            db,
            planning_period_id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
    except ValueError:
        return {}
    costs: dict[int, int] = {}
    for member in accounts.members:
        for item in member.dimensions:
            if item.dimension_id != "duties":
                continue
            costs[member.team_member_id] = max(0, round(item.deviation_absolute))
            break
    return costs


def _overlay_proposed(state, proposed: list[dict]):
    current = state
    for row in proposed:
        slot = current.slots_by_id.get(int(row["roster_slot_id"]))
        if slot is None:
            continue
        current = overlay_candidate_assignment(
            current,
            slot=slot,
            team_member_id=int(row["team_member_id"]),
            assignment_id=None,
        )
    return current


def solve_roster(
    db: Session,
    run: SolverRun,
    *,
    is_cancelled: Callable[[], bool],
    deadline: datetime,
) -> SolverSolveResult:
    if is_cancelled() or datetime.now(deadline.tzinfo) >= deadline:
        return SolverSolveResult()
    period = db.get(PlanningPeriod, run.planning_period_id)
    if period is None:
        return SolverSolveResult()
    slots = list_solver_target_slots(
        db,
        planning_period_id=run.planning_period_id,
        shift_group_id=run.shift_group_id,
        organization_id=run.organization_id,
    )
    if not slots:
        return SolverSolveResult(objective_breakdown={"unfilled": 0})
    start_date, end_date = planning_window(period)
    state = build_plan_state(
        db,
        organization_id=run.organization_id,
        start_date=start_date,
        end_date=end_date,
    )
    organization = db.get(Organization, run.organization_id)
    parameters = run.parameters or {}
    weights = resolve_solver_objective_weights(organization, parameters)
    overwrite_existing = bool(parameters.get("overwrite_existing", False))
    ctx = build_solver_context(
        db,
        state=state,
        target_slots=slots,
        weights=weights,
        overwrite_existing=overwrite_existing,
        fairness_duty_cost=_fairness_duty_cost(
            db,
            planning_period_id=run.planning_period_id,
            organization_id=run.organization_id,
            shift_group_id=run.shift_group_id,
        ),
    )
    apply_objective(ctx)
    if is_cancelled() or datetime.now(deadline.tzinfo) >= deadline:
        return SolverSolveResult()
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = max(1, int(parameters.get("num_search_workers", 1)))
    solver.parameters.random_seed = int(parameters.get("random_seed", 1))
    remaining = (deadline - datetime.now(deadline.tzinfo)).total_seconds()
    solver.parameters.max_time_in_seconds = max(0.01, remaining)
    status = solver.Solve(ctx.cp_model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        unfilled = [
            {
                "roster_slot_id": slot.id,
                "slot_date": slot.slot_date.isoformat(),
                "label": slot.label,
                "binding_constraints": ctx.binding_codes.get(slot.id, []),
            }
            for slot in slots
        ]
        return SolverSolveResult(
            proposed_assignments=[],
            unfilled_slots=unfilled,
            objective_breakdown={"unfilled": weights.unfilled * len(unfilled)},
            post_check_findings=[],
        )
    proposed: list[dict] = []
    unfilled: list[dict] = []
    for slot in slots:
        assigned_member: int | None = None
        for (slot_id, member_id), var in ctx.variables.items():
            if slot_id != slot.id:
                continue
            if solver.Value(var) == 1:
                assigned_member = member_id
                break
        if assigned_member is None and slot.id in ctx.fixed_assignments:
            assigned_member = ctx.fixed_assignments[slot.id]
        if assigned_member is None:
            unfilled.append(
                {
                    "roster_slot_id": slot.id,
                    "slot_date": slot.slot_date.isoformat(),
                    "label": slot.label,
                    "binding_constraints": ctx.binding_codes.get(slot.id, []),
                }
            )
            continue
        proposed.append(
            {
                "roster_slot_id": slot.id,
                "team_member_id": assigned_member,
                "comment": None,
                "manual_override": False,
            }
        )
    breakdown = {
        name: int(solver.Value(term))
        for name, term in ctx.objective_terms.items()
        if name != "nogo"
    }
    overlaid = _overlay_proposed(state, proposed)
    findings = evaluate_plan_state(overlaid, db=db)
    post_check = [warning.model_dump(mode="json") for warning in findings]
    return SolverSolveResult(
        proposed_assignments=proposed,
        unfilled_slots=unfilled,
        objective_breakdown=breakdown,
        post_check_findings=post_check,
    )
