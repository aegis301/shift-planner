from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    DoctorPeriodNoteRead,
    DoctorPeriodNoteUpsert,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellRead,
    PlanningCellUpsert,
    PlanningMatrixRead,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
)
from app.services.authz import (
    assert_doctor_cell_access,
    assert_doctor_shift_group_access,
    get_linked_doctor,
    is_planner,
    require_shift_group_id_for_doctor,
)
from app.services.matrix import (
    bulk_upsert_planning_cells,
    bulk_upsert_planning_shift_intents,
    clear_planning_cell,
    get_planning_matrix,
    list_doctor_period_notes,
    save_doctor_period_note,
    upsert_planning_cell,
)

router = APIRouter(prefix="/matrix", tags=["matrix"])


def _doctor_matrix_access(db: Session, user: User, shift_group_id: int | None) -> None:
    if is_planner(user):
        return
    try:
        require_shift_group_id_for_doctor(shift_group_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        assert_doctor_shift_group_access(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _linked_doctor_or_403(db: Session, user: User):
    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        raise HTTPException(status_code=403, detail="Doctor profile is not linked to this account")
    return doctor


@router.get("/{planning_period_id}", response_model=PlanningMatrixRead)
def get_matrix(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _doctor_matrix_access(db, user, shift_group_id)
    try:
        matrix = get_planning_matrix(db, planning_period_id, shift_group_id=shift_group_id)
        if is_planner(user):
            return matrix
        doctor = _linked_doctor_or_403(db, user)
        return matrix.model_copy(
            update={
                "doctors": [row for row in matrix.doctors if row.id == doctor.id],
                "cells": [row for row in matrix.cells if row.doctor_id == doctor.id],
                "shift_intents": [row for row in matrix.shift_intents if row.doctor_id == doctor.id],
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{planning_period_id}/cells", response_model=PlanningCellRead)
def put_cell(
    planning_period_id: int,
    payload: PlanningCellUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        try:
            assert_doctor_cell_access(user, doctor, payload.doctor_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        return upsert_planning_cell(db, planning_period_id, payload, actor=user.email, source="rest")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{planning_period_id}/cells/bulk", response_model=list[PlanningCellRead])
def put_cells_bulk(
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        for cell in payload.cells:
            try:
                assert_doctor_cell_access(user, doctor, cell.doctor_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        return bulk_upsert_planning_cells(db, planning_period_id, payload, actor=user.email, source="rest")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{planning_period_id}/shift-intents/bulk", response_model=list[PlanningShiftIntentRead])
def put_shift_intents_bulk(
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        for item in payload.intents:
            try:
                assert_doctor_cell_access(user, doctor, item.doctor_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            try:
                assert_doctor_shift_group_access(db, user, item.shift_group_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        rows = bulk_upsert_planning_shift_intents(db, planning_period_id, payload, actor=user.email, source="rest")
        return [PlanningShiftIntentRead.model_validate(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{planning_period_id}/cells/clear")
def clear_cell(
    planning_period_id: int,
    payload: PlanningCellClear,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        try:
            assert_doctor_cell_access(user, doctor, payload.doctor_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    deleted = clear_planning_cell(db, planning_period_id, payload, actor=user.email, source="rest")
    return {"deleted": deleted}


@router.get("/{planning_period_id}/notes", response_model=list[DoctorPeriodNoteRead])
def get_notes(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _doctor_matrix_access(db, user, shift_group_id)
    notes = list_doctor_period_notes(db, planning_period_id=planning_period_id, shift_group_id=shift_group_id)
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        notes = [note for note in notes if note.doctor_id == doctor.id]
    return notes


@router.put("/{planning_period_id}/notes", response_model=DoctorPeriodNoteRead)
def put_note(
    planning_period_id: int,
    payload: DoctorPeriodNoteUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_planner(user):
        doctor = _linked_doctor_or_403(db, user)
        try:
            assert_doctor_cell_access(user, doctor, payload.doctor_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    return save_doctor_period_note(db, planning_period_id, payload, actor=user.email, source="rest")
