import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import PlanningPeriod, RosterSlot, RosterSlotAssignment, TeamMember
from app.schemas import (
    MatrixDay,
    MatrixTeamMember,
    PlanningCellRead,
    PlanningDayStatusDefinitionRead,
    PlanningShiftIntentRead,
    RosterMatrixRead,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    RosterSlotRead,
)
from app.services.audit import record_audit
from app.services.constraints import evaluate_assignment_constraints, find_blocking_constraint, resolve_slot_constraints
from app.services.matrix import list_planning_cells, list_planning_shift_intents
from app.services.planning_day_status_definitions import (
    ensure_default_planning_day_statuses,
    list_planning_day_status_definitions,
)
from app.services.member_planning_patterns import evaluate_member_planning_patterns, list_team_member_planning_patterns
from app.services.shift_groups import (
    active_team_member_ids_in_shift_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
    team_member_may_cover_template,
)
from app.services.team_member_property_values import property_value_dict_for_member
from app.services.tenancy import require_planning_period_in_org
from app.services.shift_templates import generate_slots_for_month, list_shift_templates


def _period_days(period: PlanningPeriod) -> list[MatrixDay]:
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    return [
        MatrixDay(date=date(period.year, period.month, day), weekday=date(period.year, period.month, day).strftime("%A"))
        for day in range(1, days_in_month + 1)
    ]


def list_roster_slots(db: Session, *, planning_period_id: int) -> list[RosterSlot]:
    stmt = (
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.shift_variant))
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_template_id, RosterSlot.shift_variant_id)
    )
    return list(db.scalars(stmt))


def list_roster_slot_assignments(db: Session, *, planning_period_id: int) -> list[RosterSlotAssignment]:
    stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot)
        .options(
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.planning_period),
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_template),
            joinedload(RosterSlotAssignment.team_member),
        )
        .where(RosterSlot.planning_period_id == planning_period_id)
        .order_by(RosterSlot.slot_date, RosterSlot.position, RosterSlot.shift_template_id, RosterSlot.shift_variant_id)
    )
    return list(db.scalars(stmt))


def ensure_roster_slots_for_period(db: Session, planning_period_id: int, organization_id: int) -> list[RosterSlot]:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)

    generated_slots = generate_slots_for_month(db, year=period.year, month=period.month, organization_id=organization_id)
    if not generated_slots:
        return []

    existing = {
        (slot.slot_date, slot.shift_variant_id, slot.position)
        for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id))
    }
    for generated in generated_slots:
        key = (generated.slot_date, generated.variant_id, generated.position)
        if key in existing:
            continue
        db.add(
            RosterSlot(
                planning_period_id=planning_period_id,
                shift_template_id=generated.template_id,
                shift_variant_id=generated.variant_id,
                slot_date=generated.slot_date,
                position=generated.position,
                label=generated.label,
                starts_at=generated.starts_at,
                ends_at=generated.ends_at,
                day_class=generated.day_class,
                source="template",
            )
        )
        existing.add(key)
    db.flush()
    return list_roster_slots(db, planning_period_id=planning_period_id)


def reset_roster_slots_for_period(
    db: Session, planning_period_id: int, *, organization_id: int, actor: str, source: str
) -> list[RosterSlot]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    slot_ids = list(db.scalars(select(RosterSlot.id).where(RosterSlot.planning_period_id == planning_period_id)))
    if slot_ids:
        for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids))):
            db.delete(assignment)
    for slot in db.scalars(select(RosterSlot).where(RosterSlot.planning_period_id == planning_period_id)):
        db.delete(slot)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="regenerate",
        entity_type="planning_period_roster_slots",
        entity_id=planning_period_id,
        details={"cleared_slot_count": len(slot_ids)},
    )
    slots = ensure_roster_slots_for_period(db, planning_period_id, organization_id)
    db.commit()
    return slots


def get_roster_matrix(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> RosterMatrixRead:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)

    ensure_roster_slots_for_period(db, planning_period_id, organization_id)
    db.commit()

    team_members = list(
        db.scalars(
            select(TeamMember)
            .where(TeamMember.organization_id == organization_id, TeamMember.is_active.is_(True))
            .order_by(TeamMember.last_name, TeamMember.first_name)
        )
    )
    shift_templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    assignments = list_roster_slot_assignments(db, planning_period_id=planning_period_id)
    planning_cells = list_planning_cells(db, planning_period_id=planning_period_id)
    shift_intents = [PlanningShiftIntentRead.model_validate(row) for row in list_planning_shift_intents(db, planning_period_id=planning_period_id)]
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
        allowed_team_member_ids = active_team_member_ids_in_shift_group(db, shift_group_id)
        template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
        team_members = [m for m in team_members if m.id in allowed_team_member_ids]
        slots = [slot for slot in slots if slot.shift_template_id is not None and slot.shift_template_id in template_ids]
        visible_template_ids = {slot.shift_template_id for slot in slots}
        shift_templates = [template for template in shift_templates if template.id in visible_template_ids]
        slot_ids = {slot.id for slot in slots}
        assignments = [assignment for assignment in assignments if assignment.roster_slot_id in slot_ids]
        planning_cells = [cell for cell in planning_cells if cell.team_member_id in allowed_team_member_ids]
        shift_intents = [
            row for row in shift_intents if row.shift_group_id == shift_group_id and row.team_member_id in allowed_team_member_ids
        ]
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    day_status_definitions = [
        PlanningDayStatusDefinitionRead.model_validate(row)
        for row in list_planning_day_status_definitions(
            db, organization_id=organization_id, active_only=True
        )
    ]
    return RosterMatrixRead(
        planning_period=period,
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
        days=_period_days(period),
        shift_templates=shift_templates,
        slots=[_read_slot(slot) for slot in slots],
        assignments=[RosterSlotAssignmentRead.model_validate(assignment) for assignment in assignments],
        planning_cells=[PlanningCellRead.model_validate(cell) for cell in planning_cells],
        day_status_definitions=day_status_definitions,
        shift_intents=shift_intents,
    )


def _read_slot(slot: RosterSlot) -> RosterSlotRead:
    template = slot.shift_template
    variant = slot.shift_variant
    return RosterSlotRead(
        id=slot.id,
        planning_period_id=slot.planning_period_id,
        shift_template_id=slot.shift_template_id,
        shift_variant_id=slot.shift_variant_id,
        slot_date=slot.slot_date,
        position=slot.position,
        label=slot.label,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        day_class=slot.day_class,
        template_code=template.code if template else None,
        template_name=template.name if template else None,
        variant_label=variant.label if variant else None,
        category=template.category if template else None,
        source=slot.source,
        created_at=slot.created_at,
        updated_at=slot.updated_at,
    )


def _team_member_has_template_no_go(
    db: Session,
    *,
    planning_period_id: int,
    team_member_id: int,
    slot_date: date,
    shift_template_id: int | None,
) -> bool:
    if shift_template_id is None:
        return False
    for intent in list_planning_shift_intents(db, planning_period_id=planning_period_id):
        if intent.kind != "no_go":
            continue
        if intent.team_member_id != team_member_id:
            continue
        if intent.cell_date != slot_date:
            continue
        if intent.shift_template_id == shift_template_id:
            return True
    return False


def upsert_roster_slot_assignment(
    db: Session,
    payload: RosterSlotAssignmentUpsert,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> RosterSlotAssignment:
    slot = db.scalars(
        select(RosterSlot)
        .where(RosterSlot.id == payload.roster_slot_id)
        .options(
            joinedload(RosterSlot.planning_period),
            joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlot.shift_template),
        )
    ).first()
    if slot is None:
        raise ValueError("Roster slot not found")
    require_planning_period_in_org(db, slot.planning_period_id, organization_id)
    if not team_member_may_cover_template(db, team_member_id=payload.team_member_id, shift_template_id=slot.shift_template_id):
        raise ValueError("Team member is not a member of a shift group that covers this template")
    if not payload.manual_override and _team_member_has_template_no_go(
        db,
        planning_period_id=slot.planning_period_id,
        team_member_id=payload.team_member_id,
        slot_date=slot.slot_date,
        shift_template_id=slot.shift_template_id,
    ):
        raise ValueError("Team member marked this shift template as a no-go on that day")
    resolved_constraints = resolve_slot_constraints(db, slot)
    period = slot.planning_period
    if period is None:
        period = db.get(PlanningPeriod, slot.planning_period_id)
    org_id = period.organization_id if period is not None else organization_id
    member_property_values = property_value_dict_for_member(
        db, team_member_id=payload.team_member_id, organization_id=org_id
    )
    member_assignments = [
        row
        for row in list_roster_slot_assignments(db, planning_period_id=slot.planning_period_id)
        if row.team_member_id == payload.team_member_id
    ]
    member_cells = [
        row
        for row in list_planning_cells(db, planning_period_id=slot.planning_period_id)
        if row.team_member_id == payload.team_member_id
    ]
    preflight_warnings: list = []
    if resolved_constraints:
        preflight_warnings.extend(
            evaluate_assignment_constraints(
                db=db,
                slot=slot,
                team_member_id=payload.team_member_id,
                resolved_constraints=resolved_constraints,
                assigned_slots_for_member=member_assignments,
                planning_cells_for_member=member_cells,
                member_property_values=member_property_values,
            )
        )
    member_patterns = list_team_member_planning_patterns(
        db,
        team_member_id=payload.team_member_id,
        organization_id=organization_id,
        active_only=True,
    )
    if member_patterns:
        preflight_warnings.extend(
            evaluate_member_planning_patterns(
                db=db,
                slot=slot,
                team_member_id=payload.team_member_id,
                patterns=member_patterns,
            )
        )
    blocking = find_blocking_constraint(preflight_warnings)
    if blocking is not None:
        raise ValueError(blocking.message)
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == payload.roster_slot_id)
    )
    if assignment is None:
        assignment = RosterSlotAssignment(
            roster_slot_id=payload.roster_slot_id,
            team_member_id=payload.team_member_id,
            comment=payload.comment,
            manual_override=payload.manual_override,
            source=source,
        )
        db.add(assignment)
        action = "create"
    else:
        assignment.team_member_id = payload.team_member_id
        assignment.comment = payload.comment
        assignment.manual_override = payload.manual_override
        assignment.source = source
        action = "update"
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action=action,
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={
            "planning_period_id": slot.planning_period_id,
            "roster_slot_id": payload.roster_slot_id,
            "team_member_id": payload.team_member_id,
        },
    )
    db.commit()
    db.refresh(assignment)
    return assignment


def clear_roster_slot_assignment(
    db: Session,
    payload: RosterSlotAssignmentClear,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == payload.roster_slot_id)
    )
    if assignment is None:
        return False
    slot = db.get(RosterSlot, payload.roster_slot_id)
    if slot is None:
        return False
    require_planning_period_in_org(db, slot.planning_period_id, organization_id)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={"roster_slot_id": payload.roster_slot_id},
    )
    db.delete(assignment)
    db.commit()
    return True
