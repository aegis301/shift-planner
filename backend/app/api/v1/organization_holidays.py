from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    DeletedFlagRead,
    OrganizationHolidayCreate,
    OrganizationHolidayRead,
    OrganizationHolidayUpdate,
)
from app.services.organization_holidays import (
    create_organization_holiday,
    delete_organization_holiday,
    list_organization_holidays,
    update_organization_holiday,
)

router = APIRouter(prefix="/organization-holidays", tags=["organization-holidays"])


@router.get("", response_model=list[OrganizationHolidayRead])
def get_organization_holidays(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[OrganizationHolidayRead]:
    rows = list_organization_holidays(
        db, organization_id=user.organization_id, start_date=from_date, end_date=to_date
    )
    return [OrganizationHolidayRead.model_validate(row) for row in rows]


@router.post("", response_model=OrganizationHolidayRead, status_code=status.HTTP_201_CREATED)
def post_organization_holiday(
    payload: OrganizationHolidayCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationHolidayRead:
    try:
        row = create_organization_holiday(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrganizationHolidayRead.model_validate(row)


@router.patch("/{holiday_id}", response_model=OrganizationHolidayRead)
def patch_organization_holiday(
    holiday_id: int,
    payload: OrganizationHolidayUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationHolidayRead:
    try:
        row = update_organization_holiday(
            db,
            holiday_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Organization holiday not found")
    return OrganizationHolidayRead.model_validate(row)


@router.delete("/{holiday_id}", response_model=DeletedFlagRead)
def delete_organization_holiday_endpoint(
    holiday_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> DeletedFlagRead:
    deleted = delete_organization_holiday(
        db, holiday_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization holiday not found")
    return DeletedFlagRead(deleted=True)
