from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
)
from app.services.roster_matrix import (
    clear_roster_slot_assignment,
    get_roster_matrix,
    upsert_roster_slot_assignment,
)

router = APIRouter(prefix="/roster-matrix", tags=["roster-matrix"])


@router.get("/{planning_period_id}", response_model=RosterMatrixRead)
def get_final_roster_matrix(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return get_roster_matrix(db, planning_period_id, shift_group_id=shift_group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/assignments", response_model=RosterSlotAssignmentRead)
def put_roster_slot_assignment(
    payload: RosterSlotAssignmentUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return upsert_roster_slot_assignment(db, payload, actor=user.email, source="rest")
    except ValueError as exc:
        detail = str(exc)
        if detail == "Roster slot not found":
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/assignments/clear")
def clear_assignment(
    payload: RosterSlotAssignmentClear,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = clear_roster_slot_assignment(db, payload, actor=user.email, source="rest")
    return {"deleted": deleted}
