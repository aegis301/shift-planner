from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import SESSION_MAX_AGE_SECONDS, create_session_token
from app.db.session import get_db
from app.models import User
from app.schemas import (
    DeleteAccountInput,
    DoctorRead,
    DoctorSelfUpdate,
    JoinRequestRead,
    LoginInput,
    RegisterCreateOrganizationInput,
    RegisterJoinOrganizationInput,
    UserRead,
)
from app.services.authz import get_linked_doctor
from app.services.doctors import doctor_to_read
from app.services.join_requests import get_pending_join_request_for_user, join_request_to_read
from app.services.registration import register_create_organization, register_join_organization
from app.services.users import authenticate_user, build_user_read, delete_own_account, update_self_doctor_profile


def _set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
    )


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> UserRead:
    user = authenticate_user(db, payload.email, payload.password, payload.organization_slug)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    _set_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/register/create-organization", response_model=UserRead)
def post_register_create_organization(
    payload: RegisterCreateOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    try:
        user, _org = register_create_organization(
            db,
            organization_name=payload.organization_name,
            organization_slug=payload.organization_slug,
            email=str(payload.email),
            password=payload.password,
            locale=payload.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/register/join-organization", response_model=UserRead)
def post_register_join_organization(
    payload: RegisterJoinOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    try:
        user, _org = register_join_organization(
            db,
            organization_slug=payload.organization_slug,
            email=str(payload.email),
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            message=payload.message,
            locale=payload.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("shift_planner_session")
    return {"ok": True}


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def post_delete_account(
    payload: DeleteAccountInput,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        delete_own_account(db, user, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.delete_cookie("shift_planner_session")


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserRead:
    return build_user_read(db, user)


@router.get("/me/join-request", response_model=JoinRequestRead | None)
def get_me_join_request(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JoinRequestRead | None:
    row = get_pending_join_request_for_user(db, user_id=user.id)
    if row is None:
        return None
    return join_request_to_read(row)


@router.get("/me/doctor", response_model=DoctorRead)
def get_me_doctor(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor only")
    doctor = get_linked_doctor(db, user.id)
    if doctor is None:
        raise HTTPException(status_code=404, detail="No linked doctor profile")
    db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor_to_read(doctor)


@router.patch("/me/doctor", response_model=DoctorRead)
def patch_me_doctor(
    payload: DoctorSelfUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doctor only")
    try:
        doctor = update_self_doctor_profile(db, user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if doctor is None:
        raise HTTPException(status_code=404, detail="No linked doctor profile")
    db.refresh(doctor, attribute_names=["shift_group_links"])
    return doctor_to_read(doctor)
