from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, DoctorShiftGroup, ShiftGroup, User

ROLE_ADMIN = "admin"
ROLE_DOCTOR = "doctor"


def is_planner(user: User) -> bool:
    return user.role == ROLE_ADMIN


def get_linked_doctor(db: Session, user_id: int) -> Doctor | None:
    return db.scalar(select(Doctor).where(Doctor.user_id == user_id))


def doctor_shift_group_ids(db: Session, doctor_id: int) -> set[int]:
    return set(db.scalars(select(DoctorShiftGroup.shift_group_id).where(DoctorShiftGroup.doctor_id == doctor_id)))


def list_shift_groups_for_doctor(db: Session, doctor_id: int) -> list[ShiftGroup]:
    gids = doctor_shift_group_ids(db, doctor_id)
    if not gids:
        return []
    stmt = select(ShiftGroup).where(ShiftGroup.id.in_(gids)).order_by(ShiftGroup.display_order, ShiftGroup.code)
    return list(db.scalars(stmt))


def require_shift_group_id_for_doctor(shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise ValueError("shift_group_id is required for doctor accounts")
    return shift_group_id


def assert_doctor_shift_group_access(db: Session, user: User, shift_group_id: int) -> Doctor:
    if is_planner(user):
        raise AssertionError("assert_doctor_shift_group_access is for doctor role only")
    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        raise PermissionError("Doctor profile is not linked to this account")
    if shift_group_id not in doctor_shift_group_ids(db, doctor.id):
        raise PermissionError("Not a member of this shift group")
    return doctor


def assert_doctor_cell_access(user: User, doctor: Doctor, payload_doctor_id: int) -> None:
    if is_planner(user):
        return
    if payload_doctor_id != doctor.id:
        raise PermissionError("Can only edit your own planning row")
