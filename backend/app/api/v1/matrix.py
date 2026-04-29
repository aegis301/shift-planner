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
)
from app.services.matrix import (
    bulk_upsert_planning_cells,
    clear_planning_cell,
    get_planning_matrix,
    list_doctor_period_notes,
    save_doctor_period_note,
    upsert_planning_cell,
)

router = APIRouter(prefix="/matrix", tags=["matrix"])


@router.get("/{planning_period_id}", response_model=PlanningMatrixRead)
def get_matrix(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return get_planning_matrix(db, planning_period_id, shift_group_id=shift_group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{planning_period_id}/cells", response_model=PlanningCellRead)
def put_cell(
    planning_period_id: int,
    payload: PlanningCellUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return upsert_planning_cell(db, planning_period_id, payload, actor=user.email, source="rest")


@router.put("/{planning_period_id}/cells/bulk", response_model=list[PlanningCellRead])
def put_cells_bulk(
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return bulk_upsert_planning_cells(db, planning_period_id, payload, actor=user.email, source="rest")


@router.post("/{planning_period_id}/cells/clear")
def clear_cell(
    planning_period_id: int,
    payload: PlanningCellClear,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = clear_planning_cell(db, planning_period_id, payload, actor=user.email, source="rest")
    return {"deleted": deleted}


@router.get("/{planning_period_id}/notes", response_model=list[DoctorPeriodNoteRead])
def get_notes(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_doctor_period_notes(db, planning_period_id=planning_period_id, shift_group_id=shift_group_id)


@router.put("/{planning_period_id}/notes", response_model=DoctorPeriodNoteRead)
def put_note(
    planning_period_id: int,
    payload: DoctorPeriodNoteUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return save_doctor_period_note(db, planning_period_id, payload, actor=user.email, source="rest")

