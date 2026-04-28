from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor
from app.schemas import DoctorCreate, DoctorUpdate
from app.services.audit import record_audit


def list_doctors(db: Session, *, active_only: bool = False) -> list[Doctor]:
    stmt = select(Doctor).order_by(Doctor.name)
    if active_only:
        stmt = stmt.where(Doctor.is_active.is_(True))
    return list(db.scalars(stmt))


def create_doctor(db: Session, payload: DoctorCreate, *, actor: str, source: str) -> Doctor:
    doctor = Doctor(**payload.model_dump())
    db.add(doctor)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="doctor", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return doctor


def update_doctor(db: Session, doctor_id: int, payload: DoctorUpdate, *, actor: str, source: str) -> Doctor | None:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(doctor, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="doctor", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return doctor

