from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planning_user, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import DutyActivityCreate, DutyUtilizationPeriodRead, TimeEntryRead
from app.services.authz import assert_planning_shift_group_scope, get_linked_team_member
from app.services.duty_activity import (
    delete_duty_activity,
    duty_activity_to_read,
    list_duty_activity_episodes,
    record_duty_activity,
)
from app.services.duty_utilization import period_utilization

router = APIRouter(prefix="/duty-activity", tags=["duty-activity"])


def _require_linked_member(db: Session, user: User):
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=403, detail="Team member profile is not linked to this account")
    return member


@router.get("", response_model=list[TimeEntryRead])
def get_own_duty_activity(
    roster_slot_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TimeEntryRead]:
    member = _require_linked_member(db, user)
    rows = list_duty_activity_episodes(
        db,
        organization_id=user.organization_id,
        team_member_id=member.id,
        roster_slot_id=roster_slot_id,
    )
    return [duty_activity_to_read(row) for row in rows]


@router.post("", response_model=TimeEntryRead)
def post_own_duty_activity(
    payload: DutyActivityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimeEntryRead:
    member = _require_linked_member(db, user)
    if payload.team_member_id is not None and payload.team_member_id != member.id:
        raise HTTPException(status_code=403, detail="Can only record your own duty activity")
    try:
        row = record_duty_activity(
            db,
            payload,
            organization_id=user.organization_id,
            team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return duty_activity_to_read(row)


@router.delete("/{entry_id}")
def delete_own_duty_activity(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    member = _require_linked_member(db, user)
    try:
        deleted = delete_duty_activity(
            db,
            entry_id,
            organization_id=user.organization_id,
            team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Duty activity episode not found")
    return {"deleted": True}


@router.get("/utilization/{planning_period_id}", response_model=DutyUtilizationPeriodRead)
def get_duty_utilization(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    shift_template_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> DutyUtilizationPeriodRead:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
        return period_utilization(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            shift_template_id=shift_template_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
