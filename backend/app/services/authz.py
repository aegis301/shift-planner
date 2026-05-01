from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, DoctorShiftGroup, ShiftGroup, User, UserShiftGroup

ROLE_ADMIN = "admin"
ROLE_PLANNER = "planner"
ROLE_DOCTOR = "doctor"
ROLE_APPLICANT = "applicant"


def is_admin(user: User) -> bool:
    return user.role == ROLE_ADMIN


def is_shift_planner_role(user: User) -> bool:
    return user.role == ROLE_PLANNER


def can_use_planning_ui(user: User) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_PLANNER)


def can_access_doctor_portal(db: Session, user: User) -> bool:
    return get_linked_doctor(db, user.id) is not None


def is_pure_doctor(user: User) -> bool:
    return user.role == ROLE_DOCTOR


def is_applicant(user: User) -> bool:
    return user.role == ROLE_APPLICANT


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


def planner_shift_group_ids(db: Session, user: User) -> set[int]:
    if is_admin(user):
        return set(
            db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == user.organization_id)).all()
        )
    if is_shift_planner_role(user):
        stmt = (
            select(UserShiftGroup.shift_group_id)
            .join(ShiftGroup, ShiftGroup.id == UserShiftGroup.shift_group_id)
            .where(UserShiftGroup.user_id == user.id, ShiftGroup.organization_id == user.organization_id)
        )
        return set(db.scalars(stmt).all())
    return set()


def require_shift_group_id_for_planner_scope(user: User, shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise ValueError("shift_group_id is required for this account")
    return shift_group_id


def assert_planning_shift_group_scope(db: Session, user: User, shift_group_id: int | None) -> None:
    if not can_use_planning_ui(user):
        raise PermissionError("Planning access required")
    if is_admin(user):
        if shift_group_id is None:
            return
        group = db.get(ShiftGroup, shift_group_id)
        if group is None or group.organization_id != user.organization_id:
            raise PermissionError("Shift group not found")
        return
    allowed = planner_shift_group_ids(db, user)
    if not allowed:
        raise PermissionError("No shift groups assigned for planning")
    if shift_group_id is None:
        raise PermissionError("shift_group_id is required")
    if shift_group_id not in allowed:
        raise PermissionError("Not a member of this shift group")


def require_shift_group_id_for_doctor(shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise ValueError("shift_group_id is required for doctor accounts")
    return shift_group_id


def assert_doctor_shift_group_access(db: Session, user: User, shift_group_id: int) -> Doctor:
    if can_use_planning_ui(user) and get_linked_doctor(db, user.id) is None:
        raise AssertionError("assert_doctor_shift_group_access is for linked doctor accounts")
    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        raise PermissionError("Doctor profile is not linked to this account")
    if doctor.organization_id != user.organization_id:
        raise PermissionError("Doctor profile is not linked to this account")
    if shift_group_id not in doctor_shift_group_ids(db, doctor.id):
        raise PermissionError("Not a member of this shift group")
    return doctor


def assert_doctor_cell_access(user: User, doctor: Doctor, payload_doctor_id: int) -> None:
    if can_use_planning_ui(user):
        return
    if payload_doctor_id != doctor.id:
        raise PermissionError("Can only edit your own planning row")


def roles_allowed_for_doctor_user_link() -> set[str]:
    return {ROLE_ADMIN, ROLE_PLANNER, ROLE_DOCTOR, ROLE_APPLICANT}


def use_doctor_filtered_matrix_view(db: Session, user: User) -> bool:
    if is_admin(user):
        return False
    if is_pure_doctor(user):
        return True
    if is_shift_planner_role(user) and get_linked_doctor(db, user.id) is not None:
        return True
    return False
