from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Doctor, DoctorPeriodNote, DoctorShiftGroup, PlanningCell, RosterSlotAssignment, User
from app.schemas import DoctorCreate, DoctorRead, DoctorSelfUpdate, DoctorUpdate
from app.services.audit import record_audit
from app.services.authz import roles_allowed_for_doctor_user_link
from app.services.org_limits import assert_org_allows_doctor_user_link
from app.services.shift_groups import replace_doctor_shift_groups
from app.services.tenancy import get_organization

_MISSING = object()


def list_doctors(db: Session, *, organization_id: int, active_only: bool = False) -> list[Doctor]:
    stmt = (
        select(Doctor)
        .options(joinedload(Doctor.shift_group_links))
        .where(Doctor.organization_id == organization_id)
        .order_by(Doctor.last_name, Doctor.first_name)
    )
    if active_only:
        stmt = stmt.where(Doctor.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def list_doctors_for_planner(db: Session, user: User, *, active_only: bool = False) -> list[Doctor]:
    from app.services.authz import is_admin, planner_shift_group_ids

    if is_admin(user):
        return list_doctors(db, organization_id=user.organization_id, active_only=active_only)
    gids = planner_shift_group_ids(db, user)
    if not gids:
        return []
    stmt = (
        select(Doctor)
        .options(joinedload(Doctor.shift_group_links))
        .where(Doctor.organization_id == user.organization_id)
        .join(DoctorShiftGroup)
        .where(DoctorShiftGroup.shift_group_id.in_(gids))
        .distinct()
        .order_by(Doctor.last_name, Doctor.first_name)
    )
    if active_only:
        stmt = stmt.where(Doctor.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def doctor_to_read(doctor: Doctor) -> DoctorRead:
    link_ids = sorted({link.shift_group_id for link in doctor.shift_group_links})
    return DoctorRead(
        id=doctor.id,
        first_name=doctor.first_name,
        last_name=doctor.last_name,
        email=doctor.email,
        employment_percentage=doctor.employment_percentage,
        notes=doctor.notes,
        shift_group_ids=link_ids,
        user_id=doctor.user_id,
        is_active=doctor.is_active,
        created_at=doctor.created_at,
    )


def _apply_doctor_user_id(db: Session, doctor: Doctor, user_id: int | None) -> None:
    if user_id is None:
        doctor.user_id = None
        db.flush()
        return
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")
    if user.role not in roles_allowed_for_doctor_user_link():
        raise ValueError("User role cannot be linked to a doctor profile")
    if user.organization_id != doctor.organization_id:
        raise ValueError("User must belong to the same organization as the doctor")
    taken = db.scalar(select(Doctor).where(Doctor.user_id == user_id, Doctor.id != doctor.id))
    if taken is not None:
        raise ValueError("User is already linked to another doctor")
    if doctor.user_id is None and user_id is not None:
        org = get_organization(db, doctor.organization_id)
        if org is not None:
            assert_org_allows_doctor_user_link(db, org)
    doctor.user_id = user_id
    db.flush()


def create_doctor(
    db: Session, payload: DoctorCreate, *, organization_id: int, actor: str, source: str
) -> Doctor:
    data = payload.model_dump(exclude={"shift_group_ids", "user_id"})
    doctor = Doctor(**data, organization_id=organization_id)
    db.add(doctor)
    db.flush()
    try:
        if payload.user_id is not None:
            _apply_doctor_user_id(db, doctor, payload.user_id)
        record_audit(db, actor=actor, source=source, action="create", entity_type="doctor", entity_id=doctor.id)
        db.commit()
    except ValueError:
        db.rollback()
        raise
    db.refresh(doctor)
    if payload.shift_group_ids:
        replace_doctor_shift_groups(db, doctor.id, payload.shift_group_ids, actor=actor, source=source)
    db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor


def update_doctor(
    db: Session, doctor_id: int, payload: DoctorUpdate, *, organization_id: int, actor: str, source: str
) -> Doctor | None:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.organization_id != organization_id:
        return None
    raw = payload.model_dump(exclude_unset=True)
    group_ids = raw.pop("shift_group_ids", None)
    user_id_raw = raw.pop("user_id", _MISSING)
    for key, value in raw.items():
        setattr(doctor, key, value)
    if user_id_raw is not _MISSING:
        try:
            _apply_doctor_user_id(db, doctor, user_id_raw)
        except ValueError:
            db.rollback()
            db.refresh(doctor)
            raise
    record_audit(db, actor=actor, source=source, action="update", entity_type="doctor", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    if group_ids is not None:
        replace_doctor_shift_groups(db, doctor_id, group_ids, actor=actor, source=source)
        db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor


def update_doctor_self(db: Session, doctor: Doctor, payload: DoctorSelfUpdate, *, actor: str, source: str) -> Doctor:
    raw = payload.model_dump(exclude_unset=True)
    if "email" in raw:
        other = db.scalar(
            select(Doctor).where(
                Doctor.email == raw["email"],
                Doctor.id != doctor.id,
                Doctor.organization_id == doctor.organization_id,
            )
        )
        if other is not None:
            raise ValueError("Email already in use")
    for key, value in raw.items():
        setattr(doctor, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="doctor_self", entity_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return doctor


def delete_doctor(db: Session, doctor_id: int, *, organization_id: int, actor: str, source: str) -> bool:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.organization_id != organization_id:
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
