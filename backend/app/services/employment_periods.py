from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmploymentPeriod, TeamMember, TimeAccountOpening
from app.schemas import (
    EmploymentPeriodRead,
    EmploymentPeriodWrite,
    TimeAccountOpeningRead,
    TimeAccountOpeningUpsert,
)
from app.services.audit import record_audit
from app.services.contract_group_defaults import OPEN_ENDED_EMPLOYMENT_START
from app.services.contract_groups import ensure_default_contract_group, get_contract_group
from app.services.shift_groups import _stint_active_on, _stint_overlaps_range


def employment_percentage_on(member: TeamMember, on_date: date) -> int:
    for period in member.employment_periods:
        if _stint_active_on(period, on_date):
            return period.employment_percentage
    return 100


def employment_period_to_read(row: EmploymentPeriod) -> EmploymentPeriodRead:
    return EmploymentPeriodRead.model_validate(row)


def time_account_opening_to_read(row: TimeAccountOpening) -> TimeAccountOpeningRead:
    return TimeAccountOpeningRead.model_validate(row)


def list_employment_periods(db: Session, team_member_id: int, *, organization_id: int) -> list[EmploymentPeriod]:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        return []
    stmt = (
        select(EmploymentPeriod)
        .where(EmploymentPeriod.team_member_id == team_member_id)
        .order_by(EmploymentPeriod.start_date, EmploymentPeriod.id)
    )
    return list(db.scalars(stmt))


def _assert_no_employment_overlap(
    periods: list[tuple[date, date | None]],
) -> None:
    ordered = sorted(periods, key=lambda item: item[0])
    for index, (start_date, end_date) in enumerate(ordered):
        for other_start, other_end in ordered[index + 1 :]:
            if _stint_overlaps_range(start_date, end_date, other_start, other_end or date.max):
                raise ValueError("Employment periods overlap")


def _require_member(db: Session, team_member_id: int, organization_id: int) -> TeamMember:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    return member


def create_initial_employment_period(
    db: Session,
    member: TeamMember,
    *,
    employment_percentage: int,
) -> EmploymentPeriod:
    group = ensure_default_contract_group(db, organization_id=member.organization_id)
    period = EmploymentPeriod(
        team_member_id=member.id,
        contract_group_id=group.id,
        employment_percentage=employment_percentage,
        start_date=OPEN_ENDED_EMPLOYMENT_START,
        end_date=None,
    )
    db.add(period)
    opening = db.scalar(select(TimeAccountOpening).where(TimeAccountOpening.team_member_id == member.id))
    if opening is None:
        db.add(
            TimeAccountOpening(
                team_member_id=member.id,
                as_of_date=OPEN_ENDED_EMPLOYMENT_START,
                overtime_minutes=0,
                vacation_days_remaining=Decimal("0"),
                sick_days_used_ytd=Decimal("0"),
            )
        )
    db.flush()
    return period


def apply_current_employment_percentage(
    db: Session,
    member: TeamMember,
    employment_percentage: int,
) -> None:
    today = date.today()
    current = next((period for period in member.employment_periods if _stint_active_on(period, today)), None)
    if current is not None:
        current.employment_percentage = employment_percentage
        db.flush()
        return
    create_initial_employment_period(db, member, employment_percentage=employment_percentage)


def replace_employment_periods(
    db: Session,
    team_member_id: int,
    periods: list[EmploymentPeriodWrite],
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> list[EmploymentPeriod]:
    member = _require_member(db, team_member_id, organization_id)
    _assert_no_employment_overlap([(row.start_date, row.end_date) for row in periods])
    for payload in periods:
        group = get_contract_group(db, payload.contract_group_id, organization_id=organization_id)
        if group is None:
            raise ValueError("Contract group not found")
    existing = list(db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.team_member_id == member.id)))
    for row in existing:
        db.delete(row)
    db.flush()
    for payload in periods:
        db.add(
            EmploymentPeriod(
                team_member_id=member.id,
                contract_group_id=payload.contract_group_id,
                employment_percentage=payload.employment_percentage,
                start_date=payload.start_date,
                end_date=payload.end_date,
            )
        )
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace",
        entity_type="employment_period",
        entity_id=member.id,
    )
    db.commit()
    return list_employment_periods(db, team_member_id, organization_id=organization_id)


def get_time_account_opening(
    db: Session, team_member_id: int, *, organization_id: int
) -> TimeAccountOpening | None:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        return None
    return db.scalar(select(TimeAccountOpening).where(TimeAccountOpening.team_member_id == team_member_id))


def upsert_time_account_opening(
    db: Session,
    team_member_id: int,
    payload: TimeAccountOpeningUpsert,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> TimeAccountOpening:
    member = _require_member(db, team_member_id, organization_id)
    row = db.scalar(select(TimeAccountOpening).where(TimeAccountOpening.team_member_id == member.id))
    if row is None:
        row = TimeAccountOpening(team_member_id=member.id)
        db.add(row)
    row.as_of_date = payload.as_of_date
    row.overtime_minutes = payload.overtime_minutes
    row.vacation_days_remaining = payload.vacation_days_remaining
    row.sick_days_used_ytd = payload.sick_days_used_ytd
    row.fairness_balances = {
        str(key): float(value) for key, value in (payload.fairness_balances or {}).items()
    }
    record_audit(
        db,
        actor=actor,
        source=source,
        action="upsert",
        entity_type="time_account_opening",
        entity_id=member.id,
    )
    db.commit()
    db.refresh(row)
    return row
