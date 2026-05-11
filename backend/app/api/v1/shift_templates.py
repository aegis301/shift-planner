from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    GeneratedRosterSlotPreview,
    ShiftTemplateCreate,
    ShiftTemplatePreviewRequest,
    ShiftTemplateRead,
    ShiftTemplateUpdate,
    ShiftVariantCreate,
    ShiftVariantRead,
    ShiftVariantUpdate,
)
from app.services.authz import is_admin
from app.services.shift_templates import (
    ShiftConstraintInvalidError,
    ShiftTemplateCodeConflictError,
    create_shift_template,
    create_shift_variant,
    delete_shift_template,
    delete_shift_variant,
    list_shift_templates,
    list_shift_templates_for_planning_user,
    preview_slots_for_month,
    update_shift_template,
    update_shift_variant,
)

router = APIRouter(prefix="/shift-templates", tags=["shift-templates"])


@router.get("", response_model=list[ShiftTemplateRead])
def get_shift_templates(
    active_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_planning_user)
):
    if is_admin(user):
        return list_shift_templates(db, organization_id=user.organization_id, active_only=active_only)
    return list_shift_templates_for_planning_user(db, user)


@router.post("", response_model=ShiftTemplateRead)
def post_shift_template(
    payload: ShiftTemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        return create_shift_template(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ShiftConstraintInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except ShiftTemplateCodeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SHIFT_TEMPLATE_CODE_TAKEN", "field": "code", "value": exc.code},
        ) from exc


@router.patch("/{template_id}", response_model=ShiftTemplateRead)
def patch_shift_template(
    template_id: int,
    payload: ShiftTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        template = update_shift_template(
            db, template_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ShiftConstraintInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except ShiftTemplateCodeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SHIFT_TEMPLATE_CODE_TAKEN", "field": "code", "value": exc.code},
        ) from exc
    if template is None:
        raise HTTPException(status_code=404, detail="Shift template not found")
    return template


@router.delete("/{template_id}")
def delete_shift_template_endpoint(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    return {
        "deleted": delete_shift_template(
            db, template_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }


@router.post("/{template_id}/variants", response_model=ShiftVariantRead)
def post_shift_variant(
    template_id: int,
    payload: ShiftVariantCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        variant = create_shift_variant(
            db, template_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ShiftConstraintInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    if variant is None:
        raise HTTPException(status_code=404, detail="Shift template not found")
    return variant


@router.patch("/variants/{variant_id}", response_model=ShiftVariantRead)
def patch_shift_variant(
    variant_id: int,
    payload: ShiftVariantUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    try:
        variant = update_shift_variant(
            db, variant_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ShiftConstraintInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    if variant is None:
        raise HTTPException(status_code=404, detail="Shift variant not found")
    return variant


@router.delete("/variants/{variant_id}")
def delete_shift_variant_endpoint(
    variant_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
):
    return {
        "deleted": delete_shift_variant(
            db, variant_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }


@router.post("/preview", response_model=list[GeneratedRosterSlotPreview])
def post_shift_template_preview(
    payload: ShiftTemplatePreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
):
    return preview_slots_for_month(
        db, year=payload.year, month=payload.month, organization_id=user.organization_id
    )
