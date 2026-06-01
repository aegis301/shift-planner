from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planner, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import AdminDashboardRead, PlannerDashboardRead, TeamMemberDashboardRead
from app.services.authz import (
    assert_planning_shift_group_scope,
    can_access_team_member_portal,
    get_linked_team_member,
    is_admin,
    is_shift_planner_role,
    list_shift_groups_for_team_member,
    planner_shift_group_ids,
)
from app.services.dashboard import (
    get_admin_dashboard,
    get_planner_dashboard,
    get_team_member_dashboard_for_user,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/admin", response_model=AdminDashboardRead)
def get_dashboard_admin(
    year: int | None = Query(default=None),
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    return get_admin_dashboard(
        db, organization_id=user.organization_id, year=year, shift_group_id=shift_group_id
    )


@router.get("/planner", response_model=PlannerDashboardRead)
def get_dashboard_planner(
    shift_group_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    scoped_group_ids: set[int] | None = None
    if shift_group_id is not None:
        try:
            assert_planning_shift_group_scope(db, user, shift_group_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    elif is_shift_planner_role(user) and not is_admin(user):
        scoped_group_ids = planner_shift_group_ids(db, user)
        if not scoped_group_ids:
            raise HTTPException(status_code=403, detail="No shift groups assigned for planning")
    return get_planner_dashboard(
        db,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=scoped_group_ids,
        year=year,
    )


@router.get("/team-member", response_model=TeamMemberDashboardRead)
def get_dashboard_team_member(
    shift_group_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not can_access_team_member_portal(db, user):
        raise HTTPException(status_code=403, detail="Team member portal access denied")
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=404, detail="No linked team member profile")
    groups = list_shift_groups_for_team_member(db, member.id)
    if not groups:
        raise HTTPException(status_code=400, detail="No shift group membership")
    allowed_ids = {group.id for group in groups}
    scoped_group_ids: set[int] | None = None
    if shift_group_id is not None:
        if shift_group_id not in allowed_ids:
            raise HTTPException(status_code=403, detail="Shift group not allowed for this team member")
    else:
        scoped_group_ids = allowed_ids
    try:
        return get_team_member_dashboard_for_user(
            db,
            user,
            shift_group_id=shift_group_id,
            shift_group_ids=scoped_group_ids,
            year=year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
