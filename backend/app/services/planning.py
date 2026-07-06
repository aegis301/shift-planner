from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningPeriod,
    PlanningPeriodShiftGroupStatus,
    PlanningPlanVersion,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    TeamMemberPeriodNote,
)
from app.schemas import PlanningPeriodCreate, ShiftGroupPlanningStatusRead
from app.services.audit import record_audit
from app.services.shift_groups import list_shift_groups, require_shift_group

PLANNING_PERIOD_STATUS_DRAFT = "draft"
PLANNING_PERIOD_STATUS_PRELIMINARY = "preliminary"
PLANNING_PERIOD_STATUS_PUBLISHED = "published"
PLANNING_PERIOD_STATUSES = {
    PLANNING_PERIOD_STATUS_DRAFT,
    PLANNING_PERIOD_STATUS_PRELIMINARY,
    PLANNING_PERIOD_STATUS_PUBLISHED,
}
_OPEN_GROUP_STATUSES = frozenset({PLANNING_PERIOD_STATUS_DRAFT, PLANNING_PERIOD_STATUS_PRELIMINARY})


def list_planning_periods(db: Session, *, organization_id: int) -> list[PlanningPeriod]:
    stmt = (
        select(PlanningPeriod)
        .where(PlanningPeriod.organization_id == organization_id)
        .order_by(PlanningPeriod.year.desc(), PlanningPeriod.month.desc())
    )
    return list(db.scalars(stmt))


def list_shift_group_statuses_for_period(
    db: Session, *, planning_period_id: int, organization_id: int
) -> list[PlanningPeriodShiftGroupStatus]:
    _require_period_org(db, planning_period_id, organization_id)
    stmt = (
        select(PlanningPeriodShiftGroupStatus)
        .where(PlanningPeriodShiftGroupStatus.planning_period_id == planning_period_id)
        .order_by(PlanningPeriodShiftGroupStatus.shift_group_id)
    )
    return list(db.scalars(stmt))


def _require_period_org(db: Session, planning_period_id: int, organization_id: int) -> PlanningPeriod:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    return period


def _get_shift_group_status_row(
    db: Session, *, planning_period_id: int, shift_group_id: int, organization_id: int
) -> PlanningPeriodShiftGroupStatus | None:
    _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    return db.scalar(
        select(PlanningPeriodShiftGroupStatus).where(
            PlanningPeriodShiftGroupStatus.planning_period_id == planning_period_id,
            PlanningPeriodShiftGroupStatus.shift_group_id == shift_group_id,
        )
    )


def ensure_shift_group_statuses_for_period(
    db: Session, *, planning_period_id: int, organization_id: int
) -> list[PlanningPeriodShiftGroupStatus]:
    period = _require_period_org(db, planning_period_id, organization_id)
    existing_ids = set(
        db.scalars(
            select(PlanningPeriodShiftGroupStatus.shift_group_id).where(
                PlanningPeriodShiftGroupStatus.planning_period_id == planning_period_id
            )
        ).all()
    )
    created: list[PlanningPeriodShiftGroupStatus] = []
    for group in list_shift_groups(db, organization_id=organization_id, active_only=True):
        if group.id in existing_ids:
            continue
        row = PlanningPeriodShiftGroupStatus(
            planning_period_id=planning_period_id,
            shift_group_id=group.id,
            status=PLANNING_PERIOD_STATUS_DRAFT,
        )
        db.add(row)
        created.append(row)
    if created:
        db.flush()
        _sync_period_aggregate_status(db, period)
    return created


def ensure_shift_group_statuses_for_new_group(
    db: Session, *, shift_group_id: int, organization_id: int
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    periods = list(
        db.scalars(select(PlanningPeriod).where(PlanningPeriod.organization_id == organization_id))
    )
    for period in periods:
        existing = _get_shift_group_status_row(
            db,
            planning_period_id=period.id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
        )
        if existing is not None:
            continue
        db.add(
            PlanningPeriodShiftGroupStatus(
                planning_period_id=period.id,
                shift_group_id=shift_group_id,
                status=PLANNING_PERIOD_STATUS_DRAFT,
            )
        )
    db.flush()


def get_shift_group_planning_status(
    db: Session, *, planning_period_id: int, shift_group_id: int, organization_id: int
) -> PlanningPeriodShiftGroupStatus | None:
    row = _get_shift_group_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is not None:
        return row
    ensure_shift_group_statuses_for_period(
        db, planning_period_id=planning_period_id, organization_id=organization_id
    )
    return _get_shift_group_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )


def shift_group_planning_status_read(
    db: Session, *, planning_period_id: int, shift_group_id: int, organization_id: int
) -> ShiftGroupPlanningStatusRead | None:
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None:
        return None
    return ShiftGroupPlanningStatusRead.model_validate(row)


def _sync_period_aggregate_status(db: Session, period: PlanningPeriod) -> None:
    statuses = list(
        db.scalars(
            select(PlanningPeriodShiftGroupStatus.status).where(
                PlanningPeriodShiftGroupStatus.planning_period_id == period.id
            )
        )
    )
    if not statuses:
        period.status = PLANNING_PERIOD_STATUS_DRAFT
        period.published_at = None
        return
    if all(status == PLANNING_PERIOD_STATUS_PUBLISHED for status in statuses):
        period.status = PLANNING_PERIOD_STATUS_PUBLISHED
        if period.published_at is None:
            period.published_at = datetime.now(timezone.utc)
    elif any(status == PLANNING_PERIOD_STATUS_DRAFT for status in statuses):
        period.status = PLANNING_PERIOD_STATUS_DRAFT
        period.published_at = None
    else:
        period.status = PLANNING_PERIOD_STATUS_PRELIMINARY
        period.published_at = None


def can_edit_planning_data(status: str) -> bool:
    return status in _OPEN_GROUP_STATUSES


def _transition_with_versioning(db: Session, **kwargs):
    from app.services.plan_versions import transition_shift_group_status_with_versioning

    return transition_shift_group_status_with_versioning(db, **kwargs)


def publish_shift_group_planning(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
) -> PlanningPeriodShiftGroupStatus | None:
    return _transition_with_versioning(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        target_status=PLANNING_PERIOD_STATUS_PUBLISHED,
        actor=actor,
        source=source,
        audit_action="publish",
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
    )


def unpublish_shift_group_planning(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> PlanningPeriodShiftGroupStatus | None:
    return _transition_with_versioning(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        target_status=PLANNING_PERIOD_STATUS_PRELIMINARY,
        actor=actor,
        source=source,
        audit_action="set_preliminary",
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
        is_major_update=is_major_update,
    )


def set_shift_group_planning_to_draft(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
) -> PlanningPeriodShiftGroupStatus | None:
    return _transition_with_versioning(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        target_status=PLANNING_PERIOD_STATUS_DRAFT,
        actor=actor,
        source=source,
        audit_action="set_draft",
    )


def set_shift_group_planning_to_preliminary(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> PlanningPeriodShiftGroupStatus | None:
    return _transition_with_versioning(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        target_status=PLANNING_PERIOD_STATUS_PRELIMINARY,
        actor=actor,
        source=source,
        audit_action="set_preliminary",
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
        is_major_update=is_major_update,
    )


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
        ensure_shift_group_statuses_for_period(
            db, planning_period_id=existing.id, organization_id=organization_id
        )
        db.commit()
        return existing
    period = PlanningPeriod(
        **payload.model_dump(),
        organization_id=organization_id,
        status=PLANNING_PERIOD_STATUS_DRAFT,
    )
    db.add(period)
    db.flush()
    ensure_shift_group_statuses_for_period(db, planning_period_id=period.id, organization_id=organization_id)
    record_audit(db, actor=actor, source=source, action="create", entity_type="planning_period", entity_id=period.id)
    db.commit()
    db.refresh(period)
    from app.services.member_planning_patterns import sync_recurring_weekday_for_new_period

    sync_recurring_weekday_for_new_period(
        db, planning_period_id=period.id, organization_id=organization_id, actor=actor, source=source
    )
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
    for model in (PlanningShiftIntent, PlanningCell, TeamMemberPeriodNote, PlanningPeriodShiftGroupStatus):
        for item in db.scalars(select(model).where(model.planning_period_id == planning_period_id)):
            db.delete(item)
    for version in db.scalars(
        select(PlanningPlanVersion).where(PlanningPlanVersion.planning_period_id == planning_period_id)
    ):
        db.delete(version)

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
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
) -> PlanningPeriodShiftGroupStatus | None:
    return publish_shift_group_planning(
        db,
        planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        actor=actor,
        source=source,
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
    )


def unpublish_planning_period(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> PlanningPeriodShiftGroupStatus | None:
    return unpublish_shift_group_planning(
        db,
        planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        actor=actor,
        source=source,
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
        is_major_update=is_major_update,
    )


def set_planning_period_to_draft(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
) -> PlanningPeriodShiftGroupStatus | None:
    return set_shift_group_planning_to_draft(
        db,
        planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        actor=actor,
        source=source,
    )


def set_planning_period_to_preliminary(
    db: Session,
    planning_period_id: int,
    *,
    shift_group_id: int,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> PlanningPeriodShiftGroupStatus | None:
    return set_shift_group_planning_to_preliminary(
        db,
        planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        actor=actor,
        source=source,
        created_by_user_id=created_by_user_id,
        major_version=major_version,
        minor_version=minor_version,
        note=note,
        is_major_update=is_major_update,
    )


def is_team_member_roster_visible(status: str) -> bool:
    return status in {PLANNING_PERIOD_STATUS_PRELIMINARY, PLANNING_PERIOD_STATUS_PUBLISHED}


def can_team_member_submit_feedback(status: str) -> bool:
    return status == PLANNING_PERIOD_STATUS_PRELIMINARY


def can_team_member_edit_wishes_matrix(status: str) -> bool:
    return status in _OPEN_GROUP_STATUSES


def is_shift_group_planning_open(db: Session, *, planning_period_id: int, shift_group_id: int, organization_id: int) -> bool:
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    return row is not None and row.status in _OPEN_GROUP_STATUSES
