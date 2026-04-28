from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    AvailabilityRequestCreate,
    AvailabilityRequestRead,
    PlanningPeriodCreate,
    PlanningPeriodRead,
    RosterAssignmentCreate,
    RosterAssignmentRead,
    ValidationWarning,
)
from app.services.exports import export_matrix_csv, export_roster_csv, export_roster_matrix_csv
from app.services.planning import (
    assign_shift,
    create_planning_period,
    list_planning_periods,
    list_requests,
    list_roster_assignments,
    record_availability_request,
)
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


@router.get("/requests", response_model=list[AvailabilityRequestRead])
def get_requests(
    planning_period_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_requests(db, planning_period_id=planning_period_id)


@router.post("/requests", response_model=AvailabilityRequestRead)
def post_request(
    payload: AvailabilityRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return record_availability_request(db, payload, actor=user.email, source="rest")


@router.get("/roster", response_model=list[RosterAssignmentRead])
def get_roster(
    planning_period_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_roster_assignments(db, planning_period_id=planning_period_id)


@router.post("/roster", response_model=RosterAssignmentRead)
def post_roster_assignment(
    payload: RosterAssignmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return assign_shift(db, payload, actor=user.email, source="rest")


@router.get("/validation/{planning_period_id}", response_model=list[ValidationWarning])
def get_validation(planning_period_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return validate_roster(db, planning_period_id)


@router.get("/exports/roster/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_roster_csv(planning_period_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return PlainTextResponse(
        export_roster_csv(db, planning_period_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-{planning_period_id}.csv"'},
    )


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
