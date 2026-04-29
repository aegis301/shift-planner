import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, DoctorPeriodNote, PlanningCell, PlanningPeriod
from app.schemas import (
    DoctorPeriodNoteUpsert,
    MatrixDay,
    MatrixDoctor,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellRead,
    PlanningCellUpsert,
    PlanningMatrixRead,
)
from app.services.audit import record_audit
from app.services.shift_groups import active_doctor_ids_in_shift_group, require_shift_group


def list_planning_cells(db: Session, *, planning_period_id: int) -> list[PlanningCell]:
    stmt = (
        select(PlanningCell)
        .where(PlanningCell.planning_period_id == planning_period_id)
        .order_by(PlanningCell.cell_date, PlanningCell.doctor_id)
    )
    return list(db.scalars(stmt))


def get_planning_matrix(db: Session, planning_period_id: int, *, shift_group_id: int | None = None) -> PlanningMatrixRead:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    doctors = list(db.scalars(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.name)))
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id)
        allowed_doctor_ids = active_doctor_ids_in_shift_group(db, shift_group_id)
        doctors = [doctor for doctor in doctors if doctor.id in allowed_doctor_ids]
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    days = [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]
    cells = list_planning_cells(db, planning_period_id=planning_period_id)
    if shift_group_id is not None:
        allowed_doctor_ids = {doctor.id for doctor in doctors}
        cells = [cell for cell in cells if cell.doctor_id in allowed_doctor_ids]
    return PlanningMatrixRead(
        planning_period=period,
        doctors=[
            MatrixDoctor(
                id=doctor.id,
                name=doctor.name,
                email=doctor.email,
                employment_percentage=doctor.employment_percentage,
            )
            for doctor in doctors
        ],
        days=days,
        cells=[PlanningCellRead.model_validate(cell) for cell in cells],
    )


def upsert_planning_cell(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    actor: str,
    source: str,
) -> PlanningCell:
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.doctor_id == payload.doctor_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        cell = PlanningCell(
            planning_period_id=planning_period_id,
            doctor_id=payload.doctor_id,
            cell_date=payload.cell_date,
            status=payload.status,
            comment=payload.comment,
            source=source,
        )
        db.add(cell)
        action = "create"
    else:
        cell.status = payload.status
        cell.comment = payload.comment
        cell.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="planning_cell",
        entity_id=cell.id,
        details={
            "planning_period_id": planning_period_id,
            "doctor_id": payload.doctor_id,
            "cell_date": payload.cell_date.isoformat(),
            "status": payload.status,
        },
    )
    db.commit()
    db.refresh(cell)
    return cell


def bulk_upsert_planning_cells(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    *,
    actor: str,
    source: str,
) -> list[PlanningCell]:
    cells = [
        _upsert_planning_cell_no_commit(db, planning_period_id, cell_payload, actor=actor, source=source)
        for cell_payload in payload.cells
    ]
    db.commit()
    for cell in cells:
        db.refresh(cell)
    return cells


def _upsert_planning_cell_no_commit(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    actor: str,
    source: str,
) -> PlanningCell:
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.doctor_id == payload.doctor_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        cell = PlanningCell(
            planning_period_id=planning_period_id,
            doctor_id=payload.doctor_id,
            cell_date=payload.cell_date,
            status=payload.status,
            comment=payload.comment,
            source=source,
        )
        db.add(cell)
        action = "create"
    else:
        cell.status = payload.status
        cell.comment = payload.comment
        cell.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "doctor_id": payload.doctor_id},
    )
    return cell


def clear_planning_cell(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellClear,
    *,
    actor: str,
    source: str,
) -> bool:
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.doctor_id == payload.doctor_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "doctor_id": payload.doctor_id},
    )
    db.delete(cell)
    db.commit()
    return True


def list_doctor_period_notes(
    db: Session, *, planning_period_id: int, shift_group_id: int | None = None
) -> list[DoctorPeriodNote]:
    stmt = select(DoctorPeriodNote).where(DoctorPeriodNote.planning_period_id == planning_period_id)
    notes = list(db.scalars(stmt.order_by(DoctorPeriodNote.doctor_id)))
    if shift_group_id is None:
        return notes
    require_shift_group(db, shift_group_id)
    allowed_doctor_ids = active_doctor_ids_in_shift_group(db, shift_group_id)
    return [note for note in notes if note.doctor_id in allowed_doctor_ids]


def get_doctor_period_note(db: Session, *, planning_period_id: int, doctor_id: int) -> DoctorPeriodNote | None:
    return db.scalar(
        select(DoctorPeriodNote).where(
            DoctorPeriodNote.planning_period_id == planning_period_id,
            DoctorPeriodNote.doctor_id == doctor_id,
        )
    )


def save_doctor_period_note(
    db: Session,
    planning_period_id: int,
    payload: DoctorPeriodNoteUpsert,
    *,
    actor: str,
    source: str,
) -> DoctorPeriodNote:
    note = get_doctor_period_note(db, planning_period_id=planning_period_id, doctor_id=payload.doctor_id)
    if note is None:
        note = DoctorPeriodNote(planning_period_id=planning_period_id, **payload.model_dump())
        db.add(note)
        action = "create"
    else:
        note.source_text = payload.source_text
        note.summary = payload.summary
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="doctor_period_note",
        entity_id=note.id,
        details={"planning_period_id": planning_period_id, "doctor_id": payload.doctor_id},
    )
    db.commit()
    db.refresh(note)
    return note

