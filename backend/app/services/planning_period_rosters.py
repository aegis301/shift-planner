from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningPeriod,
    PlanningPeriodShiftGroupMember,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    ShiftGroup,
    TeamMember,
    TeamMemberPeriodNote,
)
from app.services.planning import shift_group_planning_status_read
from app.services.shift_groups import (
    require_shift_group,
    shift_template_ids_in_shift_group,
    team_member_ids_in_shift_group_for_period,
)
from app.services.team_members import team_member_planning_display_name


def team_member_ids_for_period_shift_group(
    db: Session, *, planning_period_id: int, shift_group_id: int
) -> set[int]:
    rows = db.scalars(
        select(PlanningPeriodShiftGroupMember.team_member_id).where(
            PlanningPeriodShiftGroupMember.planning_period_id == planning_period_id,
            PlanningPeriodShiftGroupMember.shift_group_id == shift_group_id,
        )
    ).all()
    return set(rows)


def assert_member_on_period_roster(
    db: Session, *, planning_period_id: int, shift_group_id: int, team_member_id: int
) -> None:
    allowed = team_member_ids_for_period_shift_group(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if team_member_id not in allowed:
        raise ValueError("Team member is not on the roster for this planning period and shift group")


def _member_ids_with_period_data(
    db: Session, *, planning_period_id: int, shift_group_id: int
) -> set[int]:
    member_ids: set[int] = set()
    for model, group_field in (
        (PlanningCell, PlanningCell.shift_group_id),
        (PlanningShiftIntent, PlanningShiftIntent.shift_group_id),
        (TeamMemberPeriodNote, TeamMemberPeriodNote.shift_group_id),
    ):
        stmt = select(model.team_member_id).where(model.planning_period_id == planning_period_id, group_field == shift_group_id)
        member_ids.update(db.scalars(stmt).all())

    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    if template_ids:
        assignment_rows = db.scalars(
            select(RosterSlotAssignment.team_member_id)
            .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
            .where(
                RosterSlot.planning_period_id == planning_period_id,
                RosterSlot.shift_template_id.in_(template_ids),
            )
        ).all()
        member_ids.update(assignment_rows)
    return member_ids


def seed_period_shift_group_rosters(
    db: Session, *, planning_period_id: int, organization_id: int, source: str = "seeded"
) -> None:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")

    groups = list(
        db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == organization_id)).all()
    )
    existing = {
        (row.shift_group_id, row.team_member_id)
        for row in db.scalars(
            select(PlanningPeriodShiftGroupMember).where(
                PlanningPeriodShiftGroupMember.planning_period_id == planning_period_id
            )
        )
    }

    for shift_group_id in groups:
        roster_ids = team_member_ids_in_shift_group_for_period(
            db, shift_group_id, year=period.year, month=period.month
        )
        roster_ids |= _member_ids_with_period_data(
            db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
        )
        active_member_ids = set(
            db.scalars(
                select(TeamMember.id).where(
                    TeamMember.id.in_(roster_ids),
                    TeamMember.organization_id == organization_id,
                    TeamMember.is_active.is_(True),
                )
            ).all()
        )
        for team_member_id in active_member_ids:
            if (shift_group_id, team_member_id) in existing:
                continue
            db.add(
                PlanningPeriodShiftGroupMember(
                    planning_period_id=planning_period_id,
                    shift_group_id=shift_group_id,
                    team_member_id=team_member_id,
                    source=source,
                )
            )
            existing.add((shift_group_id, team_member_id))
    db.flush()


def list_period_roster_team_members(
    db: Session,
    *,
    planning_period_id: int,
    organization_id: int,
    shift_group_id: int,
) -> list[TeamMember]:
    require_shift_group(db, shift_group_id, organization_id)
    allowed_ids = team_member_ids_for_period_shift_group(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if not allowed_ids:
        return []
    return list(
        db.scalars(
            select(TeamMember)
            .where(
                TeamMember.organization_id == organization_id,
                TeamMember.id.in_(allowed_ids),
                TeamMember.is_active.is_(True),
            )
            .order_by(TeamMember.last_name, TeamMember.first_name)
        )
    )


class PeriodRosterRefreshPublishedError(Exception):
    pass


class PeriodRosterRefreshConfirmationRequired(Exception):
    def __init__(self, preview: "PeriodRosterRefreshPreview") -> None:
        self.preview = preview
        super().__init__("Removing people with wishes or assignments needs confirmation")


@dataclass(frozen=True)
class PeriodRosterRefreshMember:
    team_member_id: int
    display_name: str


@dataclass(frozen=True)
class PeriodRosterRefreshRemoval:
    team_member_id: int
    display_name: str
    wishes: int
    intents: int
    notes: int
    assignments: int

    @property
    def has_data(self) -> bool:
        return self.wishes + self.intents + self.notes + self.assignments > 0


@dataclass(frozen=True)
class PeriodRosterRefreshPreview:
    added: list[PeriodRosterRefreshMember]
    removed: list[PeriodRosterRefreshRemoval]

    @property
    def requires_confirmation(self) -> bool:
        return any(row.has_data for row in self.removed)


@dataclass(frozen=True)
class PeriodRosterRefreshResult:
    added_count: int
    removed_count: int


def _display_members(db: Session, member_ids: set[int]) -> dict[int, str]:
    if not member_ids:
        return {}
    members = db.scalars(select(TeamMember).where(TeamMember.id.in_(member_ids))).all()
    return {member.id: team_member_planning_display_name(member) for member in members}


def _removal_details(
    db: Session, *, planning_period_id: int, shift_group_id: int, team_member_id: int
) -> tuple[int, int, int, int]:
    wishes = db.scalar(
        select(func.count())
        .select_from(PlanningCell)
        .where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.shift_group_id == shift_group_id,
            PlanningCell.team_member_id == team_member_id,
        )
    )
    intents = db.scalar(
        select(func.count())
        .select_from(PlanningShiftIntent)
        .where(
            PlanningShiftIntent.planning_period_id == planning_period_id,
            PlanningShiftIntent.shift_group_id == shift_group_id,
            PlanningShiftIntent.team_member_id == team_member_id,
        )
    )
    notes = db.scalar(
        select(func.count())
        .select_from(TeamMemberPeriodNote)
        .where(
            TeamMemberPeriodNote.planning_period_id == planning_period_id,
            TeamMemberPeriodNote.shift_group_id == shift_group_id,
            TeamMemberPeriodNote.team_member_id == team_member_id,
        )
    )
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    assignments = 0
    if template_ids:
        assignments = int(
            db.scalar(
                select(func.count())
                .select_from(RosterSlotAssignment)
                .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
                .where(
                    RosterSlot.planning_period_id == planning_period_id,
                    RosterSlot.shift_template_id.in_(template_ids),
                    RosterSlotAssignment.team_member_id == team_member_id,
                )
            )
            or 0
        )
    return int(wishes or 0), int(intents or 0), int(notes or 0), assignments


def preview_period_roster_refresh(
    db: Session,
    *,
    planning_period_id: int,
    organization_id: int,
    shift_group_id: int,
) -> PeriodRosterRefreshPreview:
    period = db.get(PlanningPeriod, planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Planning period not found")
    require_shift_group(db, shift_group_id, organization_id)
    current = team_member_ids_in_shift_group_for_period(
        db, shift_group_id, year=period.year, month=period.month
    )
    existing = team_member_ids_for_period_shift_group(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    names = _display_members(db, current | existing)
    added = [
        PeriodRosterRefreshMember(team_member_id=member_id, display_name=names.get(member_id, str(member_id)))
        for member_id in sorted(current - existing)
    ]
    removed: list[PeriodRosterRefreshRemoval] = []
    for member_id in sorted(existing - current):
        wishes, intents, notes, assignments = _removal_details(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=member_id,
        )
        removed.append(
            PeriodRosterRefreshRemoval(
                team_member_id=member_id,
                display_name=names.get(member_id, str(member_id)),
                wishes=wishes,
                intents=intents,
                notes=notes,
                assignments=assignments,
            )
        )
    return PeriodRosterRefreshPreview(added=added, removed=removed)


def _assert_period_roster_editable(
    db: Session, *, planning_period_id: int, organization_id: int, shift_group_id: int
) -> None:
    group_status = shift_group_planning_status_read(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if group_status is not None and group_status.status == "published":
        raise PeriodRosterRefreshPublishedError("Cannot refresh the period roster for a published shift group")


def _drop_member_period_data(
    db: Session, *, planning_period_id: int, shift_group_id: int, team_member_id: int
) -> None:
    db.execute(
        delete(PlanningCell).where(
            PlanningCell.planning_period_id == planning_period_id,
            PlanningCell.shift_group_id == shift_group_id,
            PlanningCell.team_member_id == team_member_id,
        )
    )
    db.execute(
        delete(PlanningShiftIntent).where(
            PlanningShiftIntent.planning_period_id == planning_period_id,
            PlanningShiftIntent.shift_group_id == shift_group_id,
            PlanningShiftIntent.team_member_id == team_member_id,
        )
    )
    db.execute(
        delete(TeamMemberPeriodNote).where(
            TeamMemberPeriodNote.planning_period_id == planning_period_id,
            TeamMemberPeriodNote.shift_group_id == shift_group_id,
            TeamMemberPeriodNote.team_member_id == team_member_id,
        )
    )
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    if not template_ids:
        return
    slot_ids = db.scalars(
        select(RosterSlot.id).where(
            RosterSlot.planning_period_id == planning_period_id,
            RosterSlot.shift_template_id.in_(template_ids),
        )
    ).all()
    if not slot_ids:
        return
    db.execute(
        delete(RosterSlotAssignment).where(
            RosterSlotAssignment.roster_slot_id.in_(slot_ids),
            RosterSlotAssignment.team_member_id == team_member_id,
        )
    )


def refresh_period_shift_group_roster(
    db: Session,
    *,
    planning_period_id: int,
    organization_id: int,
    shift_group_id: int,
    confirm_removals: bool,
) -> PeriodRosterRefreshResult:
    _assert_period_roster_editable(
        db,
        planning_period_id=planning_period_id,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )
    preview = preview_period_roster_refresh(
        db,
        planning_period_id=planning_period_id,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )
    if preview.requires_confirmation and not confirm_removals:
        raise PeriodRosterRefreshConfirmationRequired(preview)
    for member in preview.added:
        db.add(
            PlanningPeriodShiftGroupMember(
                planning_period_id=planning_period_id,
                shift_group_id=shift_group_id,
                team_member_id=member.team_member_id,
                source="refresh",
            )
        )
    for member in preview.removed:
        _drop_member_period_data(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            team_member_id=member.team_member_id,
        )
        row = db.scalar(
            select(PlanningPeriodShiftGroupMember).where(
                PlanningPeriodShiftGroupMember.planning_period_id == planning_period_id,
                PlanningPeriodShiftGroupMember.shift_group_id == shift_group_id,
                PlanningPeriodShiftGroupMember.team_member_id == member.team_member_id,
            )
        )
        if row is not None:
            db.delete(row)
    db.commit()
    return PeriodRosterRefreshResult(added_count=len(preview.added), removed_count=len(preview.removed))
