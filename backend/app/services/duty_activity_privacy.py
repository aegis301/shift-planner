from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Organization,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TimeEntry,
)
from app.schemas import (
    DutyActivityAccessPolicy,
    DutyActivityAccessPolicyUpdate,
    DutyActivityPurposeRead,
)
from app.services.audit import record_audit
from app.services.duty_activity import DUTY_ACTIVITY_KINDS, list_duty_activity_for_slots
from app.services.duty_utilization import _aggregate, resolve_utilization_bands, slot_utilization


def default_duty_activity_access_policy() -> DutyActivityAccessPolicy:
    return DutyActivityAccessPolicy()


def read_duty_activity_access_policy(organization: Organization) -> DutyActivityAccessPolicy:
    raw = organization.duty_activity_access_policy or {}
    return DutyActivityAccessPolicy.model_validate(raw)


def update_duty_activity_access_policy(
    db: Session,
    organization: Organization,
    payload: DutyActivityAccessPolicyUpdate,
    *,
    actor: str,
    source: str,
) -> DutyActivityAccessPolicy:
    current = read_duty_activity_access_policy(organization)
    updates = payload.model_dump(exclude_unset=True)
    merged = current.model_copy(update=updates)
    normalized = DutyActivityAccessPolicy.model_validate(merged.model_dump())
    organization.duty_activity_access_policy = normalized.model_dump()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="duty_activity_access_policy",
        entity_id=organization.id,
        details={
            "individual_read_roles": list(normalized.individual_read_roles),
            "retention_months": normalized.retention_months,
            "small_group_threshold": normalized.small_group_threshold,
            "purpose_statement": normalized.purpose_statement,
        },
    )
    db.commit()
    db.refresh(organization)
    return read_duty_activity_access_policy(organization)


def read_duty_activity_purpose(organization: Organization, member: TeamMember) -> DutyActivityPurposeRead:
    policy = read_duty_activity_access_policy(organization)
    acknowledged_at = member.duty_activity_purpose_acknowledged_at
    return DutyActivityPurposeRead(
        purpose_statement=policy.purpose_statement,
        acknowledged=acknowledged_at is not None,
        acknowledged_at=acknowledged_at,
    )


def acknowledge_duty_activity_purpose(
    db: Session,
    member: TeamMember,
    *,
    actor: str,
    source: str,
) -> DutyActivityPurposeRead:
    if member.duty_activity_purpose_acknowledged_at is None:
        member.duty_activity_purpose_acknowledged_at = datetime.now(UTC)
        record_audit(
            db,
            actor=actor,
            source=source,
            action="acknowledge",
            entity_type="duty_activity_purpose",
            entity_id=member.id,
        )
        db.commit()
        db.refresh(member)
    org = db.get(Organization, member.organization_id)
    if org is None:
        raise ValueError("Organization not found")
    return read_duty_activity_purpose(org, member)


def _subtract_months(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def purge_expired_duty_activity_episodes(
    db: Session,
    *,
    organization_id: int,
    actor: str,
    source: str,
    as_of: date | None = None,
) -> int:
    org = db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    policy = read_duty_activity_access_policy(org)
    cutoff = _subtract_months(as_of or date.today(), policy.retention_months)
    rows = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
                TimeEntry.entry_date < cutoff,
            )
        )
    )
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="purge",
        entity_type="duty_activity",
        entity_id=organization_id,
        details={"deleted": deleted, "cutoff": cutoff.isoformat(), "retention_months": policy.retention_months},
    )
    db.commit()
    return deleted


@dataclass(frozen=True)
class WorksCouncilDutyRow:
    period_label: str
    category: str
    suppressed: bool
    member_count: int
    worked_minutes: int | None
    duty_minutes: int | None
    utilization_percent: Decimal | None
    coverage_ratio: Decimal | None
    recorded_duty_count: int | None
    duty_count: int | None
    band: str | None
    exceeds_on_call_threshold: bool | None


def build_works_council_duty_rows(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
) -> list[WorksCouncilDutyRow]:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    org = db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    policy = read_duty_activity_access_policy(org)
    stmt = (
        select(RosterSlot, RosterSlotAssignment.team_member_id)
        .join(RosterSlotAssignment, RosterSlotAssignment.roster_slot_id == RosterSlot.id)
        .options(joinedload(RosterSlot.shift_template))
        .where(RosterSlot.planning_period_id == planning_period_id)
    )
    pairs = list(db.execute(stmt).unique().all())
    slots = [slot for slot, _member_id in pairs]
    episodes_by_slot = list_duty_activity_for_slots(
        db,
        organization_id=organization_id,
        roster_slot_ids={slot.id for slot in slots},
    )
    bands = resolve_utilization_bands(db, organization_id=organization_id)
    grouped: dict[str, dict] = defaultdict(lambda: {"slots": [], "member_ids": set()})
    for slot, member_id in pairs:
        template = slot.shift_template
        category = template.category if template is not None else "other"
        grouped[category]["slots"].append(slot)
        grouped[category]["member_ids"].add(member_id)
    period_label = f"{period.year}-{period.month:02d}"
    rows: list[WorksCouncilDutyRow] = []
    for category in sorted(grouped):
        bucket = grouped[category]
        member_count = len(bucket["member_ids"])
        slot_rows = [
            slot_utilization(slot, episodes_by_slot.get(slot.id, []), bands) for slot in bucket["slots"]
        ]
        recorded = [item for item in slot_rows if item.has_activity_record]
        aggregate = _aggregate(
            worked_minutes=sum(item.worked_minutes for item in recorded),
            duty_minutes=sum(item.duty_minutes for item in recorded),
            recorded_duty_count=len(recorded),
            duty_count=len(slot_rows),
            bands=bands,
        )
        suppressed = member_count < policy.small_group_threshold
        if suppressed:
            rows.append(
                WorksCouncilDutyRow(
                    period_label=period_label,
                    category=category,
                    suppressed=True,
                    member_count=member_count,
                    worked_minutes=None,
                    duty_minutes=None,
                    utilization_percent=None,
                    coverage_ratio=None,
                    recorded_duty_count=None,
                    duty_count=None,
                    band=None,
                    exceeds_on_call_threshold=None,
                )
            )
            continue
        rows.append(
            WorksCouncilDutyRow(
                period_label=period_label,
                category=category,
                suppressed=False,
                member_count=member_count,
                worked_minutes=aggregate.worked_minutes,
                duty_minutes=aggregate.duty_minutes,
                utilization_percent=aggregate.utilization_percent,
                coverage_ratio=aggregate.coverage.coverage_ratio,
                recorded_duty_count=aggregate.coverage.recorded_duty_count,
                duty_count=aggregate.coverage.duty_count,
                band=aggregate.band,
                exceeds_on_call_threshold=aggregate.exceeds_on_call_threshold,
            )
        )
    return rows


def works_council_row_to_dict(row: WorksCouncilDutyRow) -> dict:
    return {
        "period_label": row.period_label,
        "category": row.category,
        "suppressed": row.suppressed,
        "member_count": None if row.suppressed else row.member_count,
        "worked_minutes": row.worked_minutes,
        "duty_minutes": row.duty_minutes,
        "utilization_percent": str(row.utilization_percent) if row.utilization_percent is not None else None,
        "coverage_ratio": str(row.coverage_ratio) if row.coverage_ratio is not None else None,
        "recorded_duty_count": row.recorded_duty_count,
        "duty_count": row.duty_count,
        "band": row.band,
        "exceeds_on_call_threshold": row.exceeds_on_call_threshold,
    }


def audit_duty_activity_read(
    db: Session,
    *,
    actor: str,
    source: str,
    team_member_id: int,
    count: int,
) -> None:
    record_audit(
        db,
        actor=actor,
        source=source,
        action="read",
        entity_type="duty_activity",
        entity_id=team_member_id,
        details={"count": count},
    )
    db.commit()
