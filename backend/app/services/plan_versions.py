from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    PlanVersionMemberNote,
    PlanVersionPlanningCell,
    PlanVersionRosterAssignment,
    PlanVersionRosterSlot,
    PlanVersionShiftIntent,
    PlanningCell,
    PlanningPeriod,
    PlanningPeriodShiftGroupStatus,
    PlanningPlanVersion,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TeamMemberPeriodNote,
)
from app.schemas import (
    MatrixDay,
    MatrixTeamMember,
    PlanVersionListRead,
    PlanVersionRead,
    PlanningCellRead,
    PlanningDayStatusDefinitionRead,
    PlanningMatrixRead,
    PlanningPeriodRead,
    PlanningShiftIntentRead,
    RosterMatrixRead,
    RosterSlotAssignmentRead,
    RosterSlotRead,
    ShiftGroupPlanningStatusRead,
    ShiftTemplateRead,
)
from app.services.audit import record_audit
from app.services.planning import (
    PLANNING_PERIOD_STATUS_DRAFT,
    PLANNING_PERIOD_STATUS_PRELIMINARY,
    PLANNING_PERIOD_STATUS_PUBLISHED,
    _sync_period_aggregate_status,
    get_shift_group_planning_status,
)
from app.services.shift_groups import (
    active_team_member_ids_in_shift_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
)
from app.services.shift_templates import list_shift_templates
from app.services.tenancy import require_planning_period_in_org

VERSION_TRIGGER_STATUS_PRELIMINARY = "status_preliminary"
VERSION_TRIGGER_STATUS_PUBLISHED = "status_published"
VERSION_TRIGGER_MANUAL_SAVE = "manual_save"


class PlanVersionValidationError(ValueError):
    pass


class PlanVersionNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class VersionTuple:
    major: int
    minor: int

    @property
    def label(self) -> str:
        return f"{self.major}.{self.minor}"


def compare_versions(left: VersionTuple, right: VersionTuple) -> int:
    if left.major != right.major:
        return -1 if left.major < right.major else 1
    if left.minor != right.minor:
        return -1 if left.minor < right.minor else 1
    return 0


def _version_tuple(major: int, minor: int) -> VersionTuple:
    return VersionTuple(major=major, minor=minor)


def _require_status_row(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> PlanningPeriodShiftGroupStatus:
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None:
        raise PlanVersionNotFoundError("Planning period not found")
    return row


def _latest_saved_version(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
) -> PlanningPlanVersion | None:
    return db.scalar(
        select(PlanningPlanVersion)
        .where(
            PlanningPlanVersion.planning_period_id == planning_period_id,
            PlanningPlanVersion.shift_group_id == shift_group_id,
        )
        .order_by(
            PlanningPlanVersion.major_version.desc(),
            PlanningPlanVersion.minor_version.desc(),
        )
        .limit(1)
    )


def _has_any_published_version(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
) -> bool:
    row = db.scalar(
        select(PlanningPlanVersion.id)
        .where(
            PlanningPlanVersion.planning_period_id == planning_period_id,
            PlanningPlanVersion.shift_group_id == shift_group_id,
            PlanningPlanVersion.lifecycle_phase == PLANNING_PERIOD_STATUS_PUBLISHED,
        )
        .limit(1)
    )
    return row is not None


def _working_version(row: PlanningPeriodShiftGroupStatus) -> VersionTuple | None:
    if row.working_major_version is None or row.working_minor_version is None:
        return None
    return _version_tuple(row.working_major_version, row.working_minor_version)


def _set_working_version(row: PlanningPeriodShiftGroupStatus, version: VersionTuple) -> None:
    row.working_major_version = version.major
    row.working_minor_version = version.minor


def suggest_next_version(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    trigger: str,
    is_major_update: bool = False,
) -> VersionTuple:
    row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    latest = _latest_saved_version(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    working = _working_version(row)
    has_published = row.first_published_at is not None or _has_any_published_version(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )

    if trigger == VERSION_TRIGGER_STATUS_PRELIMINARY:
        if row.status == PLANNING_PERIOD_STATUS_PUBLISHED:
            if is_major_update:
                base_major = working.major if working is not None else (latest.major_version if latest else 1)
                return _version_tuple(base_major + 1, 0)
            if working is not None:
                return _version_tuple(working.major, working.minor + 1)
            if latest is not None and latest.lifecycle_phase == PLANNING_PERIOD_STATUS_PUBLISHED:
                return _version_tuple(latest.major_version, latest.minor_version + 1)
            return _version_tuple(1, 1)
        return _version_tuple(0, 1)

    if trigger == VERSION_TRIGGER_STATUS_PUBLISHED:
        if not has_published:
            return _version_tuple(1, 0)
        if working is not None:
            return working
        if latest is not None:
            return _version_tuple(latest.major_version, latest.minor_version)
        return _version_tuple(1, 0)

    if trigger == VERSION_TRIGGER_MANUAL_SAVE:
        if row.status != PLANNING_PERIOD_STATUS_PRELIMINARY:
            raise PlanVersionValidationError("Manual version save requires preliminary status")
        if not has_published:
            if latest is None:
                return _version_tuple(0, 1)
            if latest.major_version == 0:
                return _version_tuple(0, latest.minor_version + 1)
            return _version_tuple(latest.major_version, latest.minor_version + 1)
        if working is not None:
            return _version_tuple(working.major, working.minor + 1)
        if latest is not None:
            return _version_tuple(latest.major_version, latest.minor_version + 1)
        return _version_tuple(1, 1)

    raise PlanVersionValidationError(f"Unknown version trigger: {trigger}")


def validate_version_override(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    major_version: int,
    minor_version: int,
) -> None:
    existing = db.scalar(
        select(PlanningPlanVersion.id).where(
            PlanningPlanVersion.planning_period_id == planning_period_id,
            PlanningPlanVersion.shift_group_id == shift_group_id,
            PlanningPlanVersion.major_version == major_version,
            PlanningPlanVersion.minor_version == minor_version,
        )
    )
    if existing is not None:
        raise PlanVersionValidationError(f"Version {major_version}.{minor_version} already exists")
    latest = _latest_saved_version(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if latest is None:
        return
    candidate = _version_tuple(major_version, minor_version)
    latest_tuple = _version_tuple(latest.major_version, latest.minor_version)
    if compare_versions(candidate, latest_tuple) <= 0:
        raise PlanVersionValidationError(
            f"Version {major_version}.{minor_version} must be greater than {latest.major_version}.{latest.minor_version}"
        )


def _resolve_version_numbers(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    trigger: str,
    major_version: int | None,
    minor_version: int | None,
    is_major_update: bool = False,
) -> VersionTuple:
    suggested = suggest_next_version(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        trigger=trigger,
        is_major_update=is_major_update,
    )
    if major_version is None or minor_version is None:
        return suggested
    candidate = _version_tuple(major_version, minor_version)
    validate_version_override(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        major_version=candidate.major,
        minor_version=candidate.minor,
    )
    return candidate


def snapshot_plan_version(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    major_version: int,
    minor_version: int,
    lifecycle_phase: str,
    trigger: str,
    created_by_user_id: int | None,
    note: str | None,
    actor: str,
    source: str,
) -> PlanningPlanVersion:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    from app.services.matrix import list_planning_cells, list_planning_shift_intents
    from app.services.roster_matrix import list_roster_slot_assignments, list_roster_slots

    validate_version_override(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        major_version=major_version,
        minor_version=minor_version,
    )
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    slots = [
        slot
        for slot in slots
        if slot.shift_template_id is not None and slot.shift_template_id in template_ids
    ]
    slot_ids = {slot.id for slot in slots}
    assignments = [
        assignment
        for assignment in list_roster_slot_assignments(db, planning_period_id=planning_period_id)
        if assignment.roster_slot_id in slot_ids
    ]
    cells = list_planning_cells(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    intents = [
        intent
        for intent in list_planning_shift_intents(db, planning_period_id=planning_period_id)
        if intent.shift_group_id == shift_group_id
    ]
    notes = list(
        db.scalars(
            select(TeamMemberPeriodNote).where(
                TeamMemberPeriodNote.planning_period_id == planning_period_id,
                TeamMemberPeriodNote.shift_group_id == shift_group_id,
            )
        )
    )

    version = PlanningPlanVersion(
        organization_id=organization_id,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        major_version=major_version,
        minor_version=minor_version,
        lifecycle_phase=lifecycle_phase,
        trigger=trigger,
        note=note,
        created_by_user_id=created_by_user_id,
    )
    db.add(version)
    db.flush()

    for slot in slots:
        template = slot.shift_template
        variant = slot.shift_variant
        db.add(
            PlanVersionRosterSlot(
                plan_version_id=version.id,
                shift_template_id=slot.shift_template_id,
                shift_variant_id=slot.shift_variant_id,
                slot_date=slot.slot_date,
                position=slot.position,
                label=slot.label,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                day_class=slot.day_class,
                source=slot.source,
                template_code=template.code if template is not None else None,
                template_name=template.name if template is not None else None,
                variant_label=variant.label if variant is not None else None,
            )
        )

    slot_key_by_id = {
        slot.id: (slot.slot_date, slot.shift_variant_id or 0, slot.position) for slot in slots
    }
    for assignment in assignments:
        key = slot_key_by_id.get(assignment.roster_slot_id)
        if key is None:
            continue
        slot_date, shift_variant_id, position = key
        db.add(
            PlanVersionRosterAssignment(
                plan_version_id=version.id,
                slot_date=slot_date,
                shift_variant_id=shift_variant_id,
                position=position,
                team_member_id=assignment.team_member_id,
                comment=assignment.comment,
                manual_override=assignment.manual_override,
            )
        )

    for cell in cells:
        db.add(
            PlanVersionPlanningCell(
                plan_version_id=version.id,
                team_member_id=cell.team_member_id,
                cell_date=cell.cell_date,
                status=cell.status,
                comment=cell.comment,
                source=cell.source,
            )
        )

    for intent in intents:
        db.add(
            PlanVersionShiftIntent(
                plan_version_id=version.id,
                team_member_id=intent.team_member_id,
                cell_date=intent.cell_date,
                shift_template_id=intent.shift_template_id,
                kind=intent.kind,
                source=intent.source,
            )
        )

    for member_note in notes:
        db.add(
            PlanVersionMemberNote(
                plan_version_id=version.id,
                team_member_id=member_note.team_member_id,
                summary=member_note.summary,
                wishes_response_received=member_note.wishes_response_received,
            )
        )

    record_audit(
        db,
        actor=actor,
        source=source,
        action="save_plan_version",
        entity_type="planning_plan_version",
        entity_id=version.id,
        details={
            "planning_period_id": planning_period_id,
            "shift_group_id": shift_group_id,
            "major_version": major_version,
            "minor_version": minor_version,
            "lifecycle_phase": lifecycle_phase,
            "trigger": trigger,
            "year": period.year,
            "month": period.month,
        },
    )
    db.flush()
    return version


def list_plan_versions(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> PlanVersionListRead:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    versions = list(
        db.scalars(
            select(PlanningPlanVersion)
            .where(
                PlanningPlanVersion.planning_period_id == planning_period_id,
                PlanningPlanVersion.shift_group_id == shift_group_id,
            )
            .order_by(
                PlanningPlanVersion.major_version.desc(),
                PlanningPlanVersion.minor_version.desc(),
                PlanningPlanVersion.created_at.desc(),
            )
        )
    )
    return PlanVersionListRead(
        working_major_version=status_row.working_major_version,
        working_minor_version=status_row.working_minor_version,
        versions=[PlanVersionRead.model_validate(row) for row in versions],
    )


def get_plan_version(
    db: Session,
    *,
    version_id: int,
    planning_period_id: int,
    organization_id: int,
) -> PlanningPlanVersion:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    version = db.get(PlanningPlanVersion, version_id)
    if version is None or version.planning_period_id != planning_period_id:
        raise PlanVersionNotFoundError("Plan version not found")
    if version.organization_id != organization_id:
        raise PlanVersionNotFoundError("Plan version not found")
    return version


def manual_save_plan_version(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    created_by_user_id: int,
    actor: str,
    source: str,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
) -> PlanningPlanVersion:
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if status_row.status != PLANNING_PERIOD_STATUS_PRELIMINARY:
        raise PlanVersionValidationError("Manual version save requires preliminary status")
    version_numbers = _resolve_version_numbers(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        trigger=VERSION_TRIGGER_MANUAL_SAVE,
        major_version=major_version,
        minor_version=minor_version,
    )
    version = snapshot_plan_version(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        major_version=version_numbers.major,
        minor_version=version_numbers.minor,
        lifecycle_phase=PLANNING_PERIOD_STATUS_PRELIMINARY,
        trigger=VERSION_TRIGGER_MANUAL_SAVE,
        created_by_user_id=created_by_user_id,
        note=note,
        actor=actor,
        source=source,
    )
    _set_working_version(status_row, version_numbers)
    db.commit()
    db.refresh(version)
    return version


def _matrix_days(period: PlanningPeriod) -> list[MatrixDay]:
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    return [
        MatrixDay(
            date=date(period.year, period.month, day),
            weekday=date(period.year, period.month, day).strftime("%A"),
        )
        for day in range(1, days_in_month + 1)
    ]


def _team_members_for_group(
    db: Session,
    *,
    organization_id: int,
    shift_group_id: int,
) -> list[MatrixTeamMember]:
    allowed_ids = active_team_member_ids_in_shift_group(db, shift_group_id)
    members = list(
        db.scalars(
            select(TeamMember)
            .where(TeamMember.organization_id == organization_id, TeamMember.is_active.is_(True))
            .order_by(TeamMember.last_name, TeamMember.first_name)
        )
    )
    return [
        MatrixTeamMember(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            nickname=member.nickname,
            email=member.email,
            employment_percentage=member.employment_percentage,
            planning_preferences=member.planning_preferences,
        )
        for member in members
        if member.id in allowed_ids
    ]


def get_plan_version_matrix(
    db: Session,
    *,
    version_id: int,
    planning_period_id: int,
    organization_id: int,
) -> PlanningMatrixRead:
    from app.services.planning_day_status_definitions import (
        ensure_default_planning_day_statuses,
        list_planning_day_status_definitions,
    )

    version = get_plan_version(
        db, version_id=version_id, planning_period_id=planning_period_id, organization_id=organization_id
    )
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    shift_group_id = version.shift_group_id
    cells = list(
        db.scalars(
            select(PlanVersionPlanningCell).where(PlanVersionPlanningCell.plan_version_id == version.id)
        )
    )
    intents = list(
        db.scalars(
            select(PlanVersionShiftIntent).where(PlanVersionShiftIntent.plan_version_id == version.id)
        )
    )
    shift_templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    shift_templates = [template for template in shift_templates if template.id in template_ids]
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    day_status_definitions = [
        PlanningDayStatusDefinitionRead.model_validate(row)
        for row in list_planning_day_status_definitions(db, organization_id=organization_id, active_only=True)
    ]
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    return PlanningMatrixRead(
        planning_period=PlanningPeriodRead.model_validate(period),
        shift_group_planning_status=ShiftGroupPlanningStatusRead.model_validate(status_row),
        team_members=_team_members_for_group(db, organization_id=organization_id, shift_group_id=shift_group_id),
        days=_matrix_days(period),
        cells=[
            PlanningCellRead(
                id=cell.id,
                planning_period_id=planning_period_id,
                shift_group_id=shift_group_id,
                team_member_id=cell.team_member_id,
                cell_date=cell.cell_date,
                status=cell.status,
                comment=cell.comment,
                source=cell.source,
                created_at=version.created_at,
                updated_at=version.created_at,
            )
            for cell in cells
        ],
        day_status_definitions=day_status_definitions,
        shift_templates=[ShiftTemplateRead.model_validate(template) for template in shift_templates],
        shift_intents=[
            PlanningShiftIntentRead(
                id=intent.id,
                planning_period_id=planning_period_id,
                team_member_id=intent.team_member_id,
                cell_date=intent.cell_date,
                shift_group_id=shift_group_id,
                shift_template_id=intent.shift_template_id,
                kind=intent.kind,
                source=intent.source,
                created_at=version.created_at,
                updated_at=version.created_at,
            )
            for intent in intents
        ],
        template_slot_days=[],
    )


def get_plan_version_roster(
    db: Session,
    *,
    version_id: int,
    planning_period_id: int,
    organization_id: int,
) -> RosterMatrixRead:
    from app.services.planning_day_status_definitions import (
        ensure_default_planning_day_statuses,
        list_planning_day_status_definitions,
    )

    version = get_plan_version(
        db, version_id=version_id, planning_period_id=planning_period_id, organization_id=organization_id
    )
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    shift_group_id = version.shift_group_id
    snapshot_slots = list(
        db.scalars(
            select(PlanVersionRosterSlot)
            .where(PlanVersionRosterSlot.plan_version_id == version.id)
            .order_by(
                PlanVersionRosterSlot.slot_date,
                PlanVersionRosterSlot.position,
                PlanVersionRosterSlot.shift_template_id,
                PlanVersionRosterSlot.shift_variant_id,
            )
        )
    )
    snapshot_assignments = list(
        db.scalars(
            select(PlanVersionRosterAssignment).where(
                PlanVersionRosterAssignment.plan_version_id == version.id
            )
        )
    )
    assignment_by_key = {
        (row.slot_date, row.shift_variant_id, row.position): row for row in snapshot_assignments
    }
    cells = list(
        db.scalars(
            select(PlanVersionPlanningCell).where(PlanVersionPlanningCell.plan_version_id == version.id)
        )
    )
    intents = list(
        db.scalars(
            select(PlanVersionShiftIntent).where(PlanVersionShiftIntent.plan_version_id == version.id)
        )
    )
    shift_templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    shift_templates = [template for template in shift_templates if template.id in template_ids]
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    day_status_definitions = [
        PlanningDayStatusDefinitionRead.model_validate(row)
        for row in list_planning_day_status_definitions(db, organization_id=organization_id, active_only=True)
    ]
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    slots_out: list[RosterSlotRead] = []
    assignments_out: list[RosterSlotAssignmentRead] = []
    for index, slot in enumerate(snapshot_slots, start=1):
        slot_id = index
        slots_out.append(
            RosterSlotRead(
                id=slot_id,
                planning_period_id=planning_period_id,
                shift_template_id=slot.shift_template_id,
                shift_variant_id=slot.shift_variant_id,
                slot_date=slot.slot_date,
                position=slot.position,
                label=slot.label,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                day_class=slot.day_class,
                template_code=slot.template_code,
                template_name=slot.template_name,
                variant_label=slot.variant_label,
                source=slot.source,
                created_at=version.created_at,
                updated_at=version.created_at,
            )
        )
        assignment = assignment_by_key.get(
            (slot.slot_date, slot.shift_variant_id or 0, slot.position)
        )
        if assignment is None:
            continue
        assignments_out.append(
            RosterSlotAssignmentRead(
                id=slot_id,
                roster_slot_id=slot_id,
                team_member_id=assignment.team_member_id,
                comment=assignment.comment,
                manual_override=assignment.manual_override,
                source="manual",
                created_at=version.created_at,
                updated_at=version.created_at,
            )
        )
    return RosterMatrixRead(
        planning_period=PlanningPeriodRead.model_validate(period),
        shift_group_planning_status=ShiftGroupPlanningStatusRead.model_validate(status_row),
        team_members=_team_members_for_group(db, organization_id=organization_id, shift_group_id=shift_group_id),
        days=_matrix_days(period),
        shift_templates=[ShiftTemplateRead.model_validate(template) for template in shift_templates],
        slots=slots_out,
        assignments=assignments_out,
        planning_cells=[
            PlanningCellRead(
                id=cell.id,
                planning_period_id=planning_period_id,
                shift_group_id=shift_group_id,
                team_member_id=cell.team_member_id,
                cell_date=cell.cell_date,
                status=cell.status,
                comment=cell.comment,
                source=cell.source,
                created_at=version.created_at,
                updated_at=version.created_at,
            )
            for cell in cells
        ],
        day_status_definitions=day_status_definitions,
        shift_intents=[
            PlanningShiftIntentRead(
                id=intent.id,
                planning_period_id=planning_period_id,
                team_member_id=intent.team_member_id,
                cell_date=intent.cell_date,
                shift_group_id=shift_group_id,
                shift_template_id=intent.shift_template_id,
                kind=intent.kind,
                source=intent.source,
                created_at=version.created_at,
                updated_at=version.created_at,
            )
            for intent in intents
        ],
    )


def apply_preliminary_transition_versioning(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    created_by_user_id: int | None,
    actor: str,
    source: str,
    previous_status: str,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> VersionTuple | None:
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if previous_status == PLANNING_PERIOD_STATUS_DRAFT:
        version_numbers = _resolve_version_numbers(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
            trigger=VERSION_TRIGGER_STATUS_PRELIMINARY,
            major_version=major_version,
            minor_version=minor_version,
        )
        snapshot_plan_version(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
            major_version=version_numbers.major,
            minor_version=version_numbers.minor,
            lifecycle_phase=PLANNING_PERIOD_STATUS_PRELIMINARY,
            trigger=VERSION_TRIGGER_STATUS_PRELIMINARY,
            created_by_user_id=created_by_user_id,
            note=note,
            actor=actor,
            source=source,
        )
        _set_working_version(status_row, version_numbers)
        return version_numbers

    if previous_status == PLANNING_PERIOD_STATUS_PUBLISHED:
        version_numbers = _resolve_version_numbers(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
            trigger=VERSION_TRIGGER_STATUS_PRELIMINARY,
            major_version=major_version,
            minor_version=minor_version,
            is_major_update=is_major_update,
        )
        _set_working_version(status_row, version_numbers)
        return version_numbers

    return None


def apply_publish_transition_versioning(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    created_by_user_id: int | None,
    actor: str,
    source: str,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
) -> PlanningPlanVersion:
    status_row = _require_status_row(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    version_numbers = _resolve_version_numbers(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        trigger=VERSION_TRIGGER_STATUS_PUBLISHED,
        major_version=major_version,
        minor_version=minor_version,
    )
    version = snapshot_plan_version(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
        major_version=version_numbers.major,
        minor_version=version_numbers.minor,
        lifecycle_phase=PLANNING_PERIOD_STATUS_PUBLISHED,
        trigger=VERSION_TRIGGER_STATUS_PUBLISHED,
        created_by_user_id=created_by_user_id,
        note=note,
        actor=actor,
        source=source,
    )
    _set_working_version(status_row, version_numbers)
    if status_row.first_published_at is None:
        status_row.first_published_at = datetime.now(timezone.utc)
    return version


def transition_shift_group_status_with_versioning(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
    target_status: str,
    actor: str,
    source: str,
    audit_action: str,
    created_by_user_id: int | None = None,
    major_version: int | None = None,
    minor_version: int | None = None,
    note: str | None = None,
    is_major_update: bool = False,
) -> PlanningPeriodShiftGroupStatus | None:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None:
        return None
    previous_status = row.status
    if row.status == target_status:
        return row

    if target_status == PLANNING_PERIOD_STATUS_PRELIMINARY:
        apply_preliminary_transition_versioning(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            actor=actor,
            source=source,
            previous_status=previous_status,
            major_version=major_version,
            minor_version=minor_version,
            note=note,
            is_major_update=is_major_update,
        )
    elif target_status == PLANNING_PERIOD_STATUS_PUBLISHED:
        apply_publish_transition_versioning(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            actor=actor,
            source=source,
            major_version=major_version,
            minor_version=minor_version,
            note=note,
        )

    row.status = target_status
    if target_status == PLANNING_PERIOD_STATUS_PUBLISHED:
        row.published_at = datetime.now(timezone.utc)
    else:
        row.published_at = None
    db.flush()
    _sync_period_aggregate_status(db, period)
    record_audit(
        db,
        actor=actor,
        source=source,
        action=audit_action,
        entity_type="planning_period_shift_group_status",
        entity_id=row.id,
        details={
            "planning_period_id": planning_period_id,
            "shift_group_id": shift_group_id,
            "status": target_status,
            "previous_status": previous_status,
            "year": period.year,
            "month": period.month,
            "major_version": row.working_major_version,
            "minor_version": row.working_minor_version,
        },
    )
    db.commit()
    db.refresh(row)
    db.refresh(period)
    return row
