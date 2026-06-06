from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_planner, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
)
from app.services.authz import (
    assert_planning_shift_group_scope,
    assert_team_member_shift_group_access,
    can_access_team_member_portal,
    can_use_planning_ui,
    get_linked_team_member,
)
from app.services.roster_matrix import (
    clear_roster_slot_assignment,
    get_roster_matrix,
    upsert_roster_slot_assignment,
)
from app.services.exports import export_roster_matrix_pdf, export_roster_matrix_xlsx
from app.services.ics_export import export_member_shifts_ics, export_single_roster_slot_ics
from app.services.planning import get_shift_group_planning_status, is_team_member_roster_visible

router = APIRouter(prefix="/roster-matrix", tags=["roster-matrix"])
export_router = APIRouter(tags=["roster-matrix"])


def _resolve_published_roster_export_scope(
    db: Session,
    user: User,
    planning_period_id: int,
    shift_group_id: int | None,
    team_member_portal: bool,
) -> int | None:
    if can_use_planning_ui(user) and not team_member_portal:
        try:
            assert_planning_shift_group_scope(db, user, shift_group_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    else:
        linked = get_linked_team_member(db, user)
        if linked is None:
            raise HTTPException(status_code=403, detail="No linked team member profile")
        if shift_group_id is None:
            raise HTTPException(status_code=400, detail="shift_group_id is required")
        try:
            assert_team_member_shift_group_access(db, user, shift_group_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    if shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=user.organization_id,
    )
    if row is None or not is_team_member_roster_visible(row.status):
        raise HTTPException(status_code=403, detail="Roster is not visible for team members")
    return shift_group_id


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
    if shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=user.organization_id,
    )
    if row is None or not is_team_member_roster_visible(row.status):
        raise HTTPException(status_code=403, detail="Roster is not visible for team members")
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


@export_router.get("/exports/roster-matrix/{planning_period_id}.xlsx")
def get_roster_matrix_xlsx(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resolved_shift_group_id = _resolve_published_roster_export_scope(
        db, user, planning_period_id, shift_group_id, team_member_portal
    )
    try:
        body = export_roster_matrix_xlsx(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=resolved_shift_group_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="roster-matrix-{planning_period_id}.xlsx"'},
    )


@export_router.get("/exports/roster-matrix/{planning_period_id}.pdf")
def get_roster_matrix_pdf(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resolved_shift_group_id = _resolve_published_roster_export_scope(
        db, user, planning_period_id, shift_group_id, team_member_portal
    )
    try:
        body = export_roster_matrix_pdf(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=resolved_shift_group_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="roster-matrix-{planning_period_id}.pdf"'},
    )


def _require_team_member_export_user(db: Session, user: User):
    if not can_access_team_member_portal(db, user):
        raise HTTPException(status_code=403, detail="Team member portal access denied")
    linked = get_linked_team_member(db, user)
    if linked is None:
        raise HTTPException(status_code=403, detail="No linked team member profile")
    return linked


@export_router.get("/exports/roster-slots/{roster_slot_id}.ics")
def get_roster_slot_ics(
    roster_slot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    member = _require_team_member_export_user(db, user)
    try:
        body = export_single_roster_slot_ics(
            db,
            organization_id=user.organization_id,
            team_member_id=member.id,
            roster_slot_id=roster_slot_id,
            calendar_name="Shift",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="shift-{roster_slot_id}.ics"'},
    )


@export_router.get("/exports/my-shifts.ics")
def get_my_shifts_ics(
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    member = _require_team_member_export_user(db, user)
    try:
        assert_team_member_shift_group_access(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        body = export_member_shifts_ics(
            db,
            organization_id=user.organization_id,
            team_member_id=member.id,
            shift_group_id=shift_group_id,
            calendar_name="My shifts",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="my-shifts.ics"'},
    )


@export_router.get("/exports/my-shifts/{planning_period_id}.ics")
def get_my_shifts_period_ics(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _resolve_published_roster_export_scope(db, user, planning_period_id, shift_group_id, True)
    member = _require_team_member_export_user(db, user)
    try:
        body = export_member_shifts_ics(
            db,
            organization_id=user.organization_id,
            team_member_id=member.id,
            shift_group_id=shift_group_id,
            planning_period_id=planning_period_id,
            calendar_name="My shifts",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="my-shifts-{planning_period_id}.ics"',
        },
    )
