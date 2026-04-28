from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User


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

