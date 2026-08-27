from sqlalchemy import select
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
from app.services.shift_groups import (
    require_shift_group,
    shift_template_ids_in_shift_group,
    team_member_ids_in_shift_group_for_period,
)


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
