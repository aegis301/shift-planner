from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    PlanningDayStatusDefinitionCreate,
    PlanningDayStatusDefinitionRead,
    PlanningDayStatusDefinitionUpdate,
)
from app.services.planning_day_status_definitions import (
    create_planning_day_status_definition,
    delete_planning_day_status_definition,
    ensure_default_planning_day_statuses,
    get_planning_day_status_definition_or_none,
    list_planning_day_status_definitions,
    update_planning_day_status_definition,
)

router = APIRouter(prefix="/planning-day-status-definitions", tags=["planning-day-status-definitions"])


@router.get("", response_model=list[PlanningDayStatusDefinitionRead])
def get_planning_day_status_definitions(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlanningDayStatusDefinitionRead]:
    ensure_default_planning_day_statuses(db, organization_id=user.organization_id)
    rows = list_planning_day_status_definitions(
        db, organization_id=user.organization_id, active_only=active_only
    )
    return [PlanningDayStatusDefinitionRead.model_validate(row) for row in rows]


@router.post("", response_model=PlanningDayStatusDefinitionRead, status_code=status.HTTP_201_CREATED)
def post_planning_day_status_definition(
    payload: PlanningDayStatusDefinitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> PlanningDayStatusDefinitionRead:
    try:
        row = create_planning_day_status_definition(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlanningDayStatusDefinitionRead.model_validate(row)


@router.patch("/{definition_id}", response_model=PlanningDayStatusDefinitionRead)
def patch_planning_day_status_definition(
    definition_id: int,
    payload: PlanningDayStatusDefinitionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> PlanningDayStatusDefinitionRead:
    try:
        row = update_planning_day_status_definition(
            db,
            definition_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Day status definition not found")
    return PlanningDayStatusDefinitionRead.model_validate(row)


@router.delete("/{definition_id}")
def delete_planning_day_status_definition_endpoint(
    definition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> dict[str, bool]:
    try:
        deleted = delete_planning_day_status_definition(
            db,
            definition_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Day status definition not found")
    return {"deleted": True}
