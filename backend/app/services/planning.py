from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DoctorPeriodNote,
    PlanningCell,
    PlanningPeriod,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
)
from app.schemas import PlanningPeriodCreate
from app.services.audit import record_audit


def list_planning_periods(db: Session) -> list[PlanningPeriod]:
    return list(db.scalars(select(PlanningPeriod).order_by(PlanningPeriod.year.desc(), PlanningPeriod.month.desc())))


def create_planning_period(db: Session, payload: PlanningPeriodCreate, *, actor: str, source: str) -> PlanningPeriod:
    existing = db.scalar(
        select(PlanningPeriod).where(PlanningPeriod.year == payload.year, PlanningPeriod.month == payload.month)
    )
    if existing:
        return existing
    period = PlanningPeriod(**payload.model_dump(), status="draft")
    db.add(period)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="planning_period", entity_id=period.id)
    db.commit()
    db.refresh(period)
    return period


def delete_planning_period(db: Session, planning_period_id: int, *, actor: str, source: str) -> bool:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None:
        return False

    slot_ids = list(db.scalars(select(RosterSlot.id).where(RosterSlot.planning_period_id == planning_period_id)))
    if slot_ids:
        for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids))):
            db.delete(assignment)
    for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id)):
        db.delete(slot)
    for model in (PlanningShiftIntent, PlanningCell, DoctorPeriodNote):
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
