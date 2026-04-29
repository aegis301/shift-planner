import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, DoctorPeriodNote, PlanningCell, PlanningPeriod, PlanningShiftIntent
from app.schemas import (
    DoctorPeriodNoteUpsert,
    MatrixDay,
    MatrixDoctor,
    MatrixTemplateSlotDay,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellRead,
    PlanningCellUpsert,
    PlanningMatrixRead,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
    PlanningShiftIntentUpsert,
    ShiftTemplateRead,
)
from app.services.audit import record_audit
from app.services.shift_groups import (
    active_doctor_ids_in_shift_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
)
from app.services.shift_templates import generate_slots_for_month, list_shift_templates


def _cell_date_in_period(period: PlanningPeriod, cell_date: date) -> bool:
    return cell_date.year == period.year and cell_date.month == period.month


def list_planning_cells(db: Session, *, planning_period_id: int) -> list[PlanningCell]:
    stmt = (
        select(PlanningCell)
        .where(PlanningCell.planning_period_id == planning_period_id)
        .order_by(PlanningCell.cell_date, PlanningCell.doctor_id)
    )
    return list(db.scalars(stmt))


def list_planning_shift_intents(db: Session, *, planning_period_id: int) -> list[PlanningShiftIntent]:
    stmt = (
        select(PlanningShiftIntent)
        .where(PlanningShiftIntent.planning_period_id == planning_period_id)
        .order_by(
            PlanningShiftIntent.cell_date,
            PlanningShiftIntent.doctor_id,
            PlanningShiftIntent.shift_template_id,
        )
    )
    return list(db.scalars(stmt))


def get_planning_matrix(db: Session, planning_period_id: int, *, shift_group_id: int | None = None) -> PlanningMatrixRead:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    doctors = list(db.scalars(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.name)))
    group_template_ids: set[int] = set()
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id)
        allowed_doctor_ids = active_doctor_ids_in_shift_group(db, shift_group_id)
        doctors = [doctor for doctor in doctors if doctor.id in allowed_doctor_ids]
        group_template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    days = [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]
    cells = list_planning_cells(db, planning_period_id=planning_period_id)
    all_intents = list_planning_shift_intents(db, planning_period_id=planning_period_id)
    shift_templates_out: list[ShiftTemplateRead] = []
    shift_intents_out: list[PlanningShiftIntentRead] = []
    template_slot_days: list[MatrixTemplateSlotDay] = []
    if shift_group_id is not None:
        allowed_doctor_ids = {doctor.id for doctor in doctors}
        cells = [cell for cell in cells if cell.doctor_id in allowed_doctor_ids]
        shift_intents_out = [
            PlanningShiftIntentRead.model_validate(row)
            for row in all_intents
            if row.shift_group_id == shift_group_id and row.doctor_id in allowed_doctor_ids
        ]
        templates = list_shift_templates(db, active_only=True)
        by_id = {template.id: template for template in templates}
        shift_templates_out = [
            ShiftTemplateRead.model_validate(by_id[tid])
            for tid in sorted(group_template_ids)
            if tid in by_id
        ]
        slot_pairs: set[tuple[date, int]] = set()
        for slot in generate_slots_for_month(db, year=period.year, month=period.month):
            if slot.template_id in group_template_ids:
                slot_pairs.add((slot.slot_date, slot.template_id))
        template_slot_days = [
            MatrixTemplateSlotDay(cell_date=d, shift_template_id=tid) for d, tid in sorted(slot_pairs)
        ]
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
        shift_templates=shift_templates_out,
        shift_intents=shift_intents_out,
        template_slot_days=template_slot_days,
    )


def upsert_planning_cell(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    actor: str,
    source: str,
) -> PlanningCell:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")
    if not _cell_date_in_period(period, payload.cell_date):
        raise ValueError("Cell date is outside the planning period month")
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
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")
    for cell_payload in payload.cells:
        if not _cell_date_in_period(period, cell_payload.cell_date):
            raise ValueError("Cell date is outside the planning period month")
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


def bulk_upsert_planning_shift_intents(
    db: Session,
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    *,
    actor: str,
    source: str,
) -> list[PlanningShiftIntent]:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")
    out: list[PlanningShiftIntent] = []
    for item in payload.intents:
        if not _cell_date_in_period(period, item.cell_date):
            raise ValueError("Cell date is outside the planning period month")
        require_shift_group(db, item.shift_group_id)
        allowed_doctors = active_doctor_ids_in_shift_group(db, item.shift_group_id)
        if item.doctor_id not in allowed_doctors:
            raise ValueError("Doctor is not a member of this shift group")
        allowed_templates = shift_template_ids_in_shift_group(db, item.shift_group_id)
        if item.shift_template_id not in allowed_templates:
            raise ValueError("Shift template is not linked to this shift group")
        existing = db.scalar(
            select(PlanningShiftIntent).where(
                PlanningShiftIntent.planning_period_id == planning_period_id,
                PlanningShiftIntent.doctor_id == item.doctor_id,
                PlanningShiftIntent.cell_date == item.cell_date,
                PlanningShiftIntent.shift_group_id == item.shift_group_id,
                PlanningShiftIntent.shift_template_id == item.shift_template_id,
            )
        )
        if item.kind is None:
            if existing is not None:
                record_audit(
                    db,
                    actor=actor,
                    source=source,
                    action="delete",
                    entity_type="planning_shift_intent",
                    entity_id=existing.id,
                    details={
                        "planning_period_id": planning_period_id,
                        "doctor_id": item.doctor_id,
                        "cell_date": item.cell_date.isoformat(),
                    },
                )
                db.delete(existing)
            continue
        if existing is None:
            row = PlanningShiftIntent(
                planning_period_id=planning_period_id,
                doctor_id=item.doctor_id,
                cell_date=item.cell_date,
                shift_group_id=item.shift_group_id,
                shift_template_id=item.shift_template_id,
                kind=item.kind,
                source=source,
            )
            db.add(row)
            db.flush()
            record_audit(
                db,
                actor=actor,
                source=source,
                action="create",
                entity_type="planning_shift_intent",
                entity_id=row.id,
                details={
                    "planning_period_id": planning_period_id,
                    "doctor_id": item.doctor_id,
                    "cell_date": item.cell_date.isoformat(),
                    "shift_template_id": item.shift_template_id,
                    "kind": item.kind,
                },
            )
            out.append(row)
        else:
            existing.kind = item.kind
            existing.source = source
            db.flush()
            record_audit(
                db,
                actor=actor,
                source=source,
                action="update",
                entity_type="planning_shift_intent",
                entity_id=existing.id,
                details={
                    "planning_period_id": planning_period_id,
                    "doctor_id": item.doctor_id,
                    "kind": item.kind,
                },
            )
            out.append(existing)
    db.commit()
    for row in out:
        db.refresh(row)
    return out

