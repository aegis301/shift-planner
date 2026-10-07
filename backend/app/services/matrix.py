import calendar
from datetime import UTC, date, datetime

from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningPeriod,
    PlanningShiftIntent,
    TeamMember,
    TeamMemberPeriodNote,
    TeamMemberPlanningPattern,
)
from app.schemas import (
    MatrixDay,
    MatrixTeamMember,
    MatrixTemplateSlotDay,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellClearItem,
    PlanningCellRead,
    PlanningCellUpsert,
    PlanningDayStatusDefinitionRead,
    PlanningMatrixRead,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
    ShiftTemplateRead,
    TeamMemberPeriodNoteUpsert,
)
from app.services.audit import record_audit
from app.services.authz import team_member_shift_group_ids
from app.services.employment_periods import employment_percentage_on
from app.services.member_planning_patterns import merge_recurring_pattern_cell_target
from app.services.org_time import organization_timezone
from app.services.planning import is_shift_group_planning_open, shift_group_planning_status_read
from app.services.planning_day_status_definitions import (
    assert_valid_planning_cell_status,
    ensure_default_planning_day_statuses,
    list_planning_day_status_definitions,
)
from app.services.planning_period_rosters import (
    assert_member_on_period_roster,
    list_period_roster_team_members,
    team_member_ids_for_period_shift_group,
)
from app.services.shift_groups import (
    list_shift_groups,
    list_shift_template_ids_with_any_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
)
from app.services.shift_intent_bands import slot_band
from app.services.shift_templates import generate_slots_for_month, list_shift_templates


def template_bands_for_month(
    db: Session, *, year: int, month: int, organization_id: int
) -> dict[tuple[date, int], set[str]]:
    """Which day/night bands each template generates slots in, per date of the month."""
    tz = organization_timezone(db, organization_id)
    out: dict[tuple[date, int], set[str]] = {}
    for slot in generate_slots_for_month(db, year=year, month=month, organization_id=organization_id):
        out.setdefault((slot.slot_date, slot.template_id), set()).add(slot_band(slot.starts_at, slot.ends_at, tz))
    return out


def _cell_date_in_period(period: PlanningPeriod, cell_date: date) -> bool:
    return cell_date.year == period.year and cell_date.month == period.month


def _require_period_org(db: Session, planning_period_id: int, organization_id: int) -> PlanningPeriod:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    return period


def list_planning_cells(
    db: Session, *, planning_period_id: int, shift_group_id: int | None = None
) -> list[PlanningCell]:
    stmt = select(PlanningCell).where(PlanningCell.planning_period_id == planning_period_id)
    if shift_group_id is not None:
        stmt = stmt.where(PlanningCell.shift_group_id == shift_group_id)
    stmt = stmt.order_by(PlanningCell.cell_date, PlanningCell.team_member_id)
    return list(db.scalars(stmt))


def _assert_member_in_shift_group(
    db: Session, *, team_member_id: int, shift_group_id: int, planning_period_id: int
) -> None:
    assert_member_on_period_roster(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        team_member_id=team_member_id,
    )


def list_planning_shift_intents(db: Session, *, planning_period_id: int) -> list[PlanningShiftIntent]:
    stmt = (
        select(PlanningShiftIntent)
        .where(PlanningShiftIntent.planning_period_id == planning_period_id)
        .order_by(
            PlanningShiftIntent.cell_date,
            PlanningShiftIntent.team_member_id,
            PlanningShiftIntent.shift_template_id,
            PlanningShiftIntent.band,
        )
    )
    return list(db.scalars(stmt))


def get_planning_matrix(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> PlanningMatrixRead:
    period = _require_period_org(db, planning_period_id, organization_id)

    team_members = list(
        db.scalars(
            select(TeamMember)
            .where(TeamMember.organization_id == organization_id, TeamMember.is_active.is_(True))
            .order_by(TeamMember.last_name, TeamMember.first_name)
        )
    )
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
        team_members = list_period_roster_team_members(
            db,
            planning_period_id=planning_period_id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
        allowed_team_member_ids = {m.id for m in team_members}
        group_template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    days = [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]
    group_status = None
    if shift_group_id is not None:
        group_status = shift_group_planning_status_read(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
        )
    cells = list_planning_cells(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    all_intents = list_planning_shift_intents(db, planning_period_id=planning_period_id)
    shift_templates_out: list[ShiftTemplateRead] = []
    shift_intents_out: list[PlanningShiftIntentRead] = []
    template_slot_days: list[MatrixTemplateSlotDay] = []
    if shift_group_id is not None:
        allowed_team_member_ids = {m.id for m in team_members}
        shift_intents_out = [
            PlanningShiftIntentRead.model_validate(row)
            for row in all_intents
            if row.shift_group_id == shift_group_id and row.team_member_id in allowed_team_member_ids
        ]
        templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
        by_id = {template.id: template for template in templates}
        shift_templates_out = [
            ShiftTemplateRead.model_validate(by_id[tid])
            for tid in sorted(group_template_ids)
            if tid in by_id
        ]
        bands = template_bands_for_month(
            db, year=period.year, month=period.month, organization_id=organization_id
        )
        template_slot_days = [
            MatrixTemplateSlotDay(
                cell_date=d,
                shift_template_id=tid,
                shift_group_id=shift_group_id,
                has_day="day" in day_bands,
                has_night="night" in day_bands,
            )
            for (d, tid), day_bands in sorted(bands.items())
            if tid in group_template_ids
        ]
    else:
        union_templates = list_shift_template_ids_with_any_group(db, organization_id)
        templates_all = list_shift_templates(db, organization_id=organization_id, active_only=True)
        by_id = {template.id: template for template in templates_all}
        shift_templates_out = [
            ShiftTemplateRead.model_validate(by_id[tid])
            for tid in sorted(union_templates)
            if tid in by_id
        ]
        active_groups = list_shift_groups(db, organization_id=organization_id, active_only=True)
        allowed_team_member_ids = {m.id for m in team_members}
        bands = template_bands_for_month(
            db, year=period.year, month=period.month, organization_id=organization_id
        )
        triples: list[tuple[date, int, int, set[str]]] = []
        for group in active_groups:
            g_templates = shift_template_ids_in_shift_group(db, group.id)
            for (d, tid), day_bands in bands.items():
                if tid in g_templates:
                    triples.append((d, tid, group.id, day_bands))
        template_slot_days = [
            MatrixTemplateSlotDay(
                cell_date=d,
                shift_template_id=tid,
                shift_group_id=gid,
                has_day="day" in day_bands,
                has_night="night" in day_bands,
            )
            for d, tid, gid, day_bands in sorted(triples, key=lambda row: row[:3])
        ]
        active_gids = {group.id for group in active_groups}
        shift_intents_out = [
            PlanningShiftIntentRead.model_validate(row)
            for row in all_intents
            if row.team_member_id in allowed_team_member_ids and row.shift_group_id in active_gids
        ]
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    day_status_definitions = [
        PlanningDayStatusDefinitionRead.model_validate(row)
        for row in list_planning_day_status_definitions(
            db, organization_id=organization_id, active_only=False
        )
    ]
    return PlanningMatrixRead(
        planning_period=period,
        shift_group_planning_status=group_status,
        team_members=[
            MatrixTeamMember(
                id=m.id,
                first_name=m.first_name,
                last_name=m.last_name,
                nickname=m.nickname,
                email=m.email,
                employment_percentage=employment_percentage_on(m, date(period.year, period.month, 1)),
                planning_preferences=m.planning_preferences,
            )
            for m in team_members
        ],
        days=days,
        cells=[PlanningCellRead.model_validate(cell) for cell in cells],
        day_status_definitions=day_status_definitions,
        shift_templates=shift_templates_out,
        shift_intents=shift_intents_out,
        template_slot_days=template_slot_days,
    )


def upsert_planning_cell(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    organization_id: int,
    shift_group_id: int,
    actor: str,
    source: str,
) -> PlanningCell:
    period = _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    _assert_member_in_shift_group(
        db,
        team_member_id=payload.team_member_id,
        shift_group_id=shift_group_id,
        planning_period_id=planning_period_id,
    )
    normalized_status = payload.status.strip().lower()
    assert_valid_planning_cell_status(db, organization_id=organization_id, status=normalized_status)
    if not _cell_date_in_period(period, payload.cell_date):
        raise ValueError("Cell date is outside the planning period month")
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.shift_group_id == shift_group_id,
            PlanningCell.team_member_id == payload.team_member_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        cell = PlanningCell(
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=payload.team_member_id,
            cell_date=payload.cell_date,
            status=payload.status,
            comment=payload.comment,
            source=source,
        )
        db.add(cell)
        action = "create"
    else:
        cell.status = payload.status
        cell.comment = payload.comment
        cell.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="planning_cell",
        entity_id=cell.id,
        details={
            "planning_period_id": planning_period_id,
            "team_member_id": payload.team_member_id,
            "cell_date": payload.cell_date.isoformat(),
            "status": payload.status,
        },
    )
    db.commit()
    db.refresh(cell)
    from app.services.time_entries import refresh_derived_window

    refresh_derived_window(
        db,
        organization_id=organization_id,
        member_ids=[cell.team_member_id],
        start_date=cell.cell_date,
        end_date=cell.cell_date,
    )
    db.refresh(cell)
    return cell


def _timestamps_match(stored: datetime, expected: datetime) -> bool:
    def aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    return aware(stored) == aware(expected)


def _precondition_conflicts(cell: PlanningCell | None, payload: PlanningCellUpsert | PlanningCellClearItem) -> bool:
    if "expected_updated_at" not in payload.model_fields_set:
        return False
    if payload.expected_updated_at is None:
        return cell is not None
    if cell is None or cell.updated_at is None:
        return True
    return not _timestamps_match(cell.updated_at, payload.expected_updated_at)


def _find_planning_cell(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    team_member_id: int,
    cell_date: date,
    lock: bool = False,
) -> PlanningCell | None:
    stmt = select(PlanningCell).where(
        PlanningCell.planning_period_id == planning_period_id,
        PlanningCell.shift_group_id == shift_group_id,
        PlanningCell.team_member_id == team_member_id,
        PlanningCell.cell_date == cell_date,
    )
    bind = db.get_bind()
    if lock and bind is not None and bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _precondition_requested(payload: PlanningCellUpsert | PlanningCellClearItem) -> bool:
    return "expected_updated_at" in payload.model_fields_set


def _lock_preconditioned_cells(
    db: Session,
    payloads: list[PlanningCellUpsert] | list[PlanningCellClearItem],
    *,
    planning_period_id: int,
    shift_group_id: int,
) -> None:
    keys = sorted(
        {
            (item.team_member_id, item.cell_date)
            for item in payloads
            if _precondition_requested(item)
        }
    )
    for team_member_id, cell_date in keys:
        _find_planning_cell(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=team_member_id,
            cell_date=cell_date,
            lock=True,
        )


def _updated_at_still(value: datetime):
    moment = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value
    second_text = moment.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    stored = cast(PlanningCell.updated_at, String)
    return or_(
        PlanningCell.updated_at == value,
        stored == second_text,
        stored == f"{second_text}.000000",
    )


def _update_cell_if_current(
    db: Session,
    cell: PlanningCell,
    payload: PlanningCellUpsert,
    *,
    actor: str,
    source: str,
    planning_period_id: int,
) -> bool:
    result = db.execute(
        update(PlanningCell)
        .where(PlanningCell.id == cell.id, _updated_at_still(cell.updated_at))
        .values(
            status=payload.status.strip().lower(),
            comment=payload.comment,
            source=source,
            updated_at=func.now(),
        ),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        return False
    db.refresh(cell)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "team_member_id": payload.team_member_id},
    )
    return True


def _delete_cell_if_current(
    db: Session,
    cell: PlanningCell,
    *,
    actor: str,
    source: str,
    planning_period_id: int,
) -> bool:
    cell_id = cell.id
    team_member_id = cell.team_member_id
    result = db.execute(
        delete(PlanningCell).where(PlanningCell.id == cell.id, _updated_at_still(cell.updated_at)),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        return False
    db.expunge(cell)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="planning_cell",
        entity_id=cell_id,
        details={"planning_period_id": planning_period_id, "team_member_id": team_member_id},
    )
    return True


def _insert_cell_if_absent(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    shift_group_id: int,
    actor: str,
    source: str,
) -> PlanningCell | None:
    cell = PlanningCell(
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        team_member_id=payload.team_member_id,
        cell_date=payload.cell_date,
        status=payload.status.strip().lower(),
        comment=payload.comment,
        source=source,
    )
    try:
        with db.begin_nested():
            db.add(cell)
            db.flush()
    except IntegrityError:
        return None
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "team_member_id": payload.team_member_id},
    )
    return cell


def bulk_upsert_planning_cells(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    *,
    organization_id: int,
    shift_group_id: int,
    actor: str,
    source: str,
) -> tuple[list[PlanningCell], list[tuple[int, date]]]:
    period = _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    for cell_payload in payload.cells:
        assert_valid_planning_cell_status(db, organization_id=organization_id, status=cell_payload.status)
        if not _cell_date_in_period(period, cell_payload.cell_date):
            raise ValueError("Cell date is outside the planning period month")
        _assert_member_in_shift_group(
            db,
            team_member_id=cell_payload.team_member_id,
            shift_group_id=shift_group_id,
            planning_period_id=planning_period_id,
        )
    cells: list[PlanningCell] = []
    conflicts: list[tuple[int, date]] = []
    _lock_preconditioned_cells(
        db,
        payload.cells,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
    )
    for cell_payload in payload.cells:
        precondition = _precondition_requested(cell_payload)
        existing = _find_planning_cell(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=cell_payload.team_member_id,
            cell_date=cell_payload.cell_date,
            lock=precondition,
        )
        if _precondition_conflicts(existing, cell_payload):
            conflicts.append((cell_payload.team_member_id, cell_payload.cell_date))
            continue
        if precondition and existing is None:
            inserted = _insert_cell_if_absent(
                db,
                planning_period_id,
                cell_payload,
                shift_group_id=shift_group_id,
                actor=actor,
                source=source,
            )
            if inserted is None:
                conflicts.append((cell_payload.team_member_id, cell_payload.cell_date))
                continue
            cells.append(inserted)
            continue
        if precondition and existing is not None:
            if not _update_cell_if_current(
                db,
                existing,
                cell_payload,
                actor=actor,
                source=source,
                planning_period_id=planning_period_id,
            ):
                conflicts.append((cell_payload.team_member_id, cell_payload.cell_date))
                continue
            cells.append(existing)
            continue
        cells.append(
            _upsert_planning_cell_no_commit(
                db,
                planning_period_id,
                cell_payload,
                shift_group_id=shift_group_id,
                actor=actor,
                source=source,
            )
        )
    db.commit()
    for cell in cells:
        db.refresh(cell)
    if cells:
        from app.services.time_entries import refresh_derived_window

        refresh_derived_window(
            db,
            organization_id=organization_id,
            member_ids=list({cell.team_member_id for cell in cells}),
            start_date=min(cell.cell_date for cell in cells),
            end_date=max(cell.cell_date for cell in cells),
        )
        for cell in cells:
            db.refresh(cell)
    return cells, conflicts


def _upsert_planning_cell_no_commit(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellUpsert,
    *,
    shift_group_id: int,
    actor: str,
    source: str,
) -> PlanningCell:
    normalized_status = payload.status.strip().lower()
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.shift_group_id == shift_group_id,
            PlanningCell.team_member_id == payload.team_member_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        cell = PlanningCell(
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=payload.team_member_id,
            cell_date=payload.cell_date,
            status=normalized_status,
            comment=payload.comment,
            source=source,
        )
        db.add(cell)
        action = "create"
    else:
        cell.status = normalized_status
        cell.comment = payload.comment
        cell.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "team_member_id": payload.team_member_id},
    )
    return cell


def clear_planning_cell(
    db: Session,
    planning_period_id: int,
    payload: PlanningCellClear,
    *,
    organization_id: int,
    shift_group_id: int,
    actor: str,
    source: str,
) -> tuple[bool, list[tuple[int, date]]]:
    _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    if payload.cells:
        items = payload.cells
    else:
        if payload.team_member_id is None or payload.cell_date is None:
            raise ValueError("team_member_id and cell_date are required")
        item = PlanningCellClearItem(team_member_id=payload.team_member_id, cell_date=payload.cell_date)
        if "expected_updated_at" in payload.model_fields_set:
            item.expected_updated_at = payload.expected_updated_at
        items = [item]
    deleted = False
    conflicts: list[tuple[int, date]] = []
    _lock_preconditioned_cells(
        db,
        items,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
    )
    for item in items:
        precondition = _precondition_requested(item)
        cell = _find_planning_cell(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=item.team_member_id,
            cell_date=item.cell_date,
            lock=precondition,
        )
        if _precondition_conflicts(cell, item):
            conflicts.append((item.team_member_id, item.cell_date))
            continue
        if cell is None:
            continue
        if precondition:
            if not _delete_cell_if_current(
                db,
                cell,
                actor=actor,
                source=source,
                planning_period_id=planning_period_id,
            ):
                conflicts.append((item.team_member_id, item.cell_date))
                continue
            deleted = True
            continue
        record_audit(
            db,
            actor=actor,
            source=source,
            action="delete",
            entity_type="planning_cell",
            entity_id=cell.id,
            details={"planning_period_id": planning_period_id, "team_member_id": item.team_member_id},
        )
        db.delete(cell)
        deleted = True
    db.commit()
    return deleted, conflicts


def list_team_member_period_notes(
    db: Session, *, planning_period_id: int, organization_id: int, shift_group_id: int | None = None
) -> list[TeamMemberPeriodNote]:
    _require_period_org(db, planning_period_id, organization_id)
    stmt = select(TeamMemberPeriodNote).where(TeamMemberPeriodNote.planning_period_id == planning_period_id)
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
        stmt = stmt.where(TeamMemberPeriodNote.shift_group_id == shift_group_id)
    notes = list(db.scalars(stmt.order_by(TeamMemberPeriodNote.team_member_id)))
    if shift_group_id is None:
        return notes
    allowed_team_member_ids = team_member_ids_for_period_shift_group(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    return [note for note in notes if note.team_member_id in allowed_team_member_ids]


def get_team_member_period_note(
    db: Session, *, planning_period_id: int, team_member_id: int, shift_group_id: int
) -> TeamMemberPeriodNote | None:
    return db.scalar(
        select(TeamMemberPeriodNote).where(
            TeamMemberPeriodNote.planning_period_id == planning_period_id,
            TeamMemberPeriodNote.shift_group_id == shift_group_id,
            TeamMemberPeriodNote.team_member_id == team_member_id,
        )
    )


def save_team_member_period_note(
    db: Session,
    planning_period_id: int,
    payload: TeamMemberPeriodNoteUpsert,
    *,
    organization_id: int,
    shift_group_id: int,
    actor: str,
    source: str,
) -> TeamMemberPeriodNote:
    period = _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    _assert_member_in_shift_group(
        db,
        team_member_id=payload.team_member_id,
        shift_group_id=shift_group_id,
        planning_period_id=planning_period_id,
    )
    note = get_team_member_period_note(
        db,
        planning_period_id=planning_period_id,
        team_member_id=payload.team_member_id,
        shift_group_id=shift_group_id,
    )
    note_fields = payload.model_dump(
        exclude={"sync_planning_preferences", "planning_preferences"},
        exclude_unset=False,
    )
    if note is None:
        note = TeamMemberPeriodNote(
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            **note_fields,
        )
        db.add(note)
        action = "create"
    else:
        note.summary = payload.summary
        note.wishes_response_received = payload.wishes_response_received
        action = "update"
    if payload.sync_planning_preferences:
        member = db.get(TeamMember, payload.team_member_id)
        if member is None or member.organization_id != period.organization_id:
            raise ValueError("Team member not found")
        member.planning_preferences = payload.planning_preferences
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="team_member_period_note",
        entity_id=note.id,
        details={"planning_period_id": planning_period_id, "team_member_id": payload.team_member_id},
    )
    db.commit()
    db.refresh(note)
    return note


def _lock_member_for_intent_write(db: Session, team_member_id: int) -> None:
    """Serialize a member's intent writes so `all` and band rows cannot both be committed.

    The rows being normalized may not exist yet, so the lock goes on the team member row.
    """
    bind = db.get_bind()
    if bind is None or bind.dialect.name == "sqlite":
        return
    db.execute(select(TeamMember.id).where(TeamMember.id == team_member_id).with_for_update()).all()


def _intent_audit_details(planning_period_id: int, row: PlanningShiftIntent) -> dict[str, object]:
    return {
        "planning_period_id": planning_period_id,
        "team_member_id": row.team_member_id,
        "cell_date": row.cell_date.isoformat(),
        "shift_template_id": row.shift_template_id,
        "band": row.band,
        "kind": row.kind,
    }


def bulk_upsert_planning_shift_intents(
    db: Session,
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> list[PlanningShiftIntent]:
    """Write wishes and no-gos.

    A wish or no-go needs the template to run on that date. A `day` or `night` band needs the
    template to run in both bands that date. `all` and a specific band never coexist for one
    member, date, group and template: writing `all` replaces the band rows, and writing one
    band over an `all` row keeps the other band at the previous kind.
    """
    period = _require_period_org(db, planning_period_id, organization_id)
    template_bands: dict[tuple[date, int], set[str]] | None = None
    out: dict[int, PlanningShiftIntent] = {}

    def audit(action: str, row: PlanningShiftIntent) -> None:
        record_audit(
            db,
            actor=actor,
            source=source,
            action=action,
            entity_type="planning_shift_intent",
            entity_id=row.id,
            details=_intent_audit_details(planning_period_id, row),
        )

    def remove(row: PlanningShiftIntent) -> None:
        audit("delete", row)
        out.pop(row.id, None)
        db.delete(row)
        db.flush()

    for item in payload.intents:
        if not _cell_date_in_period(period, item.cell_date):
            raise ValueError("Cell date is outside the planning period month")
        require_shift_group(db, item.shift_group_id, organization_id)
        allowed_team_members = team_member_ids_for_period_shift_group(
            db, planning_period_id=planning_period_id, shift_group_id=item.shift_group_id
        )
        if item.team_member_id not in allowed_team_members:
            raise ValueError("Team member is not on the roster for this planning period and shift group")
        allowed_templates = shift_template_ids_in_shift_group(db, item.shift_group_id)
        if item.shift_template_id not in allowed_templates:
            raise ValueError("Shift template is not linked to this shift group")
        if item.kind is not None:
            if template_bands is None:
                template_bands = template_bands_for_month(
                    db, year=period.year, month=period.month, organization_id=organization_id
                )
            day_bands = template_bands.get((item.cell_date, item.shift_template_id), set())
            if not day_bands:
                raise ValueError("Shift template has no shift on this date")
            if item.band != "all" and (item.band not in day_bands or len(day_bands) < 2):
                raise ValueError("Shift template has no separate day and night shifts on this date")
        _lock_member_for_intent_write(db, item.team_member_id)
        rows = list(
            db.scalars(
                select(PlanningShiftIntent).where(
                    PlanningShiftIntent.planning_period_id == planning_period_id,
                    PlanningShiftIntent.team_member_id == item.team_member_id,
                    PlanningShiftIntent.cell_date == item.cell_date,
                    PlanningShiftIntent.shift_group_id == item.shift_group_id,
                    PlanningShiftIntent.shift_template_id == item.shift_template_id,
                )
            )
        )
        by_band = {row.band or "all": row for row in rows}
        if item.band == "all":
            for band in ("day", "night"):
                if band in by_band:
                    remove(by_band.pop(band))
        else:
            other = "night" if item.band == "day" else "day"
            whole = by_band.pop("all", None)
            if whole is not None:
                if other in by_band:
                    remove(whole)
                else:
                    whole.band = other
                    db.flush()
                    audit("update", whole)
                    out[whole.id] = whole
        existing = by_band.get(item.band)
        if item.kind is None:
            if existing is not None:
                remove(existing)
            continue
        if existing is None:
            row = PlanningShiftIntent(
                planning_period_id=planning_period_id,
                team_member_id=item.team_member_id,
                cell_date=item.cell_date,
                shift_group_id=item.shift_group_id,
                shift_template_id=item.shift_template_id,
                band=item.band,
                kind=item.kind,
                source=source,
            )
            db.add(row)
            db.flush()
            audit("create", row)
            out[row.id] = row
        else:
            existing.kind = item.kind
            existing.source = source
            db.flush()
            audit("update", existing)
            out[existing.id] = existing
    db.commit()
    rows_out = list(out.values())
    for row in rows_out:
        db.refresh(row)
    return rows_out


RECURRING_PATTERN_CELL_SOURCE = "recurring_pattern"
_OPEN_PERIOD_STATUSES = frozenset({"draft", "preliminary"})


def _pattern_weekday_key(cell_date: date) -> str:
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[cell_date.weekday()]


def _apply_recurring_weekday_status_for_group(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    team_member_id: int,
    period: PlanningPeriod,
    patterns: list[TeamMemberPlanningPattern],
    actor: str,
    source: str,
) -> None:
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    for day in range(1, days_in_month + 1):
        cell_date = date(period.year, period.month, day)
        cell = db.scalar(
            select(PlanningCell).where(
                PlanningCell.planning_period_id == planning_period_id,
                PlanningCell.shift_group_id == shift_group_id,
                PlanningCell.team_member_id == team_member_id,
                PlanningCell.cell_date == cell_date,
            )
        )
        target = merge_recurring_pattern_cell_target(cell_date, patterns)
        if target is not None:
            if cell is None:
                row = PlanningCell(
                    planning_period_id=planning_period_id,
                    shift_group_id=shift_group_id,
                    team_member_id=team_member_id,
                    cell_date=cell_date,
                    status=target,
                    comment=None,
                    source=RECURRING_PATTERN_CELL_SOURCE,
                )
                db.add(row)
                db.flush()
                record_audit(
                    db,
                    actor=actor,
                    source=source,
                    action="create",
                    entity_type="planning_cell",
                    entity_id=row.id,
                    details={
                        "planning_period_id": planning_period_id,
                        "shift_group_id": shift_group_id,
                        "team_member_id": team_member_id,
                        "cell_date": cell_date.isoformat(),
                        "status": target,
                    },
                )
            elif cell.source == RECURRING_PATTERN_CELL_SOURCE:
                if cell.status != target:
                    cell.status = target
                    db.flush()
                    record_audit(
                        db,
                        actor=actor,
                        source=source,
                        action="update",
                        entity_type="planning_cell",
                        entity_id=cell.id,
                        details={
                            "planning_period_id": planning_period_id,
                            "shift_group_id": shift_group_id,
                            "team_member_id": team_member_id,
                            "cell_date": cell_date.isoformat(),
                            "status": target,
                        },
                    )
        elif cell is not None and cell.source == RECURRING_PATTERN_CELL_SOURCE:
            cid = cell.id
            record_audit(
                db,
                actor=actor,
                source=source,
                action="delete",
                entity_type="planning_cell",
                entity_id=cid,
                details={
                    "planning_period_id": planning_period_id,
                    "shift_group_id": shift_group_id,
                    "team_member_id": team_member_id,
                },
            )
            db.delete(cell)


def apply_recurring_weekday_status_to_one_period(
    db: Session,
    *,
    planning_period_id: int,
    team_member_id: int,
    organization_id: int,
    patterns: list[TeamMemberPlanningPattern],
    actor: str,
    source: str,
) -> None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        return
    member_groups = team_member_shift_group_ids(db, team_member_id)
    if not member_groups:
        member_groups = {group.id for group in list_shift_groups(db, organization_id=organization_id, active_only=True)}
    for shift_group_id in sorted(member_groups):
        if not is_shift_group_planning_open(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=organization_id,
        ):
            continue
        _apply_recurring_weekday_status_for_group(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=team_member_id,
            period=period,
            patterns=patterns,
            actor=actor,
            source=source,
        )


def sync_recurring_weekday_cells_for_member_open_periods(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    patterns: list[TeamMemberPlanningPattern],
    actor: str,
    source: str,
) -> None:
    member_groups = team_member_shift_group_ids(db, team_member_id)
    if not member_groups:
        return
    stmt = select(PlanningPeriod).where(PlanningPeriod.organization_id == organization_id)
    for period in db.scalars(stmt):
        if not any(
            is_shift_group_planning_open(
                db,
                planning_period_id=period.id,
                shift_group_id=group_id,
                organization_id=organization_id,
            )
            for group_id in member_groups
        ):
            continue
        apply_recurring_weekday_status_to_one_period(
            db,
            planning_period_id=period.id,
            team_member_id=team_member_id,
            organization_id=organization_id,
            patterns=patterns,
            actor=actor,
            source=source,
        )
    db.commit()
