from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    EmploymentPeriodRead,
    EmploymentPeriodsReplace,
    TimeAccountOpeningRead,
    TimeAccountOpeningUpsert,
)
from app.services.employment_periods import (
    employment_period_to_read,
    get_time_account_opening,
    list_employment_periods,
    replace_employment_periods,
    time_account_opening_to_read,
    upsert_time_account_opening,
)

router = APIRouter(prefix="/team-members", tags=["employment-periods"])


@router.get("/{team_member_id}/employment-periods", response_model=list[EmploymentPeriodRead])
def get_employment_periods(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> list[EmploymentPeriodRead]:
    rows = list_employment_periods(db, team_member_id, organization_id=user.organization_id)
    return [employment_period_to_read(row) for row in rows]


@router.put("/{team_member_id}/employment-periods", response_model=list[EmploymentPeriodRead])
def put_employment_periods(
    team_member_id: int,
    payload: EmploymentPeriodsReplace,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[EmploymentPeriodRead]:
    try:
        rows = replace_employment_periods(
            db,
            team_member_id,
            payload.periods,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [employment_period_to_read(row) for row in rows]


@router.get("/{team_member_id}/time-account-opening", response_model=TimeAccountOpeningRead | None)
def get_opening(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> TimeAccountOpeningRead | None:
    row = get_time_account_opening(db, team_member_id, organization_id=user.organization_id)
    if row is None:
        return None
    return time_account_opening_to_read(row)


@router.put("/{team_member_id}/time-account-opening", response_model=TimeAccountOpeningRead)
def put_opening(
    team_member_id: int,
    payload: TimeAccountOpeningUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TimeAccountOpeningRead:
    try:
        row = upsert_time_account_opening(
            db,
            team_member_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return time_account_opening_to_read(row)
