from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_session_token
from app.db.session import get_db
from app.models import User
from app.services.authz import can_use_planning_ui, is_admin, is_applicant
from app.services.users import get_user


def get_current_user(
    db: Session = Depends(get_db),
    session: str | None = Cookie(default=None, alias="shift_planner_session"),
) -> User:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = verify_session_token(session)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = get_user(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def get_current_planning_user(user: User = Depends(get_current_user)) -> User:
    if not can_use_planning_ui(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning access denied")
    return user


def get_current_planner(user: User = Depends(get_current_planning_user)) -> User:
    return user


def get_current_user_excluding_applicant(user: User = Depends(get_current_user)) -> User:
    if is_applicant(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onboarding pending")
    return user
