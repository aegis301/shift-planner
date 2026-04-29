from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
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
)
from app.services.roster_matrix import get_roster_matrix, reset_roster_slots_for_period
from app.services.validation import validate_roster

router = APIRouter(tags=["planning"])


@router.get("/planning-periods", response_model=list[PlanningPeriodRead])
def get_planning_periods(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_planning_periods(db)


@router.post("/planning-periods", response_model=PlanningPeriodRead)
def post_planning_period(
    payload: PlanningPeriodCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return create_planning_period(db, payload, actor=user.email, source="rest")


@router.delete("/planning-periods/{planning_period_id}")
def delete_planning_period_endpoint(
    planning_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return {"deleted": delete_planning_period(db, planning_period_id, actor=user.email, source="rest")}


@router.post("/planning-periods/{planning_period_id}/regenerate-roster", response_model=RosterMatrixRead)
def regenerate_planning_period_roster(
    planning_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    try:
        reset_roster_slots_for_period(db, planning_period_id, actor=user.email, source="rest")
        return get_roster_matrix(db, planning_period_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/validation/{planning_period_id}", response_model=list[ValidationWarning])
def get_validation(planning_period_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return validate_roster(db, planning_period_id)


@router.get("/exports/roster-matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_roster_matrix_csv(planning_period_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return PlainTextResponse(
        export_roster_matrix_csv(db, planning_period_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-matrix-{planning_period_id}.csv"'},
    )


@router.get("/exports/matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_matrix_csv(planning_period_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return PlainTextResponse(
        export_matrix_csv(db, planning_period_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="matrix-{planning_period_id}.csv"'},
    )
