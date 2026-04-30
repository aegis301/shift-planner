from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Doctor, User
from app.schemas import DoctorSelfUpdate, UserRead, UserShiftGroupBrief
from app.services.authz import get_linked_doctor, list_shift_groups_for_doctor


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
    existing = get_user_by_email(db, email)
    if existing:
        return existing
    user = User(email=email.lower(), hashed_password=hash_password(password), role="admin", locale="de")
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
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        locale=user.locale,
        doctor_id=doctor_id,
        shift_groups=groups,
    )


def update_self_doctor_profile(db: Session, user: User, payload: DoctorSelfUpdate) -> Doctor | None:
    from app.services.doctors import update_doctor_self

    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        return None
    return update_doctor_self(db, doctor, payload, actor=user.email, source="rest")

