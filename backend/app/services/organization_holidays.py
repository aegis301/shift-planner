"""Organization holidays: dates an organization treats as holidays on top of the NRW calendar.

Every holiday-aware calculation passes ``organization_holiday_dates`` to ``classify_day``.
Adding or removing a holiday does not rewrite existing roster slots: the planner syncs the
affected month, which regenerates slots against the updated calendar.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OrganizationHoliday
from app.schemas import OrganizationHolidayCreate, OrganizationHolidayUpdate
from app.services.audit import record_audit

DUPLICATE_DATE_MESSAGE = "This date is already an organization holiday"


def list_organization_holidays(
    db: Session,
    *,
    organization_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[OrganizationHoliday]:
    stmt = select(OrganizationHoliday).where(OrganizationHoliday.organization_id == organization_id)
    if start_date is not None:
        stmt = stmt.where(OrganizationHoliday.holiday_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(OrganizationHoliday.holiday_date <= end_date)
    return list(db.scalars(stmt.order_by(OrganizationHoliday.holiday_date)))


def organization_holiday_dates(
    db: Session,
    *,
    organization_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> frozenset[date]:
    stmt = select(OrganizationHoliday.holiday_date).where(OrganizationHoliday.organization_id == organization_id)
    if start_date is not None:
        stmt = stmt.where(OrganizationHoliday.holiday_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(OrganizationHoliday.holiday_date <= end_date)
    return frozenset(db.scalars(stmt))


def get_organization_holiday(db: Session, holiday_id: int, *, organization_id: int) -> OrganizationHoliday | None:
    row = db.get(OrganizationHoliday, holiday_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def _date_taken(db: Session, *, organization_id: int, holiday_date: date, exclude_id: int | None = None) -> bool:
    stmt = select(OrganizationHoliday.id).where(
        OrganizationHoliday.organization_id == organization_id,
        OrganizationHoliday.holiday_date == holiday_date,
    )
    if exclude_id is not None:
        stmt = stmt.where(OrganizationHoliday.id != exclude_id)
    return db.scalar(stmt) is not None


def _clean_label(raw: str) -> str:
    label = raw.strip()
    if not label:
        raise ValueError("Label must not be empty")
    return label


def create_organization_holiday(
    db: Session,
    payload: OrganizationHolidayCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> OrganizationHoliday:
    label = _clean_label(payload.label)
    if _date_taken(db, organization_id=organization_id, holiday_date=payload.holiday_date):
        raise ValueError(DUPLICATE_DATE_MESSAGE)
    row = OrganizationHoliday(organization_id=organization_id, holiday_date=payload.holiday_date, label=label)
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="organization_holiday",
        entity_id=row.id,
        details={"holiday_date": row.holiday_date.isoformat(), "label": row.label},
    )
    db.commit()
    db.refresh(row)
    return row


def update_organization_holiday(
    db: Session,
    holiday_id: int,
    payload: OrganizationHolidayUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> OrganizationHoliday | None:
    row = get_organization_holiday(db, holiday_id, organization_id=organization_id)
    if row is None:
        return None
    if payload.label is not None:
        row.label = _clean_label(payload.label)
    if payload.holiday_date is not None and payload.holiday_date != row.holiday_date:
        if _date_taken(db, organization_id=organization_id, holiday_date=payload.holiday_date, exclude_id=row.id):
            raise ValueError(DUPLICATE_DATE_MESSAGE)
        row.holiday_date = payload.holiday_date
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="organization_holiday",
        entity_id=row.id,
        details={"holiday_date": row.holiday_date.isoformat(), "label": row.label},
    )
    db.commit()
    db.refresh(row)
    return row


def delete_organization_holiday(
    db: Session,
    holiday_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    row = get_organization_holiday(db, holiday_id, organization_id=organization_id)
    if row is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="organization_holiday",
        entity_id=row.id,
        details={"holiday_date": row.holiday_date.isoformat(), "label": row.label},
    )
    db.delete(row)
    db.commit()
    return True
