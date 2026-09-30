from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import SESSION_KIND_ACCOUNT, SESSION_KIND_USER, verify_session_subject
from app.db.session import get_db
from app.models import Account, User
from app.services.authz import can_use_planning_ui, is_admin, is_applicant
from app.services.device_sessions import BearerRejected, authenticate_bearer
from app.services.users import get_user


def get_current_session_holder(
    request: Request,
    db: Session = Depends(get_db),
    session: str | None = Cookie(default=None, alias="shift_planner_session"),
    authorization: Annotated[str | None, Header()] = None,
) -> User | Account:
    request.state.bearer_device_session_id = None
    if authorization:
        scheme, _, param = authorization.partition(" ")
        if scheme.lower() == "bearer":
            if param == "":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
            try:
                holder, device_session_id = authenticate_bearer(db, param)
            except BearerRejected:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from None
            request.state.bearer_device_session_id = device_session_id
            return holder
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    subj = verify_session_subject(session)
    if subj is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    if subj.kind == SESSION_KIND_ACCOUNT:
        acc = db.get(Account, subj.id)
        if acc is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        return acc
    if subj.kind != SESSION_KIND_USER:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = get_user(db, subj.id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def current_bearer_device_session_id(
    request: Request,
    _holder: Annotated[User | Account, Depends(get_current_session_holder)],
) -> int | None:
    return getattr(request.state, "bearer_device_session_id", None)


def get_current_user(
    holder: Annotated[User | Account, Depends(get_current_session_holder)],
) -> User:
    if isinstance(holder, Account):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "account_session_incomplete"},
        )
    return holder


def get_current_account_session(
    holder: Annotated[User | Account, Depends(get_current_session_holder)],
) -> Account:
    if isinstance(holder, User):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Onboarding is for accounts without membership")
    return holder


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
