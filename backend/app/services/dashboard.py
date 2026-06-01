import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    OrganizationJoinRequest,
    PlanningCell,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftTemplate,
    TeamMember,
)
from app.schemas import (
    AdminDashboardRead,
    DashboardKpiCounts,
    DashboardPeriodCard,
    DashboardPeriodStatusCount,
    DashboardStaffSnapshot,
    DashboardUpcomingSlot,
    DashboardValidationCodeCount,
    DashboardWishesDayStatusCount,
    DashboardWorkloadRow,
    MonthCategorySeries,
    MonthTemplateSeries,
    PlannerDashboardRead,
    ShiftCategoryCount,
    ShiftTemplateCount,
    TeamMemberDashboardRead,

)
from app.services.authz import get_linked_team_member, team_member_shift_group_ids
from app.services.join_requests import list_join_requests_for_org
from app.services.matrix import list_team_member_period_notes
from app.services.organization_directory import list_organization_staff_directory
from app.services.planning import (
    PLANNING_PERIOD_STATUS_DRAFT,
    PLANNING_PERIOD_STATUS_PRELIMINARY,
    PLANNING_PERIOD_STATUS_PUBLISHED,
    can_team_member_edit_wishes_matrix,
    is_team_member_roster_visible,
    list_planning_periods,
)
from app.services.roster_matrix import ensure_roster_slots_for_period, list_roster_slot_assignments, list_roster_slots
from app.services.shift_groups import (
    active_team_member_ids_in_shift_group,
    require_shift_group,
    shift_template_ids_in_shift_group,
)
from app.services.shift_templates import list_shift_templates
from app.services.team_members import list_team_members
from app.services.validation import validate_roster
from app.services.workload import (
    WorkloadAssignmentSlice,
    WorkloadMemberSlice,
    WorkloadSlotSlice,
    build_member_workload_rows,
    member_display_name,
    validation_counts_by_code,
)


def _today() -> date:
    return date.today()


def _resolve_current_period(periods: list[PlanningPeriod]) -> PlanningPeriod | None:
    if not periods:
        return None
    today = _today()
    for period in periods:
        if period.year == today.year and period.month == today.month:
            return period
    return periods[0]


def _periods_in_year(periods: list[PlanningPeriod], year: int) -> list[PlanningPeriod]:
    return [period for period in periods if period.year == year]


def _scope_template_and_member_ids(
    db: Session,
    *,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
) -> tuple[set[int] | None, set[int] | None]:
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
        return (
            shift_template_ids_in_shift_group(db, shift_group_id),
            active_team_member_ids_in_shift_group(db, shift_group_id),
        )
    if shift_group_ids:
        template_ids: set[int] = set()
        member_ids: set[int] = set()
        for group_id in shift_group_ids:
            require_shift_group(db, group_id, organization_id)
            template_ids |= shift_template_ids_in_shift_group(db, group_id)
            member_ids |= active_team_member_ids_in_shift_group(db, group_id)
        return template_ids, member_ids
    return None, None


def _validate_for_scope(
    db: Session,
    planning_period_id: int,
    *,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
):
    if shift_group_id is not None:
        return validate_roster(
            db, planning_period_id, organization_id=organization_id, shift_group_id=shift_group_id
        )
    if shift_group_ids:
        merged = []
        seen: set[tuple[object, ...]] = set()
        for group_id in sorted(shift_group_ids):
            for warning in validate_roster(
                db, planning_period_id, organization_id=organization_id, shift_group_id=group_id
            ):
                key = (warning.code, warning.team_member_id, warning.date, warning.severity, warning.message)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(warning)
        return merged
    return validate_roster(db, planning_period_id, organization_id=organization_id, shift_group_id=None)


def _scoped_slot_ids(
    db: Session,
    *,
    planning_period_id: int,
    template_ids: set[int] | None,
) -> set[int]:
    slots = list_roster_slots(db, planning_period_id=planning_period_id)
    if template_ids is None:
        return {slot.id for slot in slots}
    return {
        slot.id
        for slot in slots
        if slot.shift_template_id is not None and slot.shift_template_id in template_ids
    }


def _period_fill(
    db: Session,
    *,
    period: PlanningPeriod,
    template_ids: set[int] | None,
    member_ids: set[int] | None,
) -> tuple[int, int]:
    slot_ids = _scoped_slot_ids(db, planning_period_id=period.id, template_ids=template_ids)
    slot_count = len(slot_ids)
    if slot_count == 0:
        return 0, 0
    assigned = 0
    for assignment in list_roster_slot_assignments(db, planning_period_id=period.id):
        if assignment.roster_slot_id not in slot_ids:
            continue
        if member_ids is not None and assignment.team_member_id not in member_ids:
            continue
        assigned += 1
    return slot_count, assigned


def _period_card(
    db: Session,
    *,
    period: PlanningPeriod,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
    include_validation: bool,
) -> DashboardPeriodCard:
    template_ids, member_ids = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    ensure_roster_slots_for_period(db, period.id, organization_id)
    slot_count, assigned_count = _period_fill(
        db, period=period, template_ids=template_ids, member_ids=member_ids
    )
    errors = 0
    warnings = 0
    if include_validation and slot_count > 0:
        for warning in _validate_for_scope(
            db,
            period.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
        ):
            if warning.severity == "error":
                errors += 1
            elif warning.severity == "warning":
                warnings += 1
    return DashboardPeriodCard(
        period_id=period.id,
        year=period.year,
        month=period.month,
        status=period.status,
        slot_count=slot_count,
        assigned_count=assigned_count,
        unassigned_count=max(0, slot_count - assigned_count),
        validation_errors=errors,
        validation_warnings=warnings,
    )


def _year_shift_distribution(
    db: Session,
    *,
    organization_id: int,
    year: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
) -> list[MonthCategorySeries]:
    template_ids, member_ids = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    stmt = (
        select(PlanningPeriod.month, ShiftTemplate.category, func.count(RosterSlotAssignment.id))
        .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .join(ShiftTemplate, ShiftTemplate.id == RosterSlot.shift_template_id)
        .where(PlanningPeriod.organization_id == organization_id, PlanningPeriod.year == year)
    )
    if template_ids is not None:
        stmt = stmt.where(RosterSlot.shift_template_id.in_(template_ids))
    if member_ids is not None:
        stmt = stmt.where(RosterSlotAssignment.team_member_id.in_(member_ids))
    stmt = stmt.group_by(PlanningPeriod.month, ShiftTemplate.category).order_by(PlanningPeriod.month)
    by_month: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for month, category, count in db.execute(stmt).all():
        by_month[int(month)][str(category)] += int(count)
    return [
        MonthCategorySeries(
            year=year,
            month=month,
            categories=[ShiftCategoryCount(category=cat, count=cnt) for cat, cnt in sorted(cats.items())],
        )
        for month, cats in sorted(by_month.items())
    ]


def _staff_snapshot(db: Session, *, organization_id: int) -> DashboardStaffSnapshot:
    rows = list_organization_staff_directory(db, organization_id=organization_id)
    snapshot = DashboardStaffSnapshot()
    for row in rows:
        status = row.link_status
        if status == "linked_ok":
            snapshot.linked_ok += 1
        elif status == "team_member_only":
            snapshot.team_member_only += 1
        elif status == "login_unlinked":
            snapshot.login_unlinked += 1
        elif status == "linked_wrong_user":
            snapshot.linked_wrong_user += 1
        elif status == "linked_foreign_user":
            snapshot.linked_foreign_user += 1
        elif status == "login_only":
            snapshot.login_only += 1
    return snapshot


def _count_pending_join_requests(db: Session, *, organization_id: int) -> int:
    return len(list_join_requests_for_org(db, organization_id=organization_id, status="pending"))


def _roster_slices_for_period(
    db: Session,
    *,
    period_id: int,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
) -> tuple[list[WorkloadSlotSlice], list[WorkloadAssignmentSlice], list[WorkloadMemberSlice]]:
    template_ids, member_ids = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    ensure_roster_slots_for_period(db, period_id, organization_id)
    slot_ids = _scoped_slot_ids(db, planning_period_id=period_id, template_ids=template_ids)
    slots_raw = [slot for slot in list_roster_slots(db, planning_period_id=period_id) if slot.id in slot_ids]
    slots: list[WorkloadSlotSlice] = []
    for slot in slots_raw:
        category = slot.shift_template.category if slot.shift_template else None
        slots.append(
            WorkloadSlotSlice(
                id=slot.id,
                shift_template_id=slot.shift_template_id,
                category=category,
                slot_date=slot.slot_date,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
            )
        )
    assignments: list[WorkloadAssignmentSlice] = []
    for row in list_roster_slot_assignments(db, planning_period_id=period_id):
        if row.roster_slot_id not in slot_ids:
            continue
        if member_ids is not None and row.team_member_id not in member_ids:
            continue
        assignments.append(WorkloadAssignmentSlice(roster_slot_id=row.roster_slot_id, team_member_id=row.team_member_id))
    if member_ids is not None:
        allowed = member_ids
    else:
        allowed = {member.id for member in list_team_members(db, organization_id=organization_id, active_only=True)}
    members = [
        WorkloadMemberSlice(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            nickname=member.nickname,
            employment_percentage=member.employment_percentage,
        )
        for member in list_team_members(db, organization_id=organization_id, active_only=True)
        if member.id in allowed
    ]
    return slots, assignments, members


def _category_counts_for_period(
    db: Session,
    *,
    period_id: int,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None,
) -> list[ShiftCategoryCount]:
    slots, assignments, _ = _roster_slices_for_period(
        db,
        period_id=period_id,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    slot_by_id = {slot.id: slot for slot in slots}
    tallies: dict[str, int] = defaultdict(int)
    for assignment in assignments:
        slot = slot_by_id.get(assignment.roster_slot_id)
        if slot is None or slot.category is None:
            continue
        tallies[slot.category] += 1
    return [ShiftCategoryCount(category=cat, count=cnt) for cat, cnt in sorted(tallies.items())]


def _workload_rows_to_schema(rows) -> list[DashboardWorkloadRow]:
    return [
        DashboardWorkloadRow(
            team_member_id=row.team_member_id,
            name=row.name,
            employment_percentage=row.employment_percentage,
            total=row.total,
            on_call_duty=row.on_call_duty,
            standby_duty=row.standby_duty,
            late_duty=row.late_duty,
            other=row.other,
            weekend_holiday_shifts=row.weekend_holiday_shifts,
            conflicts=row.conflicts,
        )
        for row in rows
    ]


def get_admin_dashboard(
    db: Session,
    *,
    organization_id: int,
    year: int | None = None,
    shift_group_id: int | None = None,
) -> AdminDashboardRead:
    selected_year = year if year is not None else _today().year
    periods = list_planning_periods(db, organization_id=organization_id)
    year_periods = _periods_in_year(periods, selected_year)
    current = _resolve_current_period(periods)
    status_tallies: dict[str, int] = defaultdict(int)
    for period in year_periods:
        status_tallies[period.status] += 1
    period_cards = [
        _period_card(
            db,
            period=period,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=None,
            include_validation=current is not None and period.id == current.id,
        )
        for period in year_periods
    ]
    current_card = None
    if current is not None:
        current_card = _period_card(
            db,
            period=current,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=None,
            include_validation=True,
        )
    active_members = list_team_members(db, organization_id=organization_id, active_only=True)
    from app.services.shift_groups import list_shift_groups

    groups = list_shift_groups(db, organization_id=organization_id, active_only=True)
    templates = list_shift_templates(db, organization_id=organization_id, active_only=True)
    return AdminDashboardRead(
        year=selected_year,
        shift_group_id=shift_group_id,
        kpis=DashboardKpiCounts(
            active_team_members=len(active_members),
            active_shift_groups=len(groups),
            active_shift_templates=len(templates),
            pending_join_requests=_count_pending_join_requests(db, organization_id=organization_id),
        ),
        staff_snapshot=_staff_snapshot(db, organization_id=organization_id),
        period_status_counts=[
            DashboardPeriodStatusCount(status=status, count=count)
            for status, count in sorted(status_tallies.items())
        ],
        periods=period_cards,
        year_shift_distribution=_year_shift_distribution(
            db,
            organization_id=organization_id,
            year=selected_year,
            shift_group_id=shift_group_id,
            shift_group_ids=None,
        ),
        current_period=current_card,
    )


def get_planner_dashboard(
    db: Session,
    *,
    organization_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None = None,
    year: int | None = None,
) -> PlannerDashboardRead:
    selected_year = year if year is not None else _today().year
    group = require_shift_group(db, shift_group_id, organization_id) if shift_group_id is not None else None
    _, scoped_member_ids = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    periods = list_planning_periods(db, organization_id=organization_id)
    year_periods = _periods_in_year(periods, selected_year)
    current = _resolve_current_period(periods)
    period_cards = [
        _period_card(
            db,
            period=period,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
            include_validation=current is not None and period.id == current.id,
        )
        for period in year_periods
    ]
    current_card = None
    workload_rows: list[DashboardWorkloadRow] = []
    unassigned = 0
    validation_by_code: list[DashboardValidationCodeCount] = []
    current_categories: list[ShiftCategoryCount] = []
    if current is not None:
        current_card = _period_card(
            db,
            period=current,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
            include_validation=True,
        )
        slots, assignments, members = _roster_slices_for_period(
            db,
            period_id=current.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
        )
        warnings = _validate_for_scope(
            db,
            current.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
        )
        rows, unassigned = build_member_workload_rows(
            slots=slots, assignments=assignments, members=members, warnings=warnings
        )
        workload_rows = _workload_rows_to_schema(rows[:12])
        validation_by_code = [
            DashboardValidationCodeCount(code=code, severity=severity, count=count)
            for code, severity, count in validation_counts_by_code(warnings)
        ]
        current_categories = _category_counts_for_period(
            db,
            period_id=current.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
        )
    notes = (
        list_team_member_period_notes(
            db,
            planning_period_id=current.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
        if current is not None
        else []
    )
    if shift_group_id is not None:
        allowed = active_team_member_ids_in_shift_group(db, shift_group_id)
    elif scoped_member_ids is not None:
        allowed = scoped_member_ids
    else:
        allowed = {member.id for member in list_team_members(db, organization_id=organization_id, active_only=True)}
    if shift_group_id is None and shift_group_ids and current is not None:
        notes = [note for note in notes if note.team_member_id in allowed]
    total_wishes = len(allowed)
    responded = sum(1 for note in notes if note.wishes_response_received and note.team_member_id in allowed)
    wishes_percent = int(round(100 * responded / total_wishes)) if total_wishes else 0
    return PlannerDashboardRead(
        year=selected_year,
        shift_group_id=shift_group_id,
        shift_group_code=group.code if group is not None else "",
        shift_group_name_de=group.name_de if group is not None else "",
        shift_group_name_en=group.name_en if group is not None else "",
        shift_group_member_count=len(allowed),
        current_period=current_card,
        periods=period_cards,
        current_month_categories=current_categories,
        workload_rows=workload_rows,
        unassigned_slots=unassigned,
        validation_by_code=validation_by_code,
        wishes_response_percent=wishes_percent,
        wishes_responded_count=responded,
        wishes_total_count=total_wishes,
    )


def _team_member_visible_periods(periods: list[PlanningPeriod]) -> list[PlanningPeriod]:
    visible: list[PlanningPeriod] = []
    for period in periods:
        if is_team_member_roster_visible(period.status):
            visible.append(period)
        elif can_team_member_edit_wishes_matrix(period.status):
            visible.append(period)
    return visible


def _member_shifts_by_month(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    year: int,
    template_ids: set[int],
) -> list[MonthTemplateSeries]:
    if not template_ids:
        return []
    stmt = (
        select(
            PlanningPeriod.month,
            ShiftTemplate.id,
            ShiftTemplate.code,
            ShiftTemplate.name_de,
            ShiftTemplate.name_en,
            func.count(RosterSlotAssignment.id),
        )
        .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .join(ShiftTemplate, ShiftTemplate.id == RosterSlot.shift_template_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriod.year == year,
            RosterSlotAssignment.team_member_id == team_member_id,
            RosterSlot.shift_template_id.in_(template_ids),
        )
        .group_by(
            PlanningPeriod.month,
            ShiftTemplate.id,
            ShiftTemplate.code,
            ShiftTemplate.name_de,
            ShiftTemplate.name_en,
        )
        .order_by(PlanningPeriod.month, ShiftTemplate.code)
    )
    by_month: dict[int, list[ShiftTemplateCount]] = defaultdict(list)
    for month, template_id, code, name_de, name_en, count in db.execute(stmt).all():
        by_month[int(month)].append(
            ShiftTemplateCount(
                shift_template_id=int(template_id),
                template_code=code,
                template_name_de=name_de,
                template_name_en=name_en,
                count=int(count),
            )
        )
    return [
        MonthTemplateSeries(year=year, month=month, templates=rows)
        for month, rows in sorted(by_month.items())
    ]


def _member_upcoming_shifts(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    template_ids: set[int],
) -> list[DashboardUpcomingSlot]:
    if not template_ids:
        return []
    today = _today()
    visible_statuses = {PLANNING_PERIOD_STATUS_PRELIMINARY, PLANNING_PERIOD_STATUS_PUBLISHED}
    stmt = (
        select(RosterSlot)
        .options(
            joinedload(RosterSlot.shift_template),
            joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlot.planning_period),
        )
        .join(RosterSlotAssignment, RosterSlotAssignment.roster_slot_id == RosterSlot.id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriod.status.in_(visible_statuses),
            RosterSlotAssignment.team_member_id == team_member_id,
            RosterSlot.slot_date >= today,
            RosterSlot.shift_template_id.in_(template_ids),
        )
        .order_by(RosterSlot.slot_date, RosterSlot.starts_at)
    )
    upcoming: list[DashboardUpcomingSlot] = []
    for slot in db.scalars(stmt).unique():
        template = slot.shift_template
        variant = slot.shift_variant
        period = slot.planning_period
        upcoming.append(
            DashboardUpcomingSlot(
                slot_date=slot.slot_date,
                template_code=template.code if template else None,
                template_name_de=template.name_de if template else None,
                template_name_en=template.name_en if template else None,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                category=template.category if template else None,
                variant_label=variant.label if variant else None,
                day_class=slot.day_class,
                period_year=period.year if period else None,
                period_month=period.month if period else None,
            )
        )
    return upcoming


def get_team_member_dashboard(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None = None,
    year: int | None = None,
) -> TeamMemberDashboardRead:
    selected_year = year if year is not None else _today().year
    template_ids, _ = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
    )
    if shift_group_id is not None:
        if team_member_id not in active_team_member_ids_in_shift_group(db, shift_group_id):
            raise ValueError("Team member is not in this shift group")
    elif shift_group_ids:
        member_groups = team_member_shift_group_ids(db, team_member_id)
        if not member_groups.intersection(shift_group_ids):
            raise ValueError("Team member is not in any of these shift groups")
    periods = list_planning_periods(db, organization_id=organization_id)
    visible = _team_member_visible_periods(_periods_in_year(periods, selected_year))
    current = _resolve_current_period(visible) or _resolve_current_period(periods)
    period_cards = [
        _period_card(
            db,
            period=period,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
            include_validation=current is not None and period.id == current.id,
        )
        for period in visible
    ]
    current_card = None
    wishes_statuses: list[DashboardWishesDayStatusCount] = []
    my_errors = 0
    my_warnings = 0
    scoped_template_ids = template_ids or set()
    upcoming = _member_upcoming_shifts(
        db,
        organization_id=organization_id,
        team_member_id=team_member_id,
        template_ids=scoped_template_ids,
    )
    if current is not None:
        current_card = _period_card(
            db,
            period=current,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
            include_validation=True,
        )
        for warning in _validate_for_scope(
            db,
            current.id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
            shift_group_ids=shift_group_ids,
        ):
            if warning.team_member_id != team_member_id:
                continue
            if warning.severity == "error":
                my_errors += 1
            elif warning.severity == "warning":
                my_warnings += 1
        status_tallies: dict[str, int] = defaultdict(int)
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        status_by_day = {
            cell.cell_date: cell.status
            for cell in db.scalars(
                select(PlanningCell).where(
                    PlanningCell.planning_period_id == current.id,
                    PlanningCell.team_member_id == team_member_id,
                )
            )
        }
        for day in range(1, days_in_month + 1):
            cell_date = date(current.year, current.month, day)
            status = status_by_day.get(cell_date)
            if status is None:
                status_tallies["empty"] += 1
            else:
                status_tallies[status] += 1
        wishes_statuses = [
            DashboardWishesDayStatusCount(status=status, count=count)
            for status, count in sorted(status_tallies.items())
        ]

    return TeamMemberDashboardRead(
        year=selected_year,
        shift_group_id=shift_group_id,
        team_member_id=team_member_id,
        periods=period_cards,
        shifts_by_month=_member_shifts_by_month(
            db,
            organization_id=organization_id,
            team_member_id=team_member_id,
            year=selected_year,
            template_ids=template_ids or set(),
        ),
        current_period=current_card,
        wishes_day_statuses=wishes_statuses,
        my_validation_errors=my_errors,
        my_validation_warnings=my_warnings,
        upcoming_slots=upcoming,
    )


def get_team_member_dashboard_for_user(
    db: Session,
    user,
    *,
    shift_group_id: int | None,
    shift_group_ids: set[int] | None = None,
    year: int | None = None,
) -> TeamMemberDashboardRead:
    member = get_linked_team_member(db, user)
    if member is None:
        raise ValueError("No linked team member profile")
    return get_team_member_dashboard(
        db,
        organization_id=user.organization_id,
        team_member_id=member.id,
        shift_group_id=shift_group_id,
        shift_group_ids=shift_group_ids,
        year=year,
    )
