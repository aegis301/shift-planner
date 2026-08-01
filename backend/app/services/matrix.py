import calendar
from datetime import date

from sqlalchemy import select
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
from app.services.member_planning_patterns import merge_recurring_pattern_cell_target
from app.services.planning import is_shift_group_planning_open, shift_group_planning_status_read
from app.services.planning_day_status_definitions import (
    assert_valid_planning_cell_status,
    ensure_default_planning_day_statuses,
    list_planning_day_status_definitions,
)
from app.services.shift_groups import (
    active_team_member_ids_in_shift_group,
    list_shift_groups,
    list_shift_template_ids_with_any_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
)
from app.services.shift_templates import generate_slots_for_month, list_shift_templates


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


def _assert_member_in_shift_group(db: Session, *, team_member_id: int, shift_group_id: int) -> None:
    allowed = active_team_member_ids_in_shift_group(db, shift_group_id)
    if team_member_id not in allowed:
        raise ValueError("Team member is not a member of this shift group")


def list_planning_shift_intents(db: Session, *, planning_period_id: int) -> list[PlanningShiftIntent]:
    stmt = (
        select(PlanningShiftIntent)
        .where(PlanningShiftIntent.planning_period_id == planning_period_id)
        .order_by(
            PlanningShiftIntent.cell_date,
            PlanningShiftIntent.team_member_id,
            PlanningShiftIntent.shift_template_id,
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
        allowed_team_member_ids = active_team_member_ids_in_shift_group(db, shift_group_id)
        team_members = [m for m in team_members if m.id in allowed_team_member_ids]
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
        slot_pairs: set[tuple[date, int]] = set()
        for slot in generate_slots_for_month(db, year=period.year, month=period.month, organization_id=organization_id):
            if slot.template_id in group_template_ids:
                slot_pairs.add((slot.slot_date, slot.template_id))
        template_slot_days = [
            MatrixTemplateSlotDay(cell_date=d, shift_template_id=tid, shift_group_id=shift_group_id)
            for d, tid in sorted(slot_pairs)
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
        slot_triples: set[tuple[date, int, int]] = set()
        active_groups = list_shift_groups(db, organization_id=organization_id, active_only=True)
        allowed_team_member_ids = {m.id for m in team_members}
        for group in active_groups:
            g_templates = shift_template_ids_in_shift_group(db, group.id)
            if not g_templates:
                continue
            for slot in generate_slots_for_month(
                db, year=period.year, month=period.month, organization_id=organization_id
            ):
                if slot.template_id in g_templates:
                    slot_triples.add((slot.slot_date, slot.template_id, group.id))
        template_slot_days = [
            MatrixTemplateSlotDay(cell_date=d, shift_template_id=tid, shift_group_id=gid)
            for d, tid, gid in sorted(slot_triples)
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
            db, organization_id=organization_id, active_only=True
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
                employment_percentage=m.employment_percentage,
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
    _assert_member_in_shift_group(db, team_member_id=payload.team_member_id, shift_group_id=shift_group_id)
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
) -> list[PlanningCell]:
    period = _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    for cell_payload in payload.cells:
        assert_valid_planning_cell_status(db, organization_id=organization_id, status=cell_payload.status)
        if not _cell_date_in_period(period, cell_payload.cell_date):
            raise ValueError("Cell date is outside the planning period month")
        _assert_member_in_shift_group(db, team_member_id=cell_payload.team_member_id, shift_group_id=shift_group_id)
    cells = [
        _upsert_planning_cell_no_commit(
            db,
            planning_period_id,
            cell_payload,
            shift_group_id=shift_group_id,
            actor=actor,
            source=source,
        )
        for cell_payload in payload.cells
    ]
    db.commit()
    for cell in cells:
        db.refresh(cell)
    return cells


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
) -> bool:
    _require_period_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    cell = db.scalar(
        select(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.shift_group_id == shift_group_id,
            PlanningCell.team_member_id == payload.team_member_id,
            PlanningCell.cell_date == payload.cell_date,
        )
    )
    if cell is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="planning_cell",
        entity_id=cell.id,
        details={"planning_period_id": planning_period_id, "team_member_id": payload.team_member_id},
    )
    db.delete(cell)
    db.commit()
    return True


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
    allowed_team_member_ids = active_team_member_ids_in_shift_group(db, shift_group_id)
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
    _assert_member_in_shift_group(db, team_member_id=payload.team_member_id, shift_group_id=shift_group_id)
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


def bulk_upsert_planning_shift_intents(
    db: Session,
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> list[PlanningShiftIntent]:
    period = _require_period_org(db, planning_period_id, organization_id)
    out: list[PlanningShiftIntent] = []
    for item in payload.intents:
        if not _cell_date_in_period(period, item.cell_date):
            raise ValueError("Cell date is outside the planning period month")
        require_shift_group(db, item.shift_group_id, organization_id)
        allowed_team_members = active_team_member_ids_in_shift_group(db, item.shift_group_id)
        if item.team_member_id not in allowed_team_members:
            raise ValueError("Team member is not a member of this shift group")
        allowed_templates = shift_template_ids_in_shift_group(db, item.shift_group_id)
        if item.shift_template_id not in allowed_templates:
            raise ValueError("Shift template is not linked to this shift group")
        existing = db.scalar(
            select(PlanningShiftIntent).where(
                PlanningShiftIntent.planning_period_id == planning_period_id,
                PlanningShiftIntent.team_member_id == item.team_member_id,
                PlanningShiftIntent.cell_date == item.cell_date,
                PlanningShiftIntent.shift_group_id == item.shift_group_id,
                PlanningShiftIntent.shift_template_id == item.shift_template_id,
            )
        )
        if item.kind is None:
            if existing is not None:
                record_audit(
                    db,
                    actor=actor,
                    source=source,
                    action="delete",
                    entity_type="planning_shift_intent",
                    entity_id=existing.id,
                    details={
                        "planning_period_id": planning_period_id,
                        "team_member_id": item.team_member_id,
                        "cell_date": item.cell_date.isoformat(),
                    },
                )
                db.delete(existing)
            continue
        if existing is None:
            row = PlanningShiftIntent(
                planning_period_id=planning_period_id,
                team_member_id=item.team_member_id,
                cell_date=item.cell_date,
                shift_group_id=item.shift_group_id,
                shift_template_id=item.shift_template_id,
                kind=item.kind,
                source=source,
            )
            db.add(row)
            db.flush()
            record_audit(
                db,
                actor=actor,
                source=source,
                action="create",
                entity_type="planning_shift_intent",
                entity_id=row.id,
                details={
                    "planning_period_id": planning_period_id,
                    "team_member_id": item.team_member_id,
                    "cell_date": item.cell_date.isoformat(),
                    "shift_template_id": item.shift_template_id,
                    "kind": item.kind,
                },
            )
            out.append(row)
        else:
            existing.kind = item.kind
            existing.source = source
            db.flush()
            record_audit(
                db,
                actor=actor,
                source=source,
                action="update",
                entity_type="planning_shift_intent",
                entity_id=existing.id,
                details={
                    "planning_period_id": planning_period_id,
                    "team_member_id": item.team_member_id,
                    "kind": item.kind,
                },
            )
            out.append(existing)
    db.commit()
    for row in out:
        db.refresh(row)
    return out


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
