import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Doctor, PlanningPeriod, RosterSlot, RosterSlotAssignment
from app.schemas import (
    MatrixDay,
    MatrixDoctor,
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    RosterSlotRead,
)
from app.services.audit import record_audit
from app.services.matrix import list_planning_cells
from app.services.shift_templates import generate_slots_for_month, list_shift_templates


def _period_days(period: PlanningPeriod) -> list[MatrixDay]:
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    return [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]


def list_roster_slots(db: Session, *, planning_period_id: int) -> list[RosterSlot]:
    stmt = (
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.shift_variant))
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_template_id, RosterSlot.shift_variant_id)
    )
    return list(db.scalars(stmt))


def list_roster_slot_assignments(db: Session, *, planning_period_id: int) -> list[RosterSlotAssignment]:
    stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot)
        .options(joinedload(RosterSlotAssignment.roster_slot), joinedload(RosterSlotAssignment.doctor))
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_template_id, RosterSlot.shift_variant_id)
    )
    return list(db.scalars(stmt))


def ensure_roster_slots_for_period(db: Session, planning_period_id: int) -> list[RosterSlot]:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    generated_slots = generate_slots_for_month(db, year=period.year, month=period.month)
    if not generated_slots:
        return []

    existing = {
        (slot.slot_date, slot.shift_variant_id, slot.position)
        for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id))
    }
    for generated in generated_slots:
        key = (generated.slot_date, generated.variant_id, generated.position)
        if key in existing:
            continue
        db.add(
            RosterSlot(
                planning_period_id=planning_period_id,
                shift_template_id=generated.template_id,
                shift_variant_id=generated.variant_id,
                slot_date=generated.slot_date,
                position=generated.position,
                label=generated.label,
                starts_at=generated.starts_at,
                ends_at=generated.ends_at,
                day_class=generated.day_class,
                source="template",
            )
        )
        existing.add(key)
    db.flush()
    return list_roster_slots(db, planning_period_id=planning_period_id)


def reset_roster_slots_for_period(db: Session, planning_period_id: int, *, actor: str, source: str) -> list[RosterSlot]:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")
    slot_ids = list(db.scalars(select(RosterSlot.id).where(RosterSlot.planning_period_id == planning_period_id)))
    if slot_ids:
        for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids))):
            db.delete(assignment)
    for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id)):
        db.delete(slot)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="regenerate",
        entity_type="planning_period_roster_slots",
        entity_id=planning_period_id,
        details={"cleared_slot_count": len(slot_ids)},
    )
    slots = ensure_roster_slots_for_period(db, planning_period_id)
    db.commit()
    return slots


def get_roster_matrix(db: Session, planning_period_id: int) -> RosterMatrixRead:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        raise ValueError("Planning period not found")

    ensure_roster_slots_for_period(db, planning_period_id)
    db.commit()

    doctors = list(db.scalars(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.name)))
    shift_templates = list_shift_templates(db, active_only=True)
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
        shift_templates=shift_templates,
        slots=[_read_slot(slot) for slot in slots],
        assignments=[RosterSlotAssignmentRead.model_validate(assignment) for assignment in assignments],
        planning_cells=planning_cells,
    )


def _read_slot(slot: RosterSlot) -> RosterSlotRead:
    template = slot.shift_template
    variant = slot.shift_variant
    return RosterSlotRead(
        id=slot.id,
        planning_period_id=slot.planning_period_id,
        shift_template_id=slot.shift_template_id,
        shift_variant_id=slot.shift_variant_id,
        slot_date=slot.slot_date,
        position=slot.position,
        label=slot.label,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        day_class=slot.day_class,
        template_code=template.code if template else None,
        template_name_de=template.name_de if template else None,
        template_name_en=template.name_en if template else None,
        variant_label=variant.label if variant else None,
        category=template.category if template else None,
        source=slot.source,
        created_at=slot.created_at,
        updated_at=slot.updated_at,
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
