import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    PlanningPeriod,
    PlanningPeriodShiftGroupStatus,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    ShiftGroupShiftTemplate,
    ShiftSwapRequest,
    TeamMember,
    TimeEntry,
    User,
)
from app.schemas import (
    HoursLedgerRead,
    PlanningCellBulkResult,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningCellConflict,
    PlanningCellRead,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
    TeamMemberPeriodNoteRead,
    TeamMemberPeriodNoteUpsert,
)
from app.services.authz import get_linked_team_member, team_member_shift_group_ids
from app.services.duty_activity import DUTY_ACTIVITY_KINDS
from app.services.hours_ledger import get_hours_ledger
from app.services.ics_export import (
    build_ics_calendar,
    organization_timezone,
    slot_to_calendar_event,
)
from app.services.matrix import (
    bulk_upsert_planning_cells,
    bulk_upsert_planning_shift_intents,
    clear_planning_cell,
    get_planning_matrix,
    get_team_member_period_note,
    save_team_member_period_note,
)
from app.services.planning import (
    PLANNING_PERIOD_STATUS_DRAFT,
    can_team_member_edit_wishes_matrix,
    is_team_member_roster_visible,
    list_planning_periods,
)
from app.services.shift_swaps import (
    ACTIVE_STATUSES,
    SWAP_KIND_GIVEAWAY,
    SWAP_STATUS_OPEN,
    SWAP_STATUS_TARGETED,
    member_swap_actions,
)
from app.services.tenancy import require_planning_period_in_org

OFFER_PLAN_NOT_OPEN = "plan_not_open"
OFFER_SLOT_IN_PAST = "slot_in_past"
OFFER_NO_SHIFT_GROUP = "no_shift_group"
WISHES_PUBLISHED = "published"


class NoLinkedTeamMember(Exception):
    pass


class MemberWishesForbidden(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def require_linked_member(db: Session, user: User) -> TeamMember:
    member = get_linked_team_member(db, user)
    if member is None or member.organization_id != user.organization_id:
        raise NoLinkedTeamMember()
    return member


def _today() -> date:
    return datetime.now(UTC).date()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _member_assignments(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    start: date,
    end: date,
) -> list[RosterSlotAssignment]:
    return list(
        db.scalars(
            select(RosterSlotAssignment)
            .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
            .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
            .where(
                RosterSlotAssignment.team_member_id == team_member_id,
                PlanningPeriod.organization_id == organization_id,
                RosterSlot.slot_date >= start,
                RosterSlot.slot_date <= end,
            )
            .options(
                joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_template),
                joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_variant),
                joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.planning_period),
            )
            .order_by(RosterSlot.slot_date, RosterSlot.starts_at, RosterSlot.id)
        ).unique()
    )


def _covering_groups(
    db: Session, *, template_ids: set[int], member_groups: set[int]
) -> dict[int, set[int]]:
    if not template_ids or not member_groups:
        return {}
    rows = db.execute(
        select(ShiftGroupShiftTemplate.shift_template_id, ShiftGroupShiftTemplate.shift_group_id).where(
            ShiftGroupShiftTemplate.shift_template_id.in_(template_ids),
            ShiftGroupShiftTemplate.shift_group_id.in_(member_groups),
        )
    ).all()
    covered: dict[int, set[int]] = {}
    for template_id, group_id in rows:
        covered.setdefault(template_id, set()).add(group_id)
    return covered


def _status_map(
    db: Session, *, period_ids: set[int], group_ids: set[int]
) -> dict[tuple[int, int], str]:
    if not period_ids or not group_ids:
        return {}
    rows = db.scalars(
        select(PlanningPeriodShiftGroupStatus).where(
            PlanningPeriodShiftGroupStatus.planning_period_id.in_(period_ids),
            PlanningPeriodShiftGroupStatus.shift_group_id.in_(group_ids),
        )
    ).all()
    return {(row.planning_period_id, row.shift_group_id): row.status for row in rows}


def _group_names(db: Session, group_ids: set[int]) -> dict[int, str]:
    if not group_ids:
        return {}
    rows = db.scalars(select(ShiftGroup).where(ShiftGroup.id.in_(group_ids))).all()
    return {row.id: row.name for row in rows}


def _open_swaps_by_slot(db: Session, slot_ids: set[int]) -> dict[int, ShiftSwapRequest]:
    if not slot_ids:
        return {}
    rows = db.scalars(
        select(ShiftSwapRequest).where(
            ShiftSwapRequest.offered_slot_id.in_(slot_ids),
            ShiftSwapRequest.status.in_(ACTIVE_STATUSES),
        )
    ).all()
    return {row.offered_slot_id: row for row in rows}


def _running_slot_ids(db: Session, *, team_member_id: int, slot_ids: set[int]) -> set[int]:
    if not slot_ids:
        return set()
    rows = db.scalars(
        select(TimeEntry.roster_slot_id).where(
            TimeEntry.team_member_id == team_member_id,
            TimeEntry.roster_slot_id.in_(slot_ids),
            TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
            TimeEntry.ended_at.is_(None),
        )
    ).all()
    return {row for row in rows if row is not None}


def _choose_group(covered: set[int], statuses: dict[tuple[int, int], str], period_id: int) -> int | None:
    if not covered:
        return None
    visible = [group_id for group_id in covered if is_team_member_roster_visible(statuses.get((period_id, group_id), ""))]
    if visible:
        return min(visible)
    return min(covered)


def _offer_reason(status: str | None, slot_date: date, has_group: bool) -> str | None:
    if not has_group:
        return OFFER_NO_SHIFT_GROUP
    if status not in {"preliminary", "published"}:
        return OFFER_PLAN_NOT_OPEN
    if slot_date < _today():
        return OFFER_SLOT_IN_PAST
    return None


def list_member_duties(
    db: Session,
    *,
    user: User,
    start: date,
    end: date,
    limit: int | None = None,
) -> list[dict]:
    if end < start:
        raise ValueError("end must be on or after start")
    member = require_linked_member(db, user)
    assignments = _member_assignments(
        db,
        organization_id=user.organization_id,
        team_member_id=member.id,
        start=start,
        end=end,
    )
    if limit is not None:
        upcoming = [row for row in assignments if row.roster_slot.slot_date >= _today()]
        assignments = upcoming[:limit]
    member_groups = team_member_shift_group_ids(db, member.id)
    template_ids = {
        row.roster_slot.shift_template_id
        for row in assignments
        if row.roster_slot.shift_template_id is not None
    }
    covered = _covering_groups(db, template_ids=template_ids, member_groups=member_groups)
    period_ids = {row.roster_slot.planning_period_id for row in assignments}
    group_ids = {group_id for groups in covered.values() for group_id in groups}
    statuses = _status_map(db, period_ids=period_ids, group_ids=group_ids)
    names = _group_names(db, group_ids)
    slot_ids = {row.roster_slot_id for row in assignments}
    swaps = _open_swaps_by_slot(db, slot_ids)
    running = _running_slot_ids(db, team_member_id=member.id, slot_ids=slot_ids)
    duties: list[dict] = []
    for row in assignments:
        slot = row.roster_slot
        template = slot.shift_template
        variant = slot.shift_variant
        groups = covered.get(slot.shift_template_id or -1, set())
        group_id = _choose_group(groups, statuses, slot.planning_period_id)
        status = statuses.get((slot.planning_period_id, group_id)) if group_id is not None else None
        reason = _offer_reason(status, slot.slot_date, group_id is not None)
        swap = swaps.get(slot.id)
        duties.append(
            {
                "roster_slot_id": slot.id,
                "slot_date": slot.slot_date,
                "starts_at": _as_utc(slot.starts_at) if slot.starts_at is not None else None,
                "ends_at": _as_utc(slot.ends_at) if slot.ends_at is not None else None,
                "template_code": template.code if template is not None else None,
                "template_name": template.name if template is not None else None,
                "variant_label": variant.label if variant is not None else None,
                "category": template.category if template is not None else None,
                "shift_group_id": group_id,
                "shift_group_name": names.get(group_id) if group_id is not None else None,
                "plan_status": status,
                "planning_period_id": slot.planning_period_id,
                "open_swap_request_id": swap.id if swap is not None else None,
                "can_offer": reason is None,
                "can_offer_reason": reason,
                "can_record_duty_activity": slot.starts_at is not None and slot.ends_at is not None,
                "duty_activity_running": slot.id in running,
            }
        )
    return duties


def _next_draft_period(db: Session, *, organization_id: int, member_groups: set[int]) -> dict | None:
    if not member_groups:
        return None
    periods = list_planning_periods(db, organization_id=organization_id)
    period_ids = {period.id for period in periods}
    statuses = _status_map(db, period_ids=period_ids, group_ids=member_groups)
    drafts = [
        period
        for period in periods
        if any(statuses.get((period.id, group_id)) == PLANNING_PERIOD_STATUS_DRAFT for group_id in member_groups)
    ]
    if not drafts:
        return None
    today = _today()
    drafts.sort(key=lambda period: (period.year, period.month))
    upcoming = [period for period in drafts if date(period.year, period.month, 1) >= date(today.year, today.month, 1)]
    chosen = upcoming[0] if upcoming else drafts[-1]
    group_id = next(
        group_id for group_id in sorted(member_groups) if statuses.get((chosen.id, group_id)) == PLANNING_PERIOD_STATUS_DRAFT
    )
    return {
        "planning_period_id": chosen.id,
        "year": chosen.year,
        "month": chosen.month,
        "shift_group_id": group_id,
        "wishes_deadline": None,
    }


def _home_swaps(db: Session, *, organization_id: int, team_member_id: int, member_groups: set[int]) -> list[dict]:
    if not member_groups:
        return []
    rows = db.scalars(
        select(ShiftSwapRequest)
        .where(
            ShiftSwapRequest.organization_id == organization_id,
            ShiftSwapRequest.shift_group_id.in_(member_groups),
            ShiftSwapRequest.status.in_((SWAP_STATUS_OPEN, SWAP_STATUS_TARGETED)),
        )
        .order_by(ShiftSwapRequest.id)
    ).all()
    items: list[dict] = []
    for row in rows:
        if row.status == SWAP_STATUS_TARGETED and row.target_team_member_id != team_member_id:
            continue
        if row.status == SWAP_STATUS_OPEN and (
            row.kind != SWAP_KIND_GIVEAWAY or row.offered_by_team_member_id == team_member_id
        ):
            continue
        allowed, disabled = member_swap_actions(
            row,
            team_member_id=team_member_id,
            eligible_to_claim=row.offered_by_team_member_id != team_member_id,
        )
        if not allowed and not disabled:
            continue
        items.append(
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "shift_group_id": row.shift_group_id,
                "planning_period_id": row.planning_period_id,
                "offered_slot_id": row.offered_slot_id,
                "allowed_actions": allowed,
                "disabled_reasons": disabled,
            }
        )
    return items


def get_member_home(db: Session, *, user: User) -> dict:
    member = require_linked_member(db, user)
    horizon = _today() + timedelta(days=370)
    duties = list_member_duties(db, user=user, start=_today(), end=horizon, limit=5)
    groups = team_member_shift_group_ids(db, member.id)
    return {
        "duties": duties,
        "swap_actions": _home_swaps(
            db, organization_id=user.organization_id, team_member_id=member.id, member_groups=groups
        ),
        "draft_wishes": _next_draft_period(db, organization_id=user.organization_id, member_groups=groups),
    }


def get_member_wishes(
    db: Session,
    *,
    user: User,
    planning_period_id: int,
    shift_group_id: int,
) -> dict:
    member = require_linked_member(db, user)
    require_planning_period_in_org(db, planning_period_id, user.organization_id)
    matrix = get_planning_matrix(
        db,
        planning_period_id,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
    )
    filtered = matrix.model_copy(
        update={
            "team_members": [row for row in matrix.team_members if row.id == member.id],
            "cells": [row for row in matrix.cells if row.team_member_id == member.id],
            "shift_intents": [row for row in matrix.shift_intents if row.team_member_id == member.id],
        }
    )
    status = filtered.shift_group_planning_status.status if filtered.shift_group_planning_status is not None else None
    editable = status is not None and can_team_member_edit_wishes_matrix(status)
    reason = None if editable else WISHES_PUBLISHED
    note = get_team_member_period_note(
        db,
        planning_period_id=planning_period_id,
        team_member_id=member.id,
        shift_group_id=shift_group_id,
    )
    return {
        "planning_period_id": planning_period_id,
        "shift_group_id": shift_group_id,
        "editable": editable,
        "read_only_reason": reason,
        "day_status_definitions": filtered.day_status_definitions,
        "shift_templates": filtered.shift_templates,
        "cells": filtered.cells,
        "intents": filtered.shift_intents,
        "note": TeamMemberPeriodNoteRead.model_validate(note) if note is not None else None,
        "matrix": filtered,
    }


def _assert_wishes_editable(db: Session, *, user: User, planning_period_id: int, shift_group_id: int) -> TeamMember:
    wishes = get_member_wishes(
        db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if not wishes["editable"]:
        raise MemberWishesForbidden(wishes["read_only_reason"] or WISHES_PUBLISHED)
    return require_linked_member(db, user)


def _own_cells(payload: PlanningCellBulkUpsert, team_member_id: int) -> PlanningCellBulkUpsert:
    if any(cell.team_member_id != team_member_id for cell in payload.cells):
        raise MemberWishesForbidden("not_self")
    return payload


def save_member_wishes_cells(
    db: Session,
    *,
    user: User,
    planning_period_id: int,
    shift_group_id: int,
    payload: PlanningCellBulkUpsert,
) -> PlanningCellBulkResult:
    member = _assert_wishes_editable(
        db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    owned = _own_cells(payload, member.id)
    cells, conflicts = bulk_upsert_planning_cells(
        db,
        planning_period_id,
        owned,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
        actor=user.email,
        source="member",
    )
    return PlanningCellBulkResult(
        cells=[PlanningCellRead.model_validate(cell) for cell in cells],
        conflicts=[
            PlanningCellConflict(team_member_id=team_member_id, cell_date=cell_date)
            for team_member_id, cell_date in conflicts
        ],
    )


def clear_member_wishes_cells(
    db: Session,
    *,
    user: User,
    planning_period_id: int,
    shift_group_id: int,
    payload: PlanningCellClear,
) -> dict:
    member = _assert_wishes_editable(
        db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if payload.team_member_id not in (None, member.id):
        raise MemberWishesForbidden("not_self")
    if any(item.team_member_id != member.id for item in payload.cells or []):
        raise MemberWishesForbidden("not_self")
    if payload.team_member_id is None and not payload.cells:
        payload = payload.model_copy(update={"team_member_id": member.id})
    deleted, conflicts = clear_planning_cell(
        db,
        planning_period_id,
        payload,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
        actor=user.email,
        source="member",
    )
    return {
        "deleted": deleted,
        "conflicts": [
            PlanningCellConflict(team_member_id=team_member_id, cell_date=cell_date)
            for team_member_id, cell_date in conflicts
        ],
    }


def save_member_wishes_intents(
    db: Session,
    *,
    user: User,
    planning_period_id: int,
    shift_group_id: int,
    payload: PlanningShiftIntentBulkUpsert,
) -> list[PlanningShiftIntentRead]:
    member = _assert_wishes_editable(
        db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if any(item.team_member_id != member.id or item.shift_group_id != shift_group_id for item in payload.intents):
        raise MemberWishesForbidden("not_self")
    rows = bulk_upsert_planning_shift_intents(
        db,
        planning_period_id,
        payload,
        organization_id=user.organization_id,
        actor=user.email,
        source="member",
    )
    return [PlanningShiftIntentRead.model_validate(row) for row in rows]


def save_member_wishes_note(
    db: Session,
    *,
    user: User,
    planning_period_id: int,
    shift_group_id: int,
    payload: TeamMemberPeriodNoteUpsert,
) -> TeamMemberPeriodNoteRead:
    member = _assert_wishes_editable(
        db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if payload.team_member_id != member.id:
        raise MemberWishesForbidden("not_self")
    note = save_team_member_period_note(
        db,
        planning_period_id,
        payload,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
        actor=user.email,
        source="member",
    )
    return TeamMemberPeriodNoteRead.model_validate(note)


def list_member_swaps(db: Session, *, user: User, status: str | None) -> list[dict]:
    member = require_linked_member(db, user)
    groups = team_member_shift_group_ids(db, member.id)
    if not groups:
        return []
    stmt = select(ShiftSwapRequest).where(
        ShiftSwapRequest.organization_id == user.organization_id,
        ShiftSwapRequest.shift_group_id.in_(groups),
    )
    if status is not None:
        stmt = stmt.where(ShiftSwapRequest.status == status)
    rows = db.scalars(stmt.order_by(ShiftSwapRequest.id)).all()
    items: list[dict] = []
    for row in rows:
        mine = row.offered_by_team_member_id == member.id or row.target_team_member_id == member.id
        giveaway = row.kind == SWAP_KIND_GIVEAWAY and row.status == SWAP_STATUS_OPEN
        if not mine and not giveaway:
            continue
        allowed, disabled = member_swap_actions(
            row,
            team_member_id=member.id,
            eligible_to_claim=row.offered_by_team_member_id != member.id,
        )
        items.append(
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "shift_group_id": row.shift_group_id,
                "planning_period_id": row.planning_period_id,
                "offered_by_team_member_id": row.offered_by_team_member_id,
                "target_team_member_id": row.target_team_member_id,
                "offered_slot_id": row.offered_slot_id,
                "allowed_actions": allowed,
                "disabled_reasons": disabled,
            }
        )
    return items


def get_member_hours(db: Session, *, user: User, start: date, end: date) -> HoursLedgerRead:
    member = require_linked_member(db, user)
    return get_hours_ledger(
        db,
        organization_id=user.organization_id,
        team_member_id=member.id,
        start_date=start,
        end_date=end,
        reveal_duty_activity=True,
        include_reconciliation=False,
    )


def rotate_calendar_token(db: Session, *, user: User) -> str:
    member = require_linked_member(db, user)
    token = secrets.token_urlsafe(32)
    member.calendar_token = token
    db.commit()
    return token


def clear_calendar_token(db: Session, *, user: User) -> None:
    member = require_linked_member(db, user)
    member.calendar_token = None
    db.commit()


def member_calendar_ics(db: Session, *, token: str) -> bytes:
    member = db.scalar(select(TeamMember).where(TeamMember.calendar_token == token))
    if member is None:
        raise ValueError("Invalid calendar token")
    groups = team_member_shift_group_ids(db, member.id)
    start = _today() - timedelta(days=31)
    end = _today() + timedelta(days=370)
    assignments = _member_assignments(
        db,
        organization_id=member.organization_id,
        team_member_id=member.id,
        start=start,
        end=end,
    )
    period_ids = {row.roster_slot.planning_period_id for row in assignments}
    template_ids = {
        row.roster_slot.shift_template_id
        for row in assignments
        if row.roster_slot.shift_template_id is not None
    }
    covered = _covering_groups(db, template_ids=template_ids, member_groups=groups)
    statuses = _status_map(db, period_ids=period_ids, group_ids=groups)
    names = _group_names(db, groups)
    tz = organization_timezone(db, member.organization_id)
    events = []
    for row in assignments:
        slot = row.roster_slot
        groups_for_slot = covered.get(slot.shift_template_id or -1, set())
        group_id = _choose_group(groups_for_slot, statuses, slot.planning_period_id)
        if group_id is None:
            continue
        status = statuses.get((slot.planning_period_id, group_id))
        if status is None or not is_team_member_roster_visible(status):
            continue
        events.append(
            slot_to_calendar_event(
                slot,
                organization_id=member.organization_id,
                shift_group_name=names.get(group_id),
                tz=tz,
            )
        )
    label = f"{member.first_name} {member.last_name}".strip()
    return build_ics_calendar(events, calendar_name=label or "Duties")

