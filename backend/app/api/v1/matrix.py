from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellRead,
    PlanningCellUpsert,
    PlanningMatrixRead,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
    TeamMemberPeriodNoteRead,
    TeamMemberPeriodNoteUpsert,
)
from app.services.authz import (
    assert_planning_shift_group_scope,
    assert_team_member_cell_access,
    assert_team_member_shift_group_access,
    can_use_planning_ui,
    get_linked_team_member,
    require_shift_group_id_for_team_member,
    use_team_member_filtered_matrix_view,
)
from app.services.matrix import (
    bulk_upsert_planning_cells,
    bulk_upsert_planning_shift_intents,
    clear_planning_cell,
    get_planning_matrix,
    get_team_member_period_note,
    list_team_member_period_notes,
    save_team_member_period_note,
    upsert_planning_cell,
)
from app.services.planning import can_edit_planning_data, can_team_member_edit_wishes_matrix, get_shift_group_planning_status

router = APIRouter(prefix="/matrix", tags=["matrix"])


def _linked_team_member_or_403(db: Session, user: User):
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=403, detail="Team member profile is not linked to this account")
    return member


def _matrix_access(db: Session, user: User, shift_group_id: int | None) -> None:
    if can_use_planning_ui(user):
        try:
            assert_planning_shift_group_scope(db, user, shift_group_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return
    try:
        require_shift_group_id_for_team_member(shift_group_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        assert_team_member_shift_group_access(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require_shift_group_id_for_write(shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    return shift_group_id


def _team_member_feedback_access(
    db: Session,
    user: User,
    planning_period_id: int,
    shift_group_id: int | None,
    *,
    team_member_portal: bool = False,
) -> int:
    group_id = _require_shift_group_id_for_write(shift_group_id)
    if can_use_planning_ui(user) and not team_member_portal:
        _matrix_access(db, user, group_id)
        row = get_shift_group_planning_status(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=group_id,
            organization_id=user.organization_id,
        )
        if row is None or not can_edit_planning_data(row.status):
            raise HTTPException(
                status_code=403,
                detail="Planning data is read-only while this shift group's plan is published",
            )
        return group_id
    try:
        assert_team_member_shift_group_access(db, user, group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=group_id,
        organization_id=user.organization_id,
    )
    if row is None or not can_team_member_edit_wishes_matrix(row.status):
        raise HTTPException(
            status_code=403,
            detail="Team member wishes are only editable while this shift group's plan is in draft or preliminary status",
        )
    return group_id


def _filter_matrix_to_linked_member(
    db: Session,
    user: User,
    matrix: PlanningMatrixRead,
    *,
    team_member_portal: bool,
) -> PlanningMatrixRead:
    if not use_team_member_filtered_matrix_view(db, user, team_member_portal=team_member_portal):
        return matrix
    member = _linked_team_member_or_403(db, user)
    return matrix.model_copy(
        update={
            "team_members": [row for row in matrix.team_members if row.id == member.id],
            "cells": [row for row in matrix.cells if row.team_member_id == member.id],
            "shift_intents": [row for row in matrix.shift_intents if row.team_member_id == member.id],
        }
    )


def _assert_portal_self_write(
    db: Session,
    user: User,
    team_member_id: int,
    *,
    team_member_portal: bool,
) -> None:
    if can_use_planning_ui(user) and not team_member_portal:
        return
    member = _linked_team_member_or_403(db, user)
    try:
        assert_team_member_cell_access(
            user,
            member,
            team_member_id,
            team_member_portal=team_member_portal,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{planning_period_id}", response_model=PlanningMatrixRead)
def get_matrix(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _matrix_access(db, user, shift_group_id)
    try:
        matrix = get_planning_matrix(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
        return _filter_matrix_to_linked_member(
            db, user, matrix, team_member_portal=team_member_portal
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{planning_period_id}/cells", response_model=PlanningCellRead)
def put_cell(
    planning_period_id: int,
    payload: PlanningCellUpsert,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group_id = _team_member_feedback_access(
        db, user, planning_period_id, shift_group_id, team_member_portal=team_member_portal
    )
    _assert_portal_self_write(
        db, user, payload.team_member_id, team_member_portal=team_member_portal
    )
    try:
        return upsert_planning_cell(
            db,
            planning_period_id,
            payload,
            organization_id=user.organization_id,
            shift_group_id=group_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{planning_period_id}/cells/bulk", response_model=list[PlanningCellRead])
def put_cells_bulk(
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group_id = _team_member_feedback_access(
        db, user, planning_period_id, shift_group_id, team_member_portal=team_member_portal
    )
    for cell in payload.cells:
        _assert_portal_self_write(
            db, user, cell.team_member_id, team_member_portal=team_member_portal
        )
    try:
        return bulk_upsert_planning_cells(
            db,
            planning_period_id,
            payload,
            organization_id=user.organization_id,
            shift_group_id=group_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{planning_period_id}/shift-intents/bulk", response_model=list[PlanningShiftIntentRead])
def put_shift_intents_bulk(
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not can_use_planning_ui(user) or team_member_portal:
        if not payload.intents:
            raise HTTPException(status_code=400, detail="shift_group_id is required")
        group_id = payload.intents[0].shift_group_id
        _team_member_feedback_access(
            db, user, planning_period_id, group_id, team_member_portal=team_member_portal
        )
        for item in payload.intents:
            _assert_portal_self_write(
                db, user, item.team_member_id, team_member_portal=team_member_portal
            )
            try:
                assert_team_member_shift_group_access(db, user, item.shift_group_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        rows = bulk_upsert_planning_shift_intents(
            db, planning_period_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
        return [PlanningShiftIntentRead.model_validate(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{planning_period_id}/cells/clear")
def clear_cell(
    planning_period_id: int,
    payload: PlanningCellClear,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group_id = _team_member_feedback_access(
        db, user, planning_period_id, shift_group_id, team_member_portal=team_member_portal
    )
    _assert_portal_self_write(
        db, user, payload.team_member_id, team_member_portal=team_member_portal
    )
    deleted = clear_planning_cell(
        db,
        planning_period_id,
        payload,
        organization_id=user.organization_id,
        shift_group_id=group_id,
        actor=user.email,
        source="rest",
    )
    return {"deleted": deleted}


@router.get("/{planning_period_id}/notes", response_model=list[TeamMemberPeriodNoteRead])
def get_notes(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _matrix_access(db, user, shift_group_id)
    notes = list_team_member_period_notes(
        db,
        planning_period_id=planning_period_id,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
    )
    if use_team_member_filtered_matrix_view(db, user, team_member_portal=team_member_portal):
        member = _linked_team_member_or_403(db, user)
        notes = [note for note in notes if note.team_member_id == member.id]
    return notes


@router.put("/{planning_period_id}/notes", response_model=TeamMemberPeriodNoteRead)
def put_note(
    planning_period_id: int,
    payload: TeamMemberPeriodNoteUpsert,
    shift_group_id: int | None = Query(default=None),
    team_member_portal: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group_id = _team_member_feedback_access(
        db, user, planning_period_id, shift_group_id, team_member_portal=team_member_portal
    )
    payload_effective = payload
    if not can_use_planning_ui(user) or team_member_portal:
        _assert_portal_self_write(
            db, user, payload.team_member_id, team_member_portal=team_member_portal
        )
        previous = get_team_member_period_note(
            db,
            planning_period_id=planning_period_id,
            team_member_id=payload.team_member_id,
            shift_group_id=group_id,
        )
        payload_effective = payload.model_copy(
            update={"wishes_response_received": previous.wishes_response_received if previous else False}
        )
    return save_team_member_period_note(
        db,
        planning_period_id,
        payload_effective,
        organization_id=user.organization_id,
        shift_group_id=group_id,
        actor=user.email,
        source="rest",
    )
