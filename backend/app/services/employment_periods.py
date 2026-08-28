from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import EmploymentPeriod, TeamMember
from app.schemas import EmploymentPeriodRead, EmploymentPeriodWrite
from app.services.audit import record_audit
from app.services.worker_groups import get_worker_group_or_none


def _ranges_overlap(start_a: date, end_a: date | None, start_b: date, end_b: date | None) -> bool:
    last_a = end_a if end_a is not None else date.max
    last_b = end_b if end_b is not None else date.max
    return start_a <= last_b and start_b <= last_a


def employment_period_to_read(row: EmploymentPeriod) -> EmploymentPeriodRead:
    return EmploymentPeriodRead(
        id=row.id,
        team_member_id=row.team_member_id,
        worker_group_id=row.worker_group_id,
        worker_group_name=row.worker_group.name if row.worker_group is not None else None,
        employment_percentage=row.employment_percentage,
        start_date=row.start_date,
        end_date=row.end_date,
    )


def list_employment_periods(
    db: Session, *, team_member_id: int, organization_id: int
) -> list[EmploymentPeriod]:
    stmt = (
        select(EmploymentPeriod)
        .options(joinedload(EmploymentPeriod.worker_group))
        .where(
            EmploymentPeriod.team_member_id == team_member_id,
            EmploymentPeriod.organization_id == organization_id,
        )
        .order_by(EmploymentPeriod.start_date, EmploymentPeriod.id)
    )
    return list(db.scalars(stmt).unique())


def employment_on_date(periods: list[EmploymentPeriod], on_date: date) -> EmploymentPeriod | None:
    for row in periods:
        if row.start_date <= on_date and (row.end_date is None or row.end_date >= on_date):
            return row
    return None


def sync_member_employment_percentage(member: TeamMember, periods: list[EmploymentPeriod], *, today: date | None = None) -> None:
    on_date = today or date.today()
    active = employment_on_date(periods, on_date)
    if active is not None:
        member.employment_percentage = active.employment_percentage


def replace_employment_periods(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    periods: list[EmploymentPeriodWrite],
    actor: str,
    source: str,
) -> list[EmploymentPeriod]:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    normalized: list[EmploymentPeriodWrite] = []
    for item in periods:
        if item.end_date is not None and item.end_date < item.start_date:
            raise ValueError("Employment period end date must be on or after start date")
        group = get_worker_group_or_none(db, item.worker_group_id, organization_id=organization_id)
        if group is None:
            raise ValueError("Worker group not found")
        normalized.append(item)
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if _ranges_overlap(left.start_date, left.end_date, right.start_date, right.end_date):
                raise ValueError("Employment periods must not overlap")
    existing = list(
        db.scalars(
            select(EmploymentPeriod).where(
                EmploymentPeriod.team_member_id == team_member_id,
                EmploymentPeriod.organization_id == organization_id,
            )
        )
    )
    for row in existing:
        db.delete(row)
    db.flush()
    created: list[EmploymentPeriod] = []
    for item in normalized:
        row = EmploymentPeriod(
            organization_id=organization_id,
            team_member_id=team_member_id,
            worker_group_id=item.worker_group_id,
            employment_percentage=item.employment_percentage,
            start_date=item.start_date,
            end_date=item.end_date,
        )
        db.add(row)
        created.append(row)
    db.flush()
    sync_member_employment_percentage(member, created)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace",
        entity_type="employment_periods",
        entity_id=team_member_id,
    )
    db.commit()
    return list_employment_periods(db, team_member_id=team_member_id, organization_id=organization_id)
