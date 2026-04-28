import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Doctor, PlanningPeriod, RosterSlot, RosterSlotAssignment, ShiftType
from app.schemas import (
    MatrixDay,
    MatrixDoctor,
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    RosterSlotRead,
    ShiftTypeRead,
)
from app.services.matrix import list_planning_cells
from app.services.audit import record_audit


def _period_days(period: PlanningPeriod) -> list[MatrixDay]:
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    return [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]


def list_roster_slots(db: Session, *, planning_period_id: int) -> list[RosterSlot]:
    stmt = (
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_type))
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_type_id)
    )
    return list(db.scalars(stmt))


def list_roster_slot_assignments(db: Session, *, planning_period_id: int) -> list[RosterSlotAssignment]:
    stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot)
        .options(joinedload(RosterSlotAssignment.roster_slot), joinedload(RosterSlotAssignment.doctor))
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_type_id)
    )
    return list(db.scalars(stmt))


def ensure_roster_slots_for_period(db: Session, planning_period_id: int) -> list[RosterSlot]:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    shift_types = list(db.scalars(select(ShiftType).where(ShiftType.is_active.is_(True)).order_by(ShiftType.code)))
    if not shift_types:
        return []

    existing = {
        (slot.slot_date, slot.shift_type_id, slot.position)
        for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id))
    }
    for day in _period_days(period):
        for shift_type in shift_types:
            key = (day.date, shift_type.id, 1)
            if key in existing:
                continue
            db.add(
                RosterSlot(
                    planning_period_id=planning_period_id,
                    shift_type_id=shift_type.id,
                    slot_date=day.date,
                    position=1,
                    label=shift_type.name_de,
                    source="system",
                )
            )
    db.flush()
    return list_roster_slots(db, planning_period_id=planning_period_id)


def get_roster_matrix(db: Session, planning_period_id: int) -> RosterMatrixRead:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    ensure_roster_slots_for_period(db, planning_period_id)
    db.commit()

    doctors = list(db.scalars(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.name)))
    shift_types = list(db.scalars(select(ShiftType).where(ShiftType.is_active.is_(True)).order_by(ShiftType.code)))
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    assignments = list_roster_slot_assignments(db, planning_period_id=planning_period_id)
    planning_cells = list_planning_cells(db, planning_period_id=planning_period_id)
    return RosterMatrixRead(
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
        days=_period_days(period),
        shift_types=[ShiftTypeRead.model_validate(shift_type) for shift_type in shift_types],
        slots=[RosterSlotRead.model_validate(slot) for slot in slots],
        assignments=[RosterSlotAssignmentRead.model_validate(assignment) for assignment in assignments],
        planning_cells=planning_cells,
    )


def upsert_roster_slot_assignment(
    db: Session,
    payload: RosterSlotAssignmentUpsert,
    *,
    actor: str,
    source: str,
) -> RosterSlotAssignment:
    slot = db.get(RosterSlot, payload.roster_slot_id)
    if slot is None:
        raise ValueError("Roster slot not found")
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == payload.roster_slot_id)
    )
    if assignment is None:
        assignment = RosterSlotAssignment(
            roster_slot_id=payload.roster_slot_id,
            doctor_id=payload.doctor_id,
            comment=payload.comment,
            manual_override=payload.manual_override,
            source=source,
        )
        db.add(assignment)
        action = "create"
    else:
        assignment.doctor_id = payload.doctor_id
        assignment.comment = payload.comment
        assignment.manual_override = payload.manual_override
        assignment.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={
            "planning_period_id": slot.planning_period_id,
            "roster_slot_id": payload.roster_slot_id,
            "doctor_id": payload.doctor_id,
        },
    )
    db.commit()
    db.refresh(assignment)
    return assignment


def clear_roster_slot_assignment(
    db: Session,
    payload: RosterSlotAssignmentClear,
    *,
    actor: str,
    source: str,
) -> bool:
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == payload.roster_slot_id)
    )
    if assignment is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={"roster_slot_id": payload.roster_slot_id},
    )
    db.delete(assignment)
    db.commit()
    return True
