from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    AiRosterDraftApply,
    AiRosterDraftApplyResult,
    AiTaskRunCreate,
    AiTaskRunRead,
    OrganizationAiSettingsRead,
    OrganizationAiSettingsUpdate,
)
from app.services.ai.runtime import apply_roster_draft, get_ai_run, run_ai_task, run_to_read
from app.services.ai_settings import (
    get_or_create_ai_settings,
    settings_to_public,
    update_ai_settings,
)

router = APIRouter(tags=["ai"])


def _http_from_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    code = status.HTTP_400_BAD_REQUEST
    if "not found" in message.lower():
        code = status.HTTP_404_NOT_FOUND
    if "published" in message.lower() or "budget" in message.lower() or "disabled" in message.lower():
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=message)


@router.get("/organization/ai-settings", response_model=OrganizationAiSettingsRead)
def get_organization_ai_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationAiSettingsRead:
    row = get_or_create_ai_settings(db, organization_id=user.organization_id)
    return OrganizationAiSettingsRead.model_validate(settings_to_public(row, include_last4=True))


@router.put("/organization/ai-settings", response_model=OrganizationAiSettingsRead)
def put_organization_ai_settings(
    payload: OrganizationAiSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationAiSettingsRead:
    try:
        row = update_ai_settings(
            db,
            organization_id=user.organization_id,
            provider=payload.provider,
            default_model=payload.default_model,
            enabled_task_ids=payload.enabled_task_ids,
            monthly_token_budget=payload.monthly_token_budget,
            is_enabled=payload.is_enabled,
            api_key=payload.api_key,
            clear_api_key=payload.clear_api_key,
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return OrganizationAiSettingsRead.model_validate(settings_to_public(row, include_last4=True))


@router.get("/ai/settings", response_model=OrganizationAiSettingsRead)
def get_planning_ai_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> OrganizationAiSettingsRead:
    row = get_or_create_ai_settings(db, organization_id=user.organization_id)
    return OrganizationAiSettingsRead.model_validate(settings_to_public(row, include_last4=False))


@router.post("/ai/tasks/{task_id}/runs", response_model=AiTaskRunRead)
def post_ai_task_run(
    task_id: str,
    payload: AiTaskRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> AiTaskRunRead:
    try:
        run = run_ai_task(
            db,
            user=user,
            task_id=task_id,
            planning_period_id=payload.planning_period_id,
            shift_group_id=payload.shift_group_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return AiTaskRunRead.model_validate(run_to_read(run))


@router.get("/ai/runs/{run_id}", response_model=AiTaskRunRead)
def get_ai_task_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> AiTaskRunRead:
    try:
        run = get_ai_run(db, user=user, run_id=run_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return AiTaskRunRead.model_validate(run_to_read(run))


@router.post("/ai/runs/{run_id}/apply", response_model=AiRosterDraftApplyResult)
def post_ai_run_apply(
    run_id: int,
    payload: AiRosterDraftApply,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> AiRosterDraftApplyResult:
    try:
        result = apply_roster_draft(
            db,
            user=user,
            run_id=run_id,
            roster_slot_ids=payload.roster_slot_ids,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return AiRosterDraftApplyResult.model_validate(result)
