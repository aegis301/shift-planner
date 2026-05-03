from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningPeriod,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    TeamMemberPeriodNote,
)
from app.schemas import PlanningPeriodCreate
from app.services.audit import record_audit


def list_planning_periods(db: Session, *, organization_id: int) -> list[PlanningPeriod]:
    stmt = (
        select(PlanningPeriod)
        .where(PlanningPeriod.organization_id == organization_id)
        .order_by(PlanningPeriod.year.desc(), PlanningPeriod.month.desc())
    )
    return list(db.scalars(stmt))


def create_planning_period(
    db: Session, payload: PlanningPeriodCreate, *, organization_id: int, actor: str, source: str
) -> PlanningPeriod:
    existing = db.scalar(
        select(PlanningPeriod).where(
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriod.year == payload.year,
            PlanningPeriod.month == payload.month,
        )
    )
    if existing:
        return existing
    period = PlanningPeriod(**payload.model_dump(), organization_id=organization_id, status="draft")
    db.add(period)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="planning_period", entity_id=period.id)
    db.commit()
    db.refresh(period)
    return period


def delete_planning_period(db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str) -> bool:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return False

    slot_ids = list(db.scalars(select(RosterSlot.id).where(RosterSlot.planning_period_id == planning_period_id)))
    if slot_ids:
        for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids))):
            db.delete(assignment)
    for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id)):
        db.delete(slot)
    for model in (PlanningShiftIntent, PlanningCell, TeamMemberPeriodNote):
        for item in db.scalars(select(model).where(model.planning_period_id == planning_period_id)):
            db.delete(item)

    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="planning_period",
        entity_id=planning_period_id,
        details={"year": period.year, "month": period.month, "cleared_slot_count": len(slot_ids)},
    )
    db.delete(period)
    db.commit()
    return True


def publish_planning_period(
    db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str
) -> PlanningPeriod | None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return None
    if period.status == "published":
        return period
    period.status = "published"
    period.published_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="publish",
        entity_type="planning_period",
        entity_id=period.id,
        details={"year": period.year, "month": period.month},
    )
    db.commit()
    db.refresh(period)
    return period


def unpublish_planning_period(
    db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str
) -> PlanningPeriod | None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return None
    if period.status == "draft":
        return period
    period.status = "draft"
    period.published_at = None
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="unpublish",
        entity_type="planning_period",
        entity_id=period.id,
        details={"year": period.year, "month": period.month},
    )
    db.commit()
    db.refresh(period)
    return period
