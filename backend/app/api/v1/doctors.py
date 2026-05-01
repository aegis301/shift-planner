from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import DoctorCreate, DoctorRead, DoctorUpdate
from app.services.authz import is_admin
from app.services.doctors import (
    create_doctor,
    delete_doctor,
    doctor_to_read,
    list_doctors,
    list_doctors_for_planner,
    update_doctor,
)

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorRead])
def get_doctors(active_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_planning_user)):
    if is_admin(user):
        doctors = list_doctors(db, organization_id=user.organization_id, active_only=active_only)
    else:
        doctors = list_doctors_for_planner(db, user, active_only=active_only)
    return [doctor_to_read(doctor) for doctor in doctors]


@router.post("", response_model=DoctorRead)
def post_doctor(payload: DoctorCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    try:
        doctor = create_doctor(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return doctor_to_read(doctor)


@router.patch("/{doctor_id}", response_model=DoctorRead)
def patch_doctor(
    doctor_id: int,
    payload: DoctorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        doctor = update_doctor(
            db, doctor_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor_to_read(doctor)


@router.delete("/{doctor_id}")
def delete_doctor_endpoint(
    doctor_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    return {
        "deleted": delete_doctor(
            db, doctor_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }
