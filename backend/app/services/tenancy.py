from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, PlanningPeriod, ShiftGroup


def get_organization(db: Session, organization_id: int) -> Organization | None:
    return db.get(Organization, organization_id)


def ensure_default_organization(db: Session) -> Organization:
    org = db.get(Organization, 1)
    if org is not None:
        return org
    org = Organization(id=1, name="Default", plan_tier="team")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def require_planning_period_in_org(db: Session, planning_period_id: int, organization_id: int) -> PlanningPeriod:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    return period


def require_shift_group_in_org(db: Session, shift_group_id: int, organization_id: int) -> ShiftGroup:
    group = db.get(ShiftGroup, shift_group_id)
    if group is None or group.organization_id != organization_id:
        raise ValueError("Shift group not found")
    return group


def shift_group_ids_in_organization(db: Session, organization_id: int) -> set[int]:
    return set(db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == organization_id)).all())
