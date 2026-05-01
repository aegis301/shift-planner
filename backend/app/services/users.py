from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Doctor, ShiftGroup, User, UserShiftGroup
from app.schemas import DoctorSelfUpdate, UserCapabilities, UserRead, UserShiftGroupBrief
from app.services.authz import (
    ROLE_PLANNER,
    can_use_planning_ui,
    get_linked_doctor,
    is_admin,
    list_shift_groups_for_doctor,
)
from app.services.tenancy import ensure_default_organization


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def ensure_admin_user(db: Session, *, email: str, password: str) -> User:
    org = ensure_default_organization(db)
    existing = get_user_by_email(db, email)
    if existing:
        return existing
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role="admin",
        locale="de",
        organization_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def build_user_read(db: Session, user: User) -> UserRead:
    linked = get_linked_doctor(db, user.id)
    doctor_id = linked.id if linked else None
    groups: list[UserShiftGroupBrief] = []
    if linked:
        for g in list_shift_groups_for_doctor(db, linked.id):
            groups.append(UserShiftGroupBrief.model_validate(g))
    planner_groups: list[UserShiftGroupBrief] = []
    if user.role == ROLE_PLANNER:
        stmt = (
            select(ShiftGroup)
            .join(UserShiftGroup, UserShiftGroup.shift_group_id == ShiftGroup.id)
            .where(UserShiftGroup.user_id == user.id, ShiftGroup.organization_id == user.organization_id)
            .order_by(ShiftGroup.display_order, ShiftGroup.code)
        )
        for g in db.scalars(stmt):
            planner_groups.append(UserShiftGroupBrief.model_validate(g))
    caps = UserCapabilities(
        admin=is_admin(user),
        planning=can_use_planning_ui(user),
        doctor_portal=doctor_id is not None,
    )
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        locale=user.locale,
        organization_id=user.organization_id,
        doctor_id=doctor_id,
        shift_groups=groups,
        planner_shift_groups=planner_groups,
        capabilities=caps,
    )


def update_self_doctor_profile(db: Session, user: User, payload: DoctorSelfUpdate) -> Doctor | None:
    from app.services.doctors import update_doctor_self

    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        return None
    return update_doctor_self(db, doctor, payload, actor=user.email, source="rest")

