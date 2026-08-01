from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_admin,
    get_current_planner,
    get_current_user_excluding_applicant,
)
from app.db.session import get_db
from app.models import User
from app.schemas import (
    PlanningMatrixRead,
    PlanningPeriodCreate,
    PlanningPeriodRead,
    PlanVersionListRead,
    PlanVersionRead,
    PlanVersionSaveRequest,
    PlanVersionTransitionRequest,
    RosterMatrixRead,
    RosterMatrixSyncRead,
    RosterSlotSyncSummary,
    ShiftGroupPlanningStatusRead,
    ValidationWarning,
)
from app.services.authz import assert_planning_shift_group_scope, is_admin, is_shift_planner_role
from app.services.exports import (
    export_matrix_csv,
    export_roster_matrix_csv,
    export_version_matrix_csv,
    export_version_roster_matrix_csv,
    export_version_roster_matrix_pdf,
    export_version_roster_matrix_xlsx,
)
from app.services.plan_versions import (
    VERSION_TRIGGER_MANUAL_SAVE,
    VERSION_TRIGGER_STATUS_PRELIMINARY,
    VERSION_TRIGGER_STATUS_PUBLISHED,
    PlanVersionNotFoundError,
    PlanVersionValidationError,
    get_plan_version,
    get_plan_version_matrix,
    get_plan_version_roster,
    list_plan_versions,
    manual_save_plan_version,
    suggest_next_version,
)
from app.services.planning import (
    create_planning_period,
    delete_planning_period,
    list_planning_periods,
    list_shift_group_statuses_for_period,
    publish_planning_period,
    set_planning_period_to_draft,
    set_planning_period_to_preliminary,
    unpublish_planning_period,
)
from app.services.roster_matrix import (
    RosterRegeneratePublishedError,
    RosterSyncPublishedError,
    get_roster_matrix,
    reset_roster_slots_for_period,
    sync_roster_slots_for_period,
)
from app.services.validation import validate_roster

router = APIRouter(tags=["planning"])


def _period_read(period, statuses) -> PlanningPeriodRead:
    return PlanningPeriodRead.model_validate(period).model_copy(
        update={
            "shift_group_statuses": [ShiftGroupPlanningStatusRead.model_validate(row) for row in statuses]
        }
    )


@router.get("/planning-periods", response_model=list[PlanningPeriodRead])
def get_planning_periods(
    db: Session = Depends(get_db), user: User = Depends(get_current_user_excluding_applicant)
):
    periods = list_planning_periods(db, organization_id=user.organization_id)
    return [
        _period_read(period, list_shift_group_statuses_for_period(db, planning_period_id=period.id, organization_id=user.organization_id))
        for period in periods
    ]


@router.post("/planning-periods", response_model=PlanningPeriodRead)
def post_planning_period(
    payload: PlanningPeriodCreate, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    period = create_planning_period(
        db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    statuses = list_shift_group_statuses_for_period(db, planning_period_id=period.id, organization_id=user.organization_id)
    return _period_read(period, statuses)


@router.post("/planning-periods/{planning_period_id}/publish", response_model=ShiftGroupPlanningStatusRead)
def post_publish_planning_period(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    payload: PlanVersionTransitionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    options = payload or PlanVersionTransitionRequest()
    try:
        row = publish_planning_period(
            db,
            planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            created_by_user_id=user.id,
            major_version=options.major_version,
            minor_version=options.minor_version,
            note=options.note,
        )
    except PlanVersionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return ShiftGroupPlanningStatusRead.model_validate(row)


@router.post("/planning-periods/{planning_period_id}/preliminary", response_model=ShiftGroupPlanningStatusRead)
def post_set_planning_period_preliminary(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    payload: PlanVersionTransitionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    options = payload or PlanVersionTransitionRequest()
    try:
        row = set_planning_period_to_preliminary(
            db,
            planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            created_by_user_id=user.id,
            major_version=options.major_version,
            minor_version=options.minor_version,
            note=options.note,
            is_major_update=options.is_major_update,
        )
    except PlanVersionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return ShiftGroupPlanningStatusRead.model_validate(row)


@router.post("/planning-periods/{planning_period_id}/draft", response_model=ShiftGroupPlanningStatusRead)
def post_set_planning_period_draft(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    row = set_planning_period_to_draft(
        db,
        planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=user.organization_id,
        actor=user.email,
        source="rest",
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return ShiftGroupPlanningStatusRead.model_validate(row)


@router.post("/planning-periods/{planning_period_id}/unpublish", response_model=ShiftGroupPlanningStatusRead)
def post_unpublish_planning_period(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    payload: PlanVersionTransitionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    options = payload or PlanVersionTransitionRequest()
    try:
        row = unpublish_planning_period(
            db,
            planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            created_by_user_id=user.id,
            major_version=options.major_version,
            minor_version=options.minor_version,
            note=options.note,
            is_major_update=options.is_major_update,
        )
    except PlanVersionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Planning period not found")
    return ShiftGroupPlanningStatusRead.model_validate(row)


@router.delete("/planning-periods/{planning_period_id}")
def delete_planning_period_endpoint(
    planning_period_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_admin)
):
    return {
        "deleted": delete_planning_period(
            db, planning_period_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    }


@router.post("/planning-periods/{planning_period_id}/regenerate-roster", response_model=RosterMatrixRead)
def regenerate_planning_period_roster(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        reset_roster_slots_for_period(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            shift_group_id=shift_group_id,
        )
        return get_roster_matrix(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except RosterRegeneratePublishedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "ROSTER_REGENERATE_PUBLISHED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/planning-periods/{planning_period_id}/sync-roster", response_model=RosterMatrixSyncRead)
def sync_planning_period_roster(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        sync_result = sync_roster_slots_for_period(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            shift_group_id=shift_group_id,
        )
        matrix = get_roster_matrix(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
        return RosterMatrixSyncRead(
            matrix=matrix,
            sync=RosterSlotSyncSummary(
                added_count=sync_result.added_count,
                removed_count=sync_result.removed_count,
                updated_count=sync_result.updated_count,
                assignments_cleared_count=sync_result.assignments_cleared_count,
            ),
        )
    except RosterSyncPublishedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "ROSTER_SYNC_PUBLISHED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/validation/{planning_period_id}", response_model=list[ValidationWarning])
def get_validation(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        return validate_roster(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/exports/roster-matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_roster_matrix_csv(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        body = export_roster_matrix_csv(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-matrix-{planning_period_id}.csv"'},
    )


@router.get("/exports/matrix/{planning_period_id}.csv", response_class=PlainTextResponse)
def get_matrix_csv(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    if is_shift_planner_role(user) and not is_admin(user) and shift_group_id is None:
        raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        body = export_matrix_csv(
            db, planning_period_id, organization_id=user.organization_id, shift_group_id=shift_group_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="matrix-{planning_period_id}.csv"'},
    )


@router.get("/planning-periods/{planning_period_id}/versions", response_model=PlanVersionListRead)
def get_plan_versions(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        return list_plan_versions(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
        )
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/planning-periods/{planning_period_id}/versions/suggest")
def get_suggested_plan_version(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    trigger: str = Query(...),
    is_major_update: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if trigger not in {
        VERSION_TRIGGER_MANUAL_SAVE,
        VERSION_TRIGGER_STATUS_PRELIMINARY,
        VERSION_TRIGGER_STATUS_PUBLISHED,
    }:
        raise HTTPException(status_code=400, detail="Invalid version trigger")
    try:
        suggested = suggest_next_version(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
            trigger=trigger,
            is_major_update=is_major_update,
        )
    except PlanVersionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"major_version": suggested.major, "minor_version": suggested.minor, "label": suggested.label}


@router.get("/planning-periods/{planning_period_id}/versions/{version_id}", response_model=PlanVersionRead)
def get_plan_version_detail(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanVersionRead.model_validate(version)


@router.post("/planning-periods/{planning_period_id}/versions", response_model=PlanVersionRead)
def post_save_plan_version(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    payload: PlanVersionSaveRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    options = payload or PlanVersionSaveRequest()
    try:
        version = manual_save_plan_version(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            organization_id=user.organization_id,
            created_by_user_id=user.id,
            actor=user.email,
            source="rest",
            major_version=options.major_version,
            minor_version=options.minor_version,
            note=options.note,
        )
    except PlanVersionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlanVersionRead.model_validate(version)


@router.get(
    "/planning-periods/{planning_period_id}/versions/{version_id}/matrix",
    response_model=PlanningMatrixRead,
)
def get_plan_version_matrix_endpoint(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        return get_plan_version_matrix(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/planning-periods/{planning_period_id}/versions/{version_id}/roster-matrix",
    response_model=RosterMatrixRead,
)
def get_plan_version_roster_endpoint(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        return get_plan_version_roster(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/planning-periods/{planning_period_id}/versions/{version_id}/export/matrix.csv",
    response_class=PlainTextResponse,
)
def get_plan_version_matrix_csv(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        body = export_version_matrix_csv(
            db,
            planning_period_id,
            version_id=version_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="matrix-{planning_period_id}-v{version.major_version}.{version.minor_version}.csv"'
            )
        },
    )


@router.get(
    "/planning-periods/{planning_period_id}/versions/{version_id}/export/roster-matrix.csv",
    response_class=PlainTextResponse,
)
def get_plan_version_roster_csv(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        body = export_version_roster_matrix_csv(
            db,
            planning_period_id,
            version_id=version_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="roster-matrix-{planning_period_id}-v{version.major_version}.{version.minor_version}.csv"'
            )
        },
    )


@router.get("/planning-periods/{planning_period_id}/versions/{version_id}/export/roster-matrix.xlsx")
def get_plan_version_roster_xlsx(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        body = export_version_roster_matrix_xlsx(
            db,
            planning_period_id,
            version_id=version_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="roster-matrix-{planning_period_id}-v{version.major_version}.{version.minor_version}.xlsx"'
            )
        },
    )


@router.get("/planning-periods/{planning_period_id}/versions/{version_id}/export/roster-matrix.pdf")
def get_plan_version_roster_pdf(
    planning_period_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
):
    try:
        version = get_plan_version(
            db,
            version_id=version_id,
            planning_period_id=planning_period_id,
            organization_id=user.organization_id,
        )
        assert_planning_shift_group_scope(db, user, version.shift_group_id)
        body = export_version_roster_matrix_pdf(
            db,
            planning_period_id,
            version_id=version_id,
            organization_id=user.organization_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="roster-matrix-{planning_period_id}-v{version.major_version}.{version.minor_version}.pdf"'
            )
        },
    )
