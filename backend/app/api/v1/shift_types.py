from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import ShiftTypeCreate, ShiftTypeRead, ShiftTypeUpdate
from app.services.shift_types import create_shift_type, list_shift_types, update_shift_type

router = APIRouter(prefix="/shift-types", tags=["shift-types"])


@router.get("", response_model=list[ShiftTypeRead])
def get_shift_types(active_only: bool = False, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_shift_types(db, active_only=active_only)


@router.post("", response_model=ShiftTypeRead)
def post_shift_type(payload: ShiftTypeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_shift_type(db, payload, actor=user.email, source="rest")


@router.patch("/{shift_type_id}", response_model=ShiftTypeRead)
def patch_shift_type(
    shift_type_id: int,
    payload: ShiftTypeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    shift_type = update_shift_type(db, shift_type_id, payload, actor=user.email, source="rest")
    if shift_type is None:
        raise HTTPException(status_code=404, detail="Shift type not found")
    return shift_type

