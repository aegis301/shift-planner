from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Doctor, DoctorPeriodNote, PlanningCell, RosterSlotAssignment
from app.schemas import DoctorCreate, DoctorRead, DoctorUpdate
from app.services.audit import record_audit
from app.services.shift_groups import replace_doctor_shift_groups


def list_doctors(db: Session, *, active_only: bool = False) -> list[Doctor]:
    stmt = select(Doctor).options(joinedload(Doctor.shift_group_links)).order_by(Doctor.name)
    if active_only:
        stmt = stmt.where(Doctor.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def doctor_to_read(doctor: Doctor) -> DoctorRead:
    link_ids = sorted({link.shift_group_id for link in doctor.shift_group_links})
    return DoctorRead(
        id=doctor.id,
        name=doctor.name,
        email=doctor.email,
        employment_percentage=doctor.employment_percentage,
        notes=doctor.notes,
        shift_group_ids=link_ids,
        is_active=doctor.is_active,
        created_at=doctor.created_at,
    )


def create_doctor(db: Session, payload: DoctorCreate, *, actor: str, source: str) -> Doctor:
    data = payload.model_dump(exclude={"shift_group_ids"})
    doctor = Doctor(**data)
    db.add(doctor)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="doctor", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    if payload.shift_group_ids:
        replace_doctor_shift_groups(db, doctor.id, payload.shift_group_ids, actor=actor, source=source)
    db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor


def update_doctor(db: Session, doctor_id: int, payload: DoctorUpdate, *, actor: str, source: str) -> Doctor | None:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        return None
    raw = payload.model_dump(exclude_unset=True)
    group_ids = raw.pop("shift_group_ids", None)
    for key, value in raw.items():
        setattr(doctor, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="doctor", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    if group_ids is not None:
        replace_doctor_shift_groups(db, doctor_id, group_ids, actor=actor, source=source)
        db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor


def delete_doctor(db: Session, doctor_id: int, *, actor: str, source: str) -> bool:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        return False
    assignment_ids = list(db.scalars(select(RosterSlotAssignment.id).where(RosterSlotAssignment.doctor_id == doctor_id)))
    for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.doctor_id == doctor_id)):
        db.delete(assignment)
    for cell in db.scalars(select(PlanningCell).where(PlanningCell.doctor_id == doctor_id)):
        db.delete(cell)
    for note in db.scalars(select(DoctorPeriodNote).where(DoctorPeriodNote.doctor_id == doctor_id)):
        db.delete(note)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="doctor",
        entity_id=doctor.id,
        details={"email": doctor.email, "cleared_assignment_count": len(assignment_ids)},
    )
    db.delete(doctor)
    db.commit()
    return True

