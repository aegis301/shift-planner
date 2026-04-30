from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import SESSION_MAX_AGE_SECONDS, create_session_token
from app.db.session import get_db
from app.models import User
from app.schemas import DoctorRead, DoctorSelfUpdate, LoginInput, UserRead
from app.services.authz import get_linked_doctor
from app.services.doctors import doctor_to_read
from app.services.users import authenticate_user, build_user_read, update_self_doctor_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> UserRead:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    response.set_cookie(
        "shift_planner_session",
        create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return build_user_read(db, user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("shift_planner_session")
    return {"ok": True}


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserRead:
    return build_user_read(db, user)


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
