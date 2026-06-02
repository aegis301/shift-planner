from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user, get_current_user
from app.db.session import get_db
from app.models import Organization, User
from app.schemas import (
    TeamMemberCreate,
    TeamMemberPlanningPatternRead,
    TeamMemberPlanningPatternsReplace,
    TeamMemberPropertyValueRead,
    TeamMemberPropertyValuesReplace,
    TeamMemberRead,
    TeamMemberUpdate,
)
from app.services.authz import (
    assert_team_member_patterns_read,
    assert_team_member_patterns_write,
    assert_team_member_property_values_read,
    assert_team_member_property_values_write,
    is_admin,
)
from app.services.team_member_property_values import (
    list_property_values_for_member,
    replace_team_member_property_values,
)
from app.services.member_planning_patterns import (
    list_team_member_planning_patterns,
    pattern_to_read,
    read_organization_member_pattern_policy,
    replace_team_member_planning_patterns,
)
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


@router.get("/{team_member_id}/planning-patterns", response_model=list[TeamMemberPlanningPatternRead])
def get_team_member_planning_patterns(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        assert_team_member_patterns_read(db, user, team_member_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    rows = list_team_member_planning_patterns(db, team_member_id=team_member_id, organization_id=user.organization_id)
    return [pattern_to_read(row) for row in rows]


@router.put("/{team_member_id}/planning-patterns", response_model=list[TeamMemberPlanningPatternRead])
def put_team_member_planning_patterns(
    team_member_id: int,
    payload: TeamMemberPlanningPatternsReplace,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        assert_team_member_patterns_write(db, user, team_member_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    policy = read_organization_member_pattern_policy(org)
    try:
        rows = replace_team_member_planning_patterns(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            payload=payload,
            policy=policy,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [pattern_to_read(row) for row in rows]


@router.get("/{team_member_id}/property-values", response_model=list[TeamMemberPropertyValueRead])
def get_team_member_property_values(
    team_member_id: int,
    active_definitions_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        assert_team_member_property_values_read(db, user, team_member_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return list_property_values_for_member(
        db,
        team_member_id=team_member_id,
        organization_id=user.organization_id,
        active_definitions_only=active_definitions_only or not is_admin(user),
    )


@router.put("/{team_member_id}/property-values", response_model=list[TeamMemberPropertyValueRead])
def put_team_member_property_values(
    team_member_id: int,
    payload: TeamMemberPropertyValuesReplace,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        allow_ids = assert_team_member_property_values_write(db, user, team_member_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        return replace_team_member_property_values(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            payload=payload,
            actor=user.email,
            source="rest",
            allow_definition_ids=allow_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
