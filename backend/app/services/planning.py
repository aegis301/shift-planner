from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AvailabilityRequest, PlanningPeriod, RosterAssignment
from app.schemas import AvailabilityRequestCreate, PlanningPeriodCreate, RosterAssignmentCreate
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


def list_requests(db: Session, *, planning_period_id: int | None = None) -> list[AvailabilityRequest]:
    stmt = select(AvailabilityRequest).order_by(AvailabilityRequest.request_date)
    if planning_period_id is not None:
        stmt = stmt.where(AvailabilityRequest.planning_period_id == planning_period_id)
    return list(db.scalars(stmt))


def record_availability_request(
    db: Session, payload: AvailabilityRequestCreate, *, actor: str, source: str
) -> AvailabilityRequest:
    request = AvailabilityRequest(**payload.model_dump())
    db.add(request)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="availability_request",
        entity_id=request.id,
    )
    db.commit()
    db.refresh(request)
    return request


def list_roster_assignments(db: Session, *, planning_period_id: int | None = None) -> list[RosterAssignment]:
    stmt = select(RosterAssignment).order_by(RosterAssignment.assignment_date)
    if planning_period_id is not None:
        stmt = stmt.where(RosterAssignment.planning_period_id == planning_period_id)
    return list(db.scalars(stmt))


def assign_shift(db: Session, payload: RosterAssignmentCreate, *, actor: str, source: str) -> RosterAssignment:
    assignment = RosterAssignment(**payload.model_dump())
    db.add(assignment)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="roster_assignment",
        entity_id=assignment.id,
    )
    db.commit()
    db.refresh(assignment)
    return assignment

