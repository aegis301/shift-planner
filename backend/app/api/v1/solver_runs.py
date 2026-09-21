from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planner
from app.db.session import get_db
from app.models import User
from app.schemas import SolverRunApplyRead, SolverRunCreate, SolverRunRead
from app.services.authz import assert_planning_shift_group_scope
from app.services.solver_runs import (
    SolverRunConflictError,
    SolverRunNotFoundError,
    SolverRunPublishedError,
    applied_assignments_to_read,
    apply_solver_run,
    cancel_solver_run,
    get_solver_run,
    list_solver_runs,
    queue_solver_run,
    solver_run_to_read,
)

router = APIRouter(tags=["solver-runs"])


def _scope(db: Session, user: User, shift_group_id: int) -> None:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/planning-periods/{planning_period_id}/solver-runs", response_model=SolverRunRead)
def post_solver_run(
    planning_period_id: int,
    payload: SolverRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> SolverRunRead:
    _scope(db, user, payload.shift_group_id)
    try:
        run = queue_solver_run(
            db,
            planning_period_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            created_by_user_id=user.id,
        )
    except SolverRunPublishedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "SOLVER_RUN_PUBLISHED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return solver_run_to_read(run)


@router.get("/planning-periods/{planning_period_id}/solver-runs", response_model=list[SolverRunRead])
def get_solver_runs(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> list[SolverRunRead]:
    _scope(db, user, shift_group_id)
    try:
        runs = list_solver_runs(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [solver_run_to_read(run) for run in runs]


@router.get("/planning-periods/{planning_period_id}/solver-runs/{run_id}", response_model=SolverRunRead)
def get_solver_run_endpoint(
    planning_period_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> SolverRunRead:
    try:
        run = get_solver_run(
            db,
            planning_period_id,
            run_id,
            organization_id=user.organization_id,
        )
    except SolverRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _scope(db, user, run.shift_group_id)
    return solver_run_to_read(run)


@router.post("/planning-periods/{planning_period_id}/solver-runs/{run_id}/cancel", response_model=SolverRunRead)
def post_cancel_solver_run(
    planning_period_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> SolverRunRead:
    try:
        existing = get_solver_run(
            db,
            planning_period_id,
            run_id,
            organization_id=user.organization_id,
        )
        _scope(db, user, existing.shift_group_id)
        run = cancel_solver_run(
            db,
            planning_period_id,
            run_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except SolverRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SolverRunConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return solver_run_to_read(run)


@router.post("/planning-periods/{planning_period_id}/solver-runs/{run_id}/apply", response_model=SolverRunApplyRead)
def post_apply_solver_run(
    planning_period_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> SolverRunApplyRead:
    try:
        existing = get_solver_run(
            db,
            planning_period_id,
            run_id,
            organization_id=user.organization_id,
        )
        _scope(db, user, existing.shift_group_id)
        run, assignments = apply_solver_run(
            db,
            planning_period_id,
            run_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except SolverRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SolverRunPublishedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "SOLVER_RUN_PUBLISHED", "message": str(exc)},
        ) from exc
    except SolverRunConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        detail = str(exc)
        status = 404 if detail in {"Planning period not found", "Shift group not found"} else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return SolverRunApplyRead(run=solver_run_to_read(run), assignments=applied_assignments_to_read(assignments))
