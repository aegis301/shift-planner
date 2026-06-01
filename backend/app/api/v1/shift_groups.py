from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import ShiftGroup, User
from app.schemas import (
    ShiftGroupCreate,
    ShiftGroupRead,
    ShiftGroupTeamMemberIdsPut,
    ShiftGroupTemplateIdsPut,
    ShiftGroupUpdate,
)
from app.services.authz import is_admin
from app.services.shift_groups import (
    create_shift_group,
    delete_shift_group,
    list_shift_groups,
    list_shift_groups_for_planner,
    replace_group_shift_templates,
    replace_group_team_members,
    update_shift_group,
)

router = APIRouter(prefix="/shift-groups", tags=["shift-groups"])


def _shift_group_read(group: ShiftGroup) -> ShiftGroupRead:
    return ShiftGroupRead(
        id=group.id,
        code=group.code,
        name=group.name,
        display_order=group.display_order,
        is_active=group.is_active,
        created_at=group.created_at,
        team_member_ids=sorted({link.team_member_id for link in group.team_member_links}),
        shift_template_ids=sorted({link.shift_template_id for link in group.template_links}),
    )


@router.get("", response_model=list[ShiftGroupRead])
def get_shift_groups(
    active_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_planning_user)
):
    if is_admin(user):
        groups = list_shift_groups(db, organization_id=user.organization_id, active_only=active_only)
    else:
        groups = list_shift_groups_for_planner(db, user=user, active_only=active_only)
    return [_shift_group_read(g) for g in groups]


@router.post("", response_model=ShiftGroupRead)
def post_shift_group(
    payload: ShiftGroupCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    group = create_shift_group(db, payload, organization_id=user.organization_id, actor=user.email, source="rest")
    db.refresh(group, attribute_names=["team_member_links", "template_links"])
    return _shift_group_read(group)


@router.patch("/{shift_group_id}", response_model=ShiftGroupRead)
def patch_shift_group(
    shift_group_id: int,
    payload: ShiftGroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    group = update_shift_group(
        db, shift_group_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Shift group not found")
    db.refresh(group, attribute_names=["team_member_links", "template_links"])
    return _shift_group_read(group)


@router.delete("/{shift_group_id}")
def delete_shift_group_endpoint(
    shift_group_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    return {
        "deleted": delete_shift_group(
            db, shift_group_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }


@router.put("/{shift_group_id}/team-members", response_model=ShiftGroupRead)
def put_shift_group_team_members(
    shift_group_id: int,
    payload: ShiftGroupTeamMemberIdsPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        replace_group_team_members(
            db,
            shift_group_id,
            payload.team_member_ids,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    group = db.get(ShiftGroup, shift_group_id)
    if group is None or group.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Shift group not found")
    db.refresh(group, attribute_names=["team_member_links", "template_links"])
    return _shift_group_read(group)


@router.put("/{shift_group_id}/shift-templates", response_model=ShiftGroupRead)
def put_shift_group_templates(
    shift_group_id: int,
    payload: ShiftGroupTemplateIdsPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        replace_group_shift_templates(
            db,
            shift_group_id,
            payload.shift_template_ids,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    group = db.get(ShiftGroup, shift_group_id)
    if group is None or group.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Shift group not found")
    db.refresh(group, attribute_names=["team_member_links", "template_links"])
    return _shift_group_read(group)
