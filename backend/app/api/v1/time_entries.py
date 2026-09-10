from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planning_user, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    TimeEntryCreate,
    TimeEntryDeriveRequest,
    TimeEntryRead,
    TimeEntryReconciliationItem,
    TimeEntryUpdate,
)
from app.services.authz import can_use_planning_ui, get_linked_team_member, is_admin
from app.services.team_members import list_team_members_for_planner
from app.services.time_entries import (
    create_manual_entry,
    delete_time_entry,
    derive_entries,
    get_time_entry,
    list_reconciliation,
    list_time_entries,
    time_entry_to_read,
    update_time_entry,
)

router = APIRouter(prefix="/time-entries", tags=["time-entries"])


def _assert_read(db: Session, user: User, team_member_id: int, *, team_member_portal: bool) -> None:
    if team_member_portal or not can_use_planning_ui(user):
        member = get_linked_team_member(db, user)
        if member is None or member.id != team_member_id:
            raise PermissionError("Can only access your own time entries")
        return
    if is_admin(user):
        return
    allowed = {member.id for member in list_team_members_for_planner(db, user)}
    if team_member_id not in allowed:
        raise PermissionError("Team member is outside planner scope")


def _assert_write(db: Session, user: User, team_member_id: int, *, team_member_portal: bool) -> None:
    if is_admin(user) and not team_member_portal:
        return
    member = get_linked_team_member(db, user)
    if member is None or member.id != team_member_id:
        raise PermissionError("Can only write your own time entries")


def _member_ids_for_derive(db: Session, user: User, requested: list[int] | None) -> list[int] | None:
    if is_admin(user):
        return requested
    allowed = {member.id for member in list_team_members_for_planner(db, user)}
    if requested is None:
        return list(allowed)
    if any(member_id not in allowed for member_id in requested):
        raise PermissionError("Team member is outside planner scope")
    return requested


@router.get("", response_model=list[TimeEntryRead])
def get_time_entries(
    team_member_id: int,
    start_date: date,
    end_date: date,
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TimeEntryRead]:
    try:
        _assert_read(db, user, team_member_id, team_member_portal=team_member_portal)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    rows = list_time_entries(
        db,
        organization_id=user.organization_id,
        team_member_id=team_member_id,
        start_date=start_date,
        end_date=end_date,
    )
    return [time_entry_to_read(row) for row in rows]


@router.get("/reconciliation", response_model=list[TimeEntryReconciliationItem])
def get_reconciliation(
    team_member_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> list[TimeEntryReconciliationItem]:
    try:
        _assert_read(db, user, team_member_id, team_member_portal=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return list_reconciliation(
        db,
        organization_id=user.organization_id,
        team_member_id=team_member_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/derive")
def post_derive(
    payload: TimeEntryDeriveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> dict[str, bool]:
    try:
        member_ids = _member_ids_for_derive(db, user, payload.member_ids)
        derive_entries(
            db,
            organization_id=user.organization_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            member_ids=member_ids,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("", response_model=TimeEntryRead)
def post_time_entry(
    payload: TimeEntryCreate,
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimeEntryRead:
    try:
        _assert_write(db, user, payload.team_member_id, team_member_portal=team_member_portal)
        row = create_manual_entry(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return time_entry_to_read(row)


@router.patch("/{entry_id}", response_model=TimeEntryRead)
def patch_time_entry(
    entry_id: int,
    payload: TimeEntryUpdate,
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimeEntryRead:
    current = get_time_entry(db, entry_id, organization_id=user.organization_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    try:
        _assert_write(db, user, current.team_member_id, team_member_portal=team_member_portal)
        row = update_time_entry(
            db, entry_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return time_entry_to_read(row)


@router.delete("/{entry_id}")
def delete_time_entry_endpoint(
    entry_id: int,
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    current = get_time_entry(db, entry_id, organization_id=user.organization_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    try:
        _assert_write(db, user, current.team_member_id, team_member_portal=team_member_portal)
        deleted = delete_time_entry(
            db, entry_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return {"deleted": True}
