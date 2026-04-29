from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Doctor,
    DoctorShiftGroup,
    ShiftGroup,
    ShiftGroupShiftTemplate,
    ShiftTemplate,
)
from app.schemas import ShiftGroupCreate, ShiftGroupUpdate
from app.services.audit import record_audit


def list_shift_template_ids_with_any_group(db: Session) -> set[int]:
    rows = db.scalars(select(ShiftGroupShiftTemplate.shift_template_id).distinct()).all()
    return set(rows)


def doctor_may_cover_template(db: Session, *, doctor_id: int, shift_template_id: int | None) -> bool:
    if shift_template_id is None:
        return True
    if shift_template_id not in list_shift_template_ids_with_any_group(db):
        return True
    stmt = (
        select(DoctorShiftGroup.id)
        .join(ShiftGroupShiftTemplate, ShiftGroupShiftTemplate.shift_group_id == DoctorShiftGroup.shift_group_id)
        .where(
            DoctorShiftGroup.doctor_id == doctor_id,
            ShiftGroupShiftTemplate.shift_template_id == shift_template_id,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def get_shift_group_or_none(db: Session, shift_group_id: int) -> ShiftGroup | None:
    return db.get(ShiftGroup, shift_group_id)


def require_shift_group(db: Session, shift_group_id: int) -> ShiftGroup:
    group = get_shift_group_or_none(db, shift_group_id)
    if group is None:
        raise ValueError("Shift group not found")
    return group


def active_doctor_ids_in_shift_group(db: Session, shift_group_id: int) -> set[int]:
    stmt = (
        select(DoctorShiftGroup.doctor_id)
        .join(Doctor, Doctor.id == DoctorShiftGroup.doctor_id)
        .where(DoctorShiftGroup.shift_group_id == shift_group_id, Doctor.is_active.is_(True))
    )
    return set(db.scalars(stmt).all())


def shift_template_ids_in_shift_group(db: Session, shift_group_id: int) -> set[int]:
    stmt = select(ShiftGroupShiftTemplate.shift_template_id).where(ShiftGroupShiftTemplate.shift_group_id == shift_group_id)
    return set(db.scalars(stmt).all())


def list_shift_groups(db: Session, *, active_only: bool = False) -> list[ShiftGroup]:
    stmt = select(ShiftGroup).options(joinedload(ShiftGroup.doctor_links), joinedload(ShiftGroup.template_links))
    if active_only:
        stmt = stmt.where(ShiftGroup.is_active.is_(True))
    stmt = stmt.order_by(ShiftGroup.display_order, ShiftGroup.code)
    return list(db.scalars(stmt).unique())


def create_shift_group(db: Session, payload: ShiftGroupCreate, *, actor: str, source: str) -> ShiftGroup:
    group = ShiftGroup(
        code=payload.code,
        name_de=payload.name_de,
        name_en=payload.name_en,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(group)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="shift_group", entity_id=group.id)
    db.commit()
    db.refresh(group)
    return group


def update_shift_group(
    db: Session, shift_group_id: int, payload: ShiftGroupUpdate, *, actor: str, source: str
) -> ShiftGroup | None:
    group = db.get(ShiftGroup, shift_group_id)
    if group is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="shift_group", entity_id=group.id)
    db.commit()
    db.refresh(group)
    return group


def delete_shift_group(db: Session, shift_group_id: int, *, actor: str, source: str) -> bool:
    group = db.get(ShiftGroup, shift_group_id)
    if group is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="shift_group",
        entity_id=group.id,
        details={"code": group.code},
    )
    db.delete(group)
    db.commit()
    return True


def replace_group_doctors(db: Session, shift_group_id: int, doctor_ids: list[int], *, actor: str, source: str) -> None:
    require_shift_group(db, shift_group_id)
    db.execute(delete(DoctorShiftGroup).where(DoctorShiftGroup.shift_group_id == shift_group_id))
    for doctor_id in sorted(set(doctor_ids)):
        db.add(DoctorShiftGroup(doctor_id=doctor_id, shift_group_id=shift_group_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="shift_group_doctors",
        entity_id=shift_group_id,
        details={"doctor_ids": sorted(set(doctor_ids))},
    )
    db.commit()


def replace_group_shift_templates(
    db: Session, shift_group_id: int, shift_template_ids: list[int], *, actor: str, source: str
) -> None:
    require_shift_group(db, shift_group_id)
    for tid in set(shift_template_ids):
        if db.get(ShiftTemplate, tid) is None:
            raise ValueError(f"Shift template not found: {tid}")
    db.execute(delete(ShiftGroupShiftTemplate).where(ShiftGroupShiftTemplate.shift_group_id == shift_group_id))
    for template_id in sorted(set(shift_template_ids)):
        db.add(ShiftGroupShiftTemplate(shift_group_id=shift_group_id, shift_template_id=template_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="shift_group_templates",
        entity_id=shift_group_id,
        details={"shift_template_ids": sorted(set(shift_template_ids))},
    )
    db.commit()


def replace_doctor_shift_groups(db: Session, doctor_id: int, shift_group_ids: list[int], *, actor: str, source: str) -> None:
    if db.get(Doctor, doctor_id) is None:
        raise ValueError("Doctor not found")
    for gid in set(shift_group_ids):
        require_shift_group(db, gid)
    db.execute(delete(DoctorShiftGroup).where(DoctorShiftGroup.doctor_id == doctor_id))
    for shift_group_id in sorted(set(shift_group_ids)):
        db.add(DoctorShiftGroup(doctor_id=doctor_id, shift_group_id=shift_group_id))
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace_members",
        entity_type="doctor_shift_groups",
        entity_id=doctor_id,
        details={"shift_group_ids": sorted(set(shift_group_ids))},
    )
    db.commit()
