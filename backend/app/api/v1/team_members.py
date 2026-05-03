from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import TeamMemberCreate, TeamMemberRead, TeamMemberUpdate
from app.services.authz import is_admin
from app.services.team_members import (
    create_team_member,
    delete_team_member,
    list_team_members,
    list_team_members_for_planner,
    team_member_to_read,
    update_team_member,
)

router = APIRouter(prefix="/team-members", tags=["team-members"])


@router.get("", response_model=list[TeamMemberRead])
def get_team_members(
    active_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_planning_user)
):
    if is_admin(user):
        members = list_team_members(db, organization_id=user.organization_id, active_only=active_only)
    else:
        members = list_team_members_for_planner(db, user, active_only=active_only)
    return [team_member_to_read(m) for m in members]


@router.post("", response_model=TeamMemberRead)
def post_team_member(payload: TeamMemberCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)):
    try:
        member = create_team_member(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return team_member_to_read(member)


@router.patch("/{team_member_id}", response_model=TeamMemberRead)
def patch_team_member(
    team_member_id: int,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        member = update_team_member(
            db, team_member_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    return team_member_to_read(member)


@router.delete("/{team_member_id}")
def delete_team_member_endpoint(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    return {
        "deleted": delete_team_member(
            db, team_member_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }
