from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_admin, get_current_planner, get_current_user
from app.api.file_responses import ICS_RESPONSES, PDF_RESPONSES, XLSX_RESPONSES
from app.db.session import get_db
from app.models import (
    RosterChangeSet,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftGroupShiftTemplate,
    User,
)
from app.schemas import (
    DeletedFlagRead,
    RosterChangeSetCreate,
    RosterChangeSetItemRead,
    RosterChangeSetRead,
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    SlotCandidatesRead,
)
from app.services.authz import (
    assert_planning_shift_group_scope,
    assert_team_member_shift_group_access,
    can_access_team_member_portal,
    can_use_planning_ui,
    get_linked_team_member,
)
from app.services.exports import (
    export_roster_matrix_pdf,
    export_roster_matrix_xlsx,
    export_works_council_duty_utilization_pdf,
    export_works_council_duty_utilization_xlsx,
)
from app.services.ics_export import (
    export_member_shifts_ics,
    export_single_roster_slot_ics,
    resolve_ics_date_range,
)
from app.services.planning import (
    can_edit_planning_data,
    get_shift_group_planning_status,
    is_team_member_roster_visible,
)
from app.services.roster_candidates import list_slot_candidates
from app.services.roster_change_sets import (
    RosterChangeInput,
    RosterChangeSetError,
    apply_roster_change_set,
    legacy_refusal_message,
    list_roster_change_sets,
    revert_roster_change_set,
)
from app.services.roster_matrix import (
    get_roster_matrix,
)

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


def _resolve_assignment_shift_group_id(
    db: Session,
    *,
    slot: RosterSlot,
    organization_id: int,
    shift_group_id: int | None,
) -> int:
    if shift_group_id is not None:
        return shift_group_id
    if slot.shift_template_id is not None:
        linked = list(
            db.scalars(
                select(ShiftGroupShiftTemplate.shift_group_id).where(
                    ShiftGroupShiftTemplate.shift_template_id == slot.shift_template_id
                )
            )
        )
        if len(linked) == 1:
            return linked[0]
        if linked:
            return linked[0]
    fallback = db.scalar(
        select(ShiftGroup.id)
        .where(ShiftGroup.organization_id == organization_id, ShiftGroup.is_active.is_(True))
        .order_by(ShiftGroup.display_order, ShiftGroup.id)
        .limit(1)
    )
    if fallback is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    return fallback


def _assert_roster_editable(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> None:
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None or not can_edit_planning_data(row.status):
        raise HTTPException(
            status_code=403,
            detail="Roster assignments are read-only while this shift group's plan is published",
        )


@router.get(
    "/{planning_period_id}/slots/{roster_slot_id}/candidates",
    response_model=SlotCandidatesRead,
)
def get_slot_candidates(
    planning_period_id: int,
    roster_slot_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> SlotCandidatesRead:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        payload = list_slot_candidates(
            db,
            roster_slot_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload.planning_period_id != planning_period_id:
        raise HTTPException(status_code=404, detail="Roster slot not found")
    return payload


def _change_set_read(row: RosterChangeSet) -> RosterChangeSetRead:
    return RosterChangeSetRead(
        id=row.id,
        organization_id=row.organization_id,
        planning_period_id=row.planning_period_id,
        shift_group_id=row.shift_group_id,
        created_by_user_id=row.created_by_user_id,
        actor=row.actor,
        source=row.source,
        mode=row.mode,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        reverts_change_set_id=row.reverts_change_set_id,
        label=row.label,
        created_at=row.created_at,
        items=[
            RosterChangeSetItemRead(
                id=item.id,
                roster_slot_id=item.roster_slot_id,
                before_team_member_id=item.before_team_member_id,
                after_team_member_id=item.after_team_member_id,
                before_manual_override=item.before_manual_override,
                after_manual_override=item.after_manual_override,
                before_comment=item.before_comment,
                after_comment=item.after_comment,
                outcome=item.outcome,  # type: ignore[arg-type]
                findings=item.findings or [],
                refusal_code=item.refusal_code,
            )
            for item in row.items
        ],
    )


def _change_set_response(row: RosterChangeSet):
    body = jsonable_encoder(_change_set_read(row))
    if row.status == "refused":
        return JSONResponse(status_code=409, content=body)
    return body


@router.post("/{planning_period_id}/change-sets")
def post_roster_change_set(
    planning_period_id: int,
    payload: RosterChangeSetCreate,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        change_set = apply_roster_change_set(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            items=[
                RosterChangeInput(
                    roster_slot_id=item.roster_slot_id,
                    team_member_id=item.team_member_id,
                    manual_override=item.manual_override,
                    comment=item.comment,
                )
                for item in payload.items
            ],
            mode=payload.mode,
            actor=user.email,
            source="ui",
            created_by_user_id=user.id,
            label=payload.label,
        )
    except RosterChangeSetError as exc:
        status = 422 if exc.code == "TOO_MANY_ITEMS" else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
    return _change_set_response(change_set)


@router.get("/{planning_period_id}/change-sets", response_model=list[RosterChangeSetRead])
def get_roster_change_sets(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    rows = list_roster_change_sets(
        db,
        planning_period_id,
        shift_group_id,
        organization_id=user.organization_id,
        limit=limit,
    )
    loaded = db.scalars(
        select(RosterChangeSet).where(RosterChangeSet.id.in_([row.id for row in rows] or [-1])).options(selectinload(RosterChangeSet.items))
    ).all()
    by_id = {row.id: row for row in loaded}
    return [_change_set_read(by_id[row.id]) for row in rows if row.id in by_id]


@router.post("/change-sets/{change_set_id}/revert")
def post_revert_roster_change_set(
    change_set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    original = db.get(RosterChangeSet, change_set_id)
    if original is None or original.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Roster change set not found")
    try:
        assert_planning_shift_group_scope(db, user, original.shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        change_set = revert_roster_change_set(
            db,
            change_set_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="revert",
            created_by_user_id=user.id,
        )
    except RosterChangeSetError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
    return _change_set_response(change_set)


@router.put("/assignments", response_model=RosterSlotAssignmentRead)
def put_roster_slot_assignment(
    payload: RosterSlotAssignmentUpsert,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    slot = db.get(RosterSlot, payload.roster_slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Roster slot not found")
    resolved_shift_group_id = _resolve_assignment_shift_group_id(
        db,
        slot=slot,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
    )
    try:
        assert_planning_shift_group_scope(db, user, resolved_shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    _assert_roster_editable(
        db,
        planning_period_id=slot.planning_period_id,
        shift_group_id=resolved_shift_group_id,
        organization_id=user.organization_id,
    )
    change_set = apply_roster_change_set(
        db,
        organization_id=user.organization_id,
        planning_period_id=slot.planning_period_id,
        shift_group_id=resolved_shift_group_id,
        items=[
            RosterChangeInput(
                roster_slot_id=payload.roster_slot_id,
                team_member_id=payload.team_member_id,
                manual_override=payload.manual_override,
                comment=payload.comment,
            )
        ],
        mode="all_or_nothing",
        actor=user.email,
        source="ui",
        created_by_user_id=user.id,
    )
    item = change_set.items[0]
    if change_set.status == "refused":
        detail = legacy_refusal_message(item)
        if item.refusal_code == "PUBLISHED":
            raise HTTPException(
                status_code=403,
                detail="Roster assignments are read-only while this shift group's plan is published",
            )
        if detail == "Roster slot not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == payload.roster_slot_id)
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Roster slot not found")
    body = RosterSlotAssignmentRead.model_validate(assignment)
    body.change_set_id = change_set.id
    return body


@router.post("/assignments/clear", response_model=DeletedFlagRead)
def clear_assignment(
    payload: RosterSlotAssignmentClear,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    slot = db.get(RosterSlot, payload.roster_slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Roster slot not found")
    resolved_shift_group_id = _resolve_assignment_shift_group_id(
        db,
        slot=slot,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
    )
    try:
        assert_planning_shift_group_scope(db, user, resolved_shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    _assert_roster_editable(
        db,
        planning_period_id=slot.planning_period_id,
        shift_group_id=resolved_shift_group_id,
        organization_id=user.organization_id,
    )
    change_set = apply_roster_change_set(
        db,
        organization_id=user.organization_id,
        planning_period_id=slot.planning_period_id,
        shift_group_id=resolved_shift_group_id,
        items=[RosterChangeInput(roster_slot_id=payload.roster_slot_id, team_member_id=None)],
        mode="all_or_nothing",
        actor=user.email,
        source="ui",
        created_by_user_id=user.id,
    )
    item = change_set.items[0]
    if item.refusal_code == "PUBLISHED":
        raise HTTPException(
            status_code=403,
            detail="Roster assignments are read-only while this shift group's plan is published",
        )
    deleted = item.outcome == "applied" and item.before_team_member_id is not None and item.after_team_member_id is None
    return DeletedFlagRead(deleted=deleted, change_set_id=change_set.id)


@export_router.get(
    "/exports/roster-matrix/{planning_period_id}.xlsx",
    response_class=Response,
    responses=XLSX_RESPONSES,
)
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


@export_router.get(
    "/exports/duty-activity/works-council/{planning_period_id}.xlsx",
    response_class=Response,
    responses=XLSX_RESPONSES,
)
def get_works_council_duty_xlsx(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        body = export_works_council_duty_utilization_xlsx(
            db, planning_period_id, organization_id=user.organization_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="duty-activity-works-council-{planning_period_id}.xlsx"'
        },
    )


@export_router.get(
    "/exports/duty-activity/works-council/{planning_period_id}.pdf",
    response_class=Response,
    responses=PDF_RESPONSES,
)
def get_works_council_duty_pdf(
    planning_period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        body = export_works_council_duty_utilization_pdf(
            db, planning_period_id, organization_id=user.organization_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="duty-activity-works-council-{planning_period_id}.pdf"'
        },
    )


@export_router.get(
    "/exports/roster-matrix/{planning_period_id}.pdf",
    response_class=Response,
    responses=PDF_RESPONSES,
)
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


@export_router.get(
    "/exports/roster-slots/{roster_slot_id}.ics",
    response_class=Response,
    responses=ICS_RESPONSES,
)
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


@export_router.get("/exports/my-shifts.ics", response_class=Response, responses=ICS_RESPONSES)
def get_my_shifts_ics(
    shift_group_id: int = Query(...),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    member = _require_team_member_export_user(db, user)
    try:
        assert_team_member_shift_group_access(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        resolved_start, resolved_end = resolve_ics_date_range(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        body = export_member_shifts_ics(
            db,
            organization_id=user.organization_id,
            team_member_id=member.id,
            shift_group_id=shift_group_id,
            start_date=resolved_start,
            end_date=resolved_end,
            calendar_name="My shifts",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if resolved_start is not None and resolved_end is not None:
        filename = f"my-shifts-{resolved_start.isoformat()}_{resolved_end.isoformat()}.ics"
    else:
        filename = "my-shifts.ics"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.get(
    "/exports/my-shifts/{planning_period_id}.ics",
    response_class=Response,
    responses=ICS_RESPONSES,
)
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
