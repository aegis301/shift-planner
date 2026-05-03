from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planner, get_current_user
from app.db.session import get_db
from app.models import PlanningPeriod, User
from app.schemas import (
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
)
from app.services.authz import (
    assert_planning_shift_group_scope,
    assert_team_member_shift_group_access,
    can_use_planning_ui,
    get_linked_team_member,
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
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if can_use_planning_ui(user) and not team_member_portal:
        try:
            assert_planning_shift_group_scope(db, user, shift_group_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            return get_roster_matrix(
                db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    linked = get_linked_team_member(db, user)
    if linked is None:
        raise HTTPException(status_code=403, detail="No linked team member profile")
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Planning period not found")
    if period.status != "published":
        raise HTTPException(status_code=403, detail="Roster is not published yet")
    if shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        assert_team_member_shift_group_access(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        return get_roster_matrix(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/assignments", response_model=RosterSlotAssignmentRead)
def put_roster_slot_assignment(
    payload: RosterSlotAssignmentUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        return upsert_roster_slot_assignment(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "Roster slot not found":
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post("/assignments/clear")
def clear_assignment(
    payload: RosterSlotAssignmentClear,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    deleted = clear_roster_slot_assignment(
        db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    return {"deleted": deleted}
