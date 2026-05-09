from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_admin,
    get_current_planner,
    get_current_user_excluding_applicant,
)
from app.db.session import get_db
from app.models import User
from app.services.authz import is_admin, is_shift_planner_role
from app.schemas import (
    PlanningPeriodCreate,
    PlanningPeriodRead,
    RosterMatrixRead,
    ValidationWarning,
)
from app.services.exports import export_matrix_csv, export_roster_matrix_csv
from app.services.planning import (
    create_planning_period,
    delete_planning_period,
    list_planning_periods,
    publish_planning_period,
    set_planning_period_to_draft,
    set_planning_period_to_preliminary,
    unpublish_planning_period,
)
from app.services.roster_matrix import get_roster_matrix, reset_roster_slots_for_period
from app.services.validation import validate_roster

router = APIRouter(tags=["planning"])


@router.get("/planning-periods", response_model=list[PlanningPeriodRead])
def get_planning_periods(
    db: Session = Depends(get_db), user: User = Depends(get_current_user_excluding_applicant)
):
    return list_planning_periods(db, organization_id=user.organization_id)


@router.post("/planning-periods", response_model=PlanningPeriodRead)
def post_planning_period(
    payload: PlanningPeriodCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    return create_planning_period(
        db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
    )


@router.post("/planning-periods/{planning_period_id}/publish", response_model=PlanningPeriodRead)
def post_publish_planning_period(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    period = publish_planning_period(
        db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return period


@router.post("/planning-periods/{planning_period_id}/preliminary", response_model=PlanningPeriodRead)
def post_set_planning_period_preliminary(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    period = set_planning_period_to_preliminary(
        db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return period


@router.post("/planning-periods/{planning_period_id}/draft", response_model=PlanningPeriodRead)
def post_set_planning_period_draft(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    period = set_planning_period_to_draft(
        db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return period


@router.post("/planning-periods/{planning_period_id}/unpublish", response_model=PlanningPeriodRead)
def post_unpublish_planning_period(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    period = unpublish_planning_period(
        db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return period


@router.delete("/planning-periods/{planning_period_id}")
def delete_planning_period_endpoint(
    planning_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    return {
        "deleted": delete_planning_period(
            db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }


@router.post("/planning-periods/{planning_period_id}/regenerate-roster", response_model=RosterMatrixRead)
def regenerate_planning_period_roster(
    planning_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_planner)
):
    try:
        reset_roster_slots_for_period(
            db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
        return get_roster_matrix(db, planning_period_id, organization_id=user.organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/validation/{planning_period_id}", response_model=list[ValidationWarning])
def get_validation(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        return validate_roster(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/exports/roster-matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_roster_matrix_csv(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        body = export_roster_matrix_csv(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-matrix-{planning_period_id}.csv"'},
    )


@router.get("/exports/matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_matrix_csv(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        body = export_matrix_csv(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="matrix-{planning_period_id}.csv"'},
    )
