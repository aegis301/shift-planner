from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import OrganizationHoliday, User
from app.schemas import (
    OrganizationHolidayCreate,
    OrganizationHolidayDeleteRead,
    OrganizationHolidayRead,
    OrganizationHolidayRosterSyncRead,
    OrganizationHolidayUpdate,
    OrganizationHolidayWriteRead,
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


def _write_read(
    row: OrganizationHoliday, roster_sync: OrganizationHolidayRosterSyncRead
) -> OrganizationHolidayWriteRead:
    return OrganizationHolidayWriteRead(
        **OrganizationHolidayRead.model_validate(row).model_dump(), roster_sync=roster_sync
    )


@router.post("", response_model=OrganizationHolidayWriteRead, status_code=status.HTTP_201_CREATED)
def post_organization_holiday(
    payload: OrganizationHolidayCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationHolidayWriteRead:
    """Create the holiday and re-plan that day in existing, unpublished planning months."""
    try:
        row, roster_sync = create_organization_holiday(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _write_read(row, roster_sync)


@router.patch("/{holiday_id}", response_model=OrganizationHolidayWriteRead)
def patch_organization_holiday(
    holiday_id: int,
    payload: OrganizationHolidayUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationHolidayWriteRead:
    """Rename or move the holiday. Moving re-plans both the old and the new day."""
    try:
        result = update_organization_holiday(
            db,
            holiday_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Organization holiday not found")
    return _write_read(*result)


@router.delete("/{holiday_id}", response_model=OrganizationHolidayDeleteRead)
def delete_organization_holiday_endpoint(
    holiday_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationHolidayDeleteRead:
    """Delete the holiday and re-plan that day in existing, unpublished planning months."""
    roster_sync = delete_organization_holiday(
        db, holiday_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if roster_sync is None:
        raise HTTPException(status_code=404, detail="Organization holiday not found")
    return OrganizationHolidayDeleteRead(deleted=True, roster_sync=roster_sync)
