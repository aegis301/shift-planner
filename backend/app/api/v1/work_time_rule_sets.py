from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    WorkTimeRuleSetAdoptRead,
    WorkTimeRuleSetAdoptRequest,
    WorkTimeRuleSetCreate,
    WorkTimeRuleSetPresetRead,
    WorkTimeRuleSetRead,
    WorkTimeRuleSetUpdate,
)
from app.services.work_time_presets import (
    adopt_work_time_rule_set_preset,
    list_work_time_rule_set_presets,
    work_time_rule_set_preset_to_read,
)
from app.services.work_time_rule_sets import (
    create_work_time_rule_set,
    delete_work_time_rule_set,
    get_work_time_rule_set,
    list_work_time_rule_sets,
    update_work_time_rule_set,
    work_time_rule_set_to_read,
)

router = APIRouter(prefix="/work-time-rule-sets", tags=["work-time-rule-sets"])


@router.get("", response_model=list[WorkTimeRuleSetRead])
def get_work_time_rule_sets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> list[WorkTimeRuleSetRead]:
    return [
        work_time_rule_set_to_read(row)
        for row in list_work_time_rule_sets(db, organization_id=user.organization_id)
    ]


@router.get("/presets", response_model=list[WorkTimeRuleSetPresetRead])
def get_work_time_rule_set_presets(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_planning_user),
) -> list[WorkTimeRuleSetPresetRead]:
    return [work_time_rule_set_preset_to_read(row) for row in list_work_time_rule_set_presets(db)]


@router.post("/presets/{code}/adopt", response_model=WorkTimeRuleSetAdoptRead, status_code=status.HTTP_201_CREATED)
def post_adopt_work_time_rule_set_preset(
    code: str,
    payload: WorkTimeRuleSetAdoptRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkTimeRuleSetAdoptRead:
    adopted = adopt_work_time_rule_set_preset(
        db,
        code,
        organization_id=user.organization_id,
        actor=user.email,
        source="rest",
        is_active=payload.is_active,
    )
    if adopted is None:
        raise HTTPException(status_code=404, detail="Work time rule set preset not found")
    return adopted


@router.get("/{rule_set_id}", response_model=WorkTimeRuleSetRead)
def get_work_time_rule_set_endpoint(
    rule_set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> WorkTimeRuleSetRead:
    row = get_work_time_rule_set(db, rule_set_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Work time rule set not found")
    return work_time_rule_set_to_read(row)


@router.post("", response_model=WorkTimeRuleSetRead, status_code=status.HTTP_201_CREATED)
def post_work_time_rule_set(
    payload: WorkTimeRuleSetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkTimeRuleSetRead:
    try:
        row = create_work_time_rule_set(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return work_time_rule_set_to_read(row)


@router.patch("/{rule_set_id}", response_model=WorkTimeRuleSetRead)
def patch_work_time_rule_set(
    rule_set_id: int,
    payload: WorkTimeRuleSetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkTimeRuleSetRead:
    try:
        row = update_work_time_rule_set(
            db,
            rule_set_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Work time rule set not found")
    return work_time_rule_set_to_read(row)


@router.delete("/{rule_set_id}")
def delete_work_time_rule_set_endpoint(
    rule_set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> dict[str, bool]:
    try:
        deleted = delete_work_time_rule_set(
            db,
            rule_set_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Work time rule set not found")
    return {"deleted": True}
