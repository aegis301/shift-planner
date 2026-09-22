from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Organization, RosterSlotAssignment, SolverRun
from app.schemas import (
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    SolverConfigRead,
    SolverRunCreate,
    SolverRunRead,
)
from app.services.audit import record_audit
from app.services.planning import can_edit_planning_data, get_shift_group_planning_status
from app.services.roster_matrix import upsert_roster_slot_assignment
from app.services.shift_groups import require_shift_group
from app.services.solver.result import SolverSolveResult
from app.services.solver.weights import read_solver_objective_weights
from app.services.tenancy import require_planning_period_in_org
from app.services.work_time_rule_sets import get_active_work_time_rule_set


def solve_roster(*args, **kwargs):
    from app.services.solver.solve import solve_roster as _solve_roster

    return _solve_roster(*args, **kwargs)

SOLVER_RUN_STATUS_QUEUED = "queued"
SOLVER_RUN_STATUS_RUNNING = "running"
SOLVER_RUN_STATUS_SUCCEEDED = "succeeded"
SOLVER_RUN_STATUS_FAILED = "failed"
SOLVER_RUN_STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = {
    SOLVER_RUN_STATUS_SUCCEEDED,
    SOLVER_RUN_STATUS_FAILED,
    SOLVER_RUN_STATUS_CANCELLED,
}

DEFAULT_TIME_BUDGET_SECONDS = 30
DEFAULT_TIME_BUDGET_CEILING_SECONDS = 120
DEFAULT_NUM_SEARCH_WORKERS = 1

FAILURE_TIME_BUDGET_EXCEEDED = "time_budget_exceeded"
FAILURE_SOLVE_ERROR = "solve_error"

SOLVER_ASSIGNMENT_SOURCE = "solver"


class SolverRunPublishedError(Exception):
    pass


class SolverRunNotFoundError(Exception):
    pass


class SolverRunConflictError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def solver_run_to_read(run: SolverRun) -> SolverRunRead:
    return SolverRunRead.model_validate(run)


def _require_editable_shift_group(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None or not can_edit_planning_data(row.status):
        raise SolverRunPublishedError("Cannot run the roster solver for a published shift group")


def _organization_ceiling(db: Session, organization_id: int) -> int:
    org = db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    ceiling = org.solver_time_budget_ceiling_seconds
    if ceiling is None or ceiling < 1:
        return DEFAULT_TIME_BUDGET_CEILING_SECONDS
    return int(ceiling)


def _build_parameters(
    payload: SolverRunCreate,
    *,
    ceiling: int,
) -> dict:
    requested_budget = (
        DEFAULT_TIME_BUDGET_SECONDS if payload.time_budget_seconds is None else int(payload.time_budget_seconds)
    )
    time_budget_seconds = min(max(requested_budget, 1), ceiling)
    num_search_workers = (
        DEFAULT_NUM_SEARCH_WORKERS if payload.num_search_workers is None else int(payload.num_search_workers)
    )
    if num_search_workers < 1:
        num_search_workers = DEFAULT_NUM_SEARCH_WORKERS
    random_seed = payload.random_seed if payload.random_seed is not None else secrets.randbelow(2**31)
    parameters: dict = {
        "time_budget_seconds": time_budget_seconds,
        "num_search_workers": num_search_workers,
        "random_seed": int(random_seed),
        "overwrite_existing": bool(payload.overwrite_existing),
    }
    if payload.objective_weights is not None:
        parameters["objective_weights"] = payload.objective_weights.model_dump()
    return parameters


def read_solver_config(db: Session, organization_id: int) -> SolverConfigRead:
    org = db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    return SolverConfigRead(
        time_budget_ceiling_seconds=_organization_ceiling(db, organization_id),
        default_time_budget_seconds=DEFAULT_TIME_BUDGET_SECONDS,
        weights=read_solver_objective_weights(org),
    )


def queue_solver_run(
    db: Session,
    planning_period_id: int,
    payload: SolverRunCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None,
) -> SolverRun:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    _require_editable_shift_group(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=payload.shift_group_id,
        organization_id=organization_id,
    )
    ceiling = _organization_ceiling(db, organization_id)
    parameters = _build_parameters(payload, ceiling=ceiling)
    active_set = get_active_work_time_rule_set(db, organization_id=organization_id)
    now = datetime.now(UTC)
    run = SolverRun(
        organization_id=organization_id,
        planning_period_id=planning_period_id,
        shift_group_id=payload.shift_group_id,
        status=SOLVER_RUN_STATUS_QUEUED,
        parameters=parameters,
        proposed_assignments=[],
        objective_breakdown={},
        unfilled_slots=[],
        post_check_findings=[],
        rule_set_version_id=active_set.id if active_set is not None else None,
        created_by_user_id=created_by_user_id,
        queued_at=now,
    )
    db.add(run)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="queue",
        entity_type="solver_run",
        entity_id=run.id,
        details={
            "planning_period_id": planning_period_id,
            "shift_group_id": payload.shift_group_id,
            "parameters": parameters,
        },
    )
    db.commit()
    db.refresh(run)
    return run


def list_solver_runs(
    db: Session,
    planning_period_id: int,
    *,
    organization_id: int,
    shift_group_id: int,
) -> list[SolverRun]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    return list(
        db.scalars(
            select(SolverRun)
            .where(
                SolverRun.planning_period_id == planning_period_id,
                SolverRun.organization_id == organization_id,
                SolverRun.shift_group_id == shift_group_id,
            )
            .order_by(SolverRun.id.desc())
        )
    )


def get_solver_run(
    db: Session,
    planning_period_id: int,
    run_id: int,
    *,
    organization_id: int,
) -> SolverRun:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    run = db.get(SolverRun, run_id)
    if run is None or run.planning_period_id != planning_period_id or run.organization_id != organization_id:
        raise SolverRunNotFoundError("Solver run not found")
    return run


def cancel_solver_run(
    db: Session,
    planning_period_id: int,
    run_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> SolverRun:
    run = get_solver_run(db, planning_period_id, run_id, organization_id=organization_id)
    if run.status in TERMINAL_STATUSES:
        raise SolverRunConflictError(
            "SOLVER_RUN_NOT_CANCELLABLE",
            f"Cannot cancel a solver run in status {run.status}",
        )
    run.cancel_requested = True
    if run.status == SOLVER_RUN_STATUS_QUEUED:
        run.status = SOLVER_RUN_STATUS_CANCELLED
        run.finished_at = datetime.now(UTC)
        run.failure_reason = None
    record_audit(
        db,
        actor=actor,
        source=source,
        action="cancel",
        entity_type="solver_run",
        entity_id=run.id,
        details={"status": run.status},
    )
    db.commit()
    db.refresh(run)
    return run


def apply_solver_run(
    db: Session,
    planning_period_id: int,
    run_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> tuple[SolverRun, list[RosterSlotAssignment]]:
    run = get_solver_run(db, planning_period_id, run_id, organization_id=organization_id)
    if run.status != SOLVER_RUN_STATUS_SUCCEEDED:
        raise SolverRunConflictError(
            "SOLVER_RUN_NOT_APPLYABLE",
            f"Cannot apply a solver run in status {run.status}",
        )
    if run.applied_at is not None:
        raise SolverRunConflictError("SOLVER_RUN_ALREADY_APPLIED", "Solver run has already been applied")
    _require_editable_shift_group(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=run.shift_group_id,
        organization_id=organization_id,
    )
    overwrite_existing = bool(run.parameters.get("overwrite_existing", False))
    existing_slot_ids: set[int] = set()
    proposed_slot_ids = [int(row["roster_slot_id"]) for row in run.proposed_assignments]
    if not overwrite_existing and proposed_slot_ids:
        existing_slot_ids = set(
            db.scalars(
                select(RosterSlotAssignment.roster_slot_id).where(
                    RosterSlotAssignment.roster_slot_id.in_(proposed_slot_ids)
                )
            )
        )
    written: list[RosterSlotAssignment] = []
    for row in run.proposed_assignments:
        slot_id = int(row["roster_slot_id"])
        if slot_id in existing_slot_ids:
            continue
        assignment = upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(
                roster_slot_id=slot_id,
                team_member_id=int(row["team_member_id"]),
                comment=row.get("comment"),
                manual_override=bool(row.get("manual_override", False)),
            ),
            organization_id=organization_id,
            actor=actor,
            source=SOLVER_ASSIGNMENT_SOURCE,
        )
        written.append(assignment)
    run.applied_at = datetime.now(UTC)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="apply",
        entity_type="solver_run",
        entity_id=run.id,
        details={"assignment_count": len(written)},
    )
    db.commit()
    db.refresh(run)
    return run, written


def claim_next_queued_run(db: Session) -> SolverRun | None:
    dialect_name = db.get_bind().dialect.name
    stmt = (
        select(SolverRun.id)
        .where(SolverRun.status == SOLVER_RUN_STATUS_QUEUED)
        .order_by(SolverRun.id)
        .limit(1)
    )
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    run_id = db.scalar(stmt)
    if run_id is None:
        return None
    now = datetime.now(UTC)
    result = db.execute(
        update(SolverRun)
        .where(SolverRun.id == run_id, SolverRun.status == SOLVER_RUN_STATUS_QUEUED)
        .values(status=SOLVER_RUN_STATUS_RUNNING, started_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(SolverRun, run_id)


def _finalize_run(
    db: Session,
    run: SolverRun,
    *,
    status: str,
    result: SolverSolveResult | None = None,
    failure_reason: str | None = None,
) -> SolverRun:
    now = datetime.now(UTC)
    run.status = status
    run.finished_at = now
    run.failure_reason = failure_reason
    if run.started_at is not None:
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        run.duration_ms = int((now - started).total_seconds() * 1000)
    if result is not None:
        run.proposed_assignments = result.proposed_assignments
        run.unfilled_slots = result.unfilled_slots
        run.objective_breakdown = result.objective_breakdown
        run.post_check_findings = result.post_check_findings
    db.commit()
    db.refresh(run)
    return run


def execute_solver_run(
    db: Session,
    run_id: int,
    *,
    solve_fn: Callable[..., SolverSolveResult] | None = None,
) -> SolverRun:
    run = db.get(SolverRun, run_id)
    if run is None:
        raise SolverRunNotFoundError("Solver run not found")
    db.refresh(run)
    if run.cancel_requested:
        return _finalize_run(db, run, status=SOLVER_RUN_STATUS_CANCELLED)
    budget = float(run.parameters.get("time_budget_seconds", DEFAULT_TIME_BUDGET_SECONDS))
    started = datetime.now(UTC)
    deadline = started + timedelta(seconds=budget)
    resolver = solve_fn if solve_fn is not None else solve_roster

    def is_cancelled() -> bool:
        db.refresh(run)
        return bool(run.cancel_requested)

    try:
        result = resolver(db, run, is_cancelled=is_cancelled, deadline=deadline)
    except Exception as exc:
        return _finalize_run(
            db,
            run,
            status=SOLVER_RUN_STATUS_FAILED,
            failure_reason=f"{FAILURE_SOLVE_ERROR}:{exc}",
        )
    elapsed = (datetime.now(UTC) - started).total_seconds()
    db.refresh(run)
    if run.cancel_requested:
        return _finalize_run(db, run, status=SOLVER_RUN_STATUS_CANCELLED, result=result)
    if elapsed > budget:
        return _finalize_run(
            db,
            run,
            status=SOLVER_RUN_STATUS_FAILED,
            result=result,
            failure_reason=FAILURE_TIME_BUDGET_EXCEEDED,
        )
    return _finalize_run(db, run, status=SOLVER_RUN_STATUS_SUCCEEDED, result=result)


def process_one_queued_run(
    db: Session,
    *,
    solve_fn: Callable[..., SolverSolveResult] | None = None,
) -> SolverRun | None:
    run = claim_next_queued_run(db)
    if run is None:
        return None
    return execute_solver_run(db, run.id, solve_fn=solve_fn)


def applied_assignments_to_read(assignments: list[RosterSlotAssignment]) -> list[RosterSlotAssignmentRead]:
    return [RosterSlotAssignmentRead.model_validate(row) for row in assignments]
