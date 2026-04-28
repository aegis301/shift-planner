from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ShiftType
from app.schemas import ShiftTypeCreate, ShiftTypeUpdate
from app.services.audit import record_audit


def list_shift_types(db: Session, *, active_only: bool = False) -> list[ShiftType]:
    stmt = select(ShiftType).order_by(ShiftType.code)
    if active_only:
        stmt = stmt.where(ShiftType.is_active.is_(True))
    return list(db.scalars(stmt))


def create_shift_type(db: Session, payload: ShiftTypeCreate, *, actor: str, source: str) -> ShiftType:
    shift_type = ShiftType(**payload.model_dump())
    db.add(shift_type)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="shift_type",
        entity_id=shift_type.id,
    )
    db.commit()
    db.refresh(shift_type)
    return shift_type


def update_shift_type(
    db: Session, shift_type_id: int, payload: ShiftTypeUpdate, *, actor: str, source: str
) -> ShiftType | None:
    shift_type = db.get(ShiftType, shift_type_id)
    if shift_type is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(shift_type, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="shift_type", entity_id=shift_type.id)
    db.commit()
    db.refresh(shift_type)
    return shift_type

