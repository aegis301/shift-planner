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

PLANNING_PERIOD_STATUS_DRAFT = "draft"
PLANNING_PERIOD_STATUS_PRELIMINARY = "preliminary"
PLANNING_PERIOD_STATUS_PUBLISHED = "published"
PLANNING_PERIOD_STATUSES = {
    PLANNING_PERIOD_STATUS_DRAFT,
    PLANNING_PERIOD_STATUS_PRELIMINARY,
    PLANNING_PERIOD_STATUS_PUBLISHED,
}


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
    period = PlanningPeriod(
        **payload.model_dump(),
        organization_id=organization_id,
        status=PLANNING_PERIOD_STATUS_DRAFT,
    )
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
    if period.status == PLANNING_PERIOD_STATUS_PUBLISHED:
        return period
    period.status = PLANNING_PERIOD_STATUS_PUBLISHED
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
    if period.status == PLANNING_PERIOD_STATUS_PRELIMINARY:
        return period
    period.status = PLANNING_PERIOD_STATUS_PRELIMINARY
    period.published_at = None
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="set_preliminary",
        entity_type="planning_period",
        entity_id=period.id,
        details={"year": period.year, "month": period.month},
    )
    db.commit()
    db.refresh(period)
    return period


def set_planning_period_to_draft(
    db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str
) -> PlanningPeriod | None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return None
    if period.status == PLANNING_PERIOD_STATUS_DRAFT:
        return period
    period.status = PLANNING_PERIOD_STATUS_DRAFT
    period.published_at = None
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="set_draft",
        entity_type="planning_period",
        entity_id=period.id,
        details={"year": period.year, "month": period.month},
    )
    db.commit()
    db.refresh(period)
    return period


def set_planning_period_to_preliminary(
    db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str
) -> PlanningPeriod | None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return None
    if period.status == PLANNING_PERIOD_STATUS_PRELIMINARY:
        return period
    period.status = PLANNING_PERIOD_STATUS_PRELIMINARY
    period.published_at = None
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="set_preliminary",
        entity_type="planning_period",
        entity_id=period.id,
        details={"year": period.year, "month": period.month},
    )
    db.commit()
    db.refresh(period)
    return period


def is_team_member_roster_visible(status: str) -> bool:
    return status in {PLANNING_PERIOD_STATUS_PRELIMINARY, PLANNING_PERIOD_STATUS_PUBLISHED}


def can_team_member_submit_feedback(status: str) -> bool:
    return status == PLANNING_PERIOD_STATUS_PRELIMINARY


def can_team_member_edit_wishes_matrix(status: str) -> bool:
    return status in {PLANNING_PERIOD_STATUS_DRAFT, PLANNING_PERIOD_STATUS_PRELIMINARY}
