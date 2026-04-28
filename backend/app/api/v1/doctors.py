from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import DoctorCreate, DoctorRead, DoctorUpdate
from app.services.doctors import create_doctor, list_doctors, update_doctor

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorRead])
def get_doctors(active_only: bool = False, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_doctors(db, active_only=active_only)


@router.post("", response_model=DoctorRead)
def post_doctor(payload: DoctorCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_doctor(db, payload, actor=user.email, source="rest")


@router.patch("/{doctor_id}", response_model=DoctorRead)
def patch_doctor(
    doctor_id: int,
    payload: DoctorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doctor = update_doctor(db, doctor_id, payload, actor=user.email, source="rest")
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor

