from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ShiftGroup, TeamMember, TeamMemberShiftGroup, User, UserShiftGroup

ROLE_ADMIN = "admin"
ROLE_PLANNER = "planner"
ROLE_TEAM_MEMBER = "team_member"
ROLE_APPLICANT = "applicant"


def is_admin(user: User) -> bool:
    return user.role == ROLE_ADMIN


def is_shift_planner_role(user: User) -> bool:
    return user.role == ROLE_PLANNER


def can_use_planning_ui(user: User) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_PLANNER)


def can_access_team_member_portal(db: Session, user: User) -> bool:
    return get_linked_team_member(db, user) is not None


def is_pure_team_member(user: User) -> bool:
    return user.role == ROLE_TEAM_MEMBER


def is_applicant(user: User) -> bool:
    return user.role == ROLE_APPLICANT


def get_linked_team_member(db: Session, user: User) -> TeamMember | None:
    return db.scalar(
        select(TeamMember).where(
            TeamMember.user_id == user.id,
            TeamMember.organization_id == user.organization_id,
        )
    )


def team_member_shift_group_ids(db: Session, team_member_id: int) -> set[int]:
    return set(
        db.scalars(select(TeamMemberShiftGroup.shift_group_id).where(TeamMemberShiftGroup.team_member_id == team_member_id))
    )


def list_shift_groups_for_team_member(db: Session, team_member_id: int) -> list[ShiftGroup]:
    gids = team_member_shift_group_ids(db, team_member_id)
    if not gids:
        return []
    stmt = select(ShiftGroup).where(ShiftGroup.id.in_(gids)).order_by(ShiftGroup.display_order, ShiftGroup.code)
    return list(db.scalars(stmt))


def planner_shift_group_ids(db: Session, user: User) -> set[int]:
    if is_admin(user):
        return set(
            db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == user.organization_id)).all()
        )
    if is_shift_planner_role(user):
        stmt = (
            select(UserShiftGroup.shift_group_id)
            .join(ShiftGroup, ShiftGroup.id == UserShiftGroup.shift_group_id)
            .where(UserShiftGroup.user_id == user.id, ShiftGroup.organization_id == user.organization_id)
        )
        return set(db.scalars(stmt).all())
    return set()


def require_shift_group_id_for_planner_scope(user: User, shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise ValueError("shift_group_id is required for this account")
    return shift_group_id


def assert_planning_shift_group_scope(db: Session, user: User, shift_group_id: int | None) -> None:
    if not can_use_planning_ui(user):
        raise PermissionError("Planning access required")
    if is_admin(user):
        if shift_group_id is None:
            return
        group = db.get(ShiftGroup, shift_group_id)
        if group is None or group.organization_id != user.organization_id:
            raise PermissionError("Shift group not found")
        return
    allowed = planner_shift_group_ids(db, user)
    if not allowed:
        raise PermissionError("No shift groups assigned for planning")
    if shift_group_id is None:
        raise PermissionError("shift_group_id is required")
    if shift_group_id not in allowed:
        raise PermissionError("Not a member of this shift group")


def require_shift_group_id_for_team_member(shift_group_id: int | None) -> int:
    if shift_group_id is None:
        raise ValueError("shift_group_id is required for team member accounts")
    return shift_group_id


def assert_team_member_shift_group_access(db: Session, user: User, shift_group_id: int) -> TeamMember:
    if can_use_planning_ui(user) and get_linked_team_member(db, user) is None:
        raise AssertionError("assert_team_member_shift_group_access is for linked team member accounts")
    member = get_linked_team_member(db, user)
    if member is None:
        raise PermissionError("Team member profile is not linked to this account")
    if member.organization_id != user.organization_id:
        raise PermissionError("Team member profile is not linked to this account")
    if shift_group_id not in team_member_shift_group_ids(db, member.id):
        raise PermissionError("Not a member of this shift group")
    return member


def assert_team_member_cell_access(user: User, member: TeamMember, payload_team_member_id: int) -> None:
    if can_use_planning_ui(user):
        return
    if payload_team_member_id != member.id:
        raise PermissionError("Can only edit your own planning row")


def roles_allowed_for_team_member_user_link() -> set[str]:
    return {ROLE_ADMIN, ROLE_PLANNER, ROLE_TEAM_MEMBER, ROLE_APPLICANT}


def use_team_member_filtered_matrix_view(db: Session, user: User) -> bool:
    if is_admin(user):
        return False
    if is_pure_team_member(user):
        return True
    if is_shift_planner_role(user) and get_linked_team_member(db, user) is not None:
        return True
    return False


def assert_team_member_patterns_read(db: Session, user: User, team_member_id: int) -> None:
    if is_admin(user):
        return
    if can_use_planning_ui(user):
        from app.services.team_members import list_team_members_for_planner

        allowed_ids = {member.id for member in list_team_members_for_planner(db, user)}
        if team_member_id not in allowed_ids:
            raise PermissionError("Team member is outside planner scope")
        return
    member = get_linked_team_member(db, user)
    if member is not None and member.id == team_member_id:
        return
    raise PermissionError("Not allowed to read planning patterns for this team member")


def assert_team_member_patterns_write(db: Session, user: User, team_member_id: int) -> None:
    if is_admin(user):
        return
    member = get_linked_team_member(db, user)
    if member is not None and member.id == team_member_id:
        return
    raise PermissionError("Not allowed to edit planning patterns for this team member")


def assert_team_member_property_values_read(db: Session, user: User, team_member_id: int) -> None:
    if is_admin(user):
        return
    member = get_linked_team_member(db, user)
    if member is not None and member.id == team_member_id:
        return
    raise PermissionError("Not allowed to read property values for this team member")


def writable_property_definition_ids_for_user(db: Session, user: User, team_member_id: int) -> set[int] | None:
    if is_admin(user):
        return None
    member = get_linked_team_member(db, user)
    if member is None or member.id != team_member_id:
        raise PermissionError("Not allowed to edit property values for this team member")
    from app.models import TeamMemberPropertyDefinition
    from sqlalchemy import select

    rows = db.scalars(
        select(TeamMemberPropertyDefinition.id).where(
            TeamMemberPropertyDefinition.organization_id == user.organization_id,
            TeamMemberPropertyDefinition.is_active.is_(True),
            TeamMemberPropertyDefinition.editable_by_team_member.is_(True),
        )
    )
    return set(rows.all())


def assert_team_member_property_values_write(db: Session, user: User, team_member_id: int) -> set[int] | None:
    return writable_property_definition_ids_for_user(db, user, team_member_id)
