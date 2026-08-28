from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    EmploymentPeriodRead,
    EmploymentPeriodsReplace,
    TimeAccountOpeningRead,
    TimeAccountOpeningUpsert,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
    TimesheetFillRequest,
    TimesheetRead,
    TimesheetSummaryRead,
    WorkerGroupCreate,
    WorkerGroupRead,
    WorkerGroupUpdate,
)
from app.services.authz import assert_hours_member_access, is_admin
from app.services.employment_periods import (
    employment_period_to_read,
    list_employment_periods,
    replace_employment_periods,
)
from app.services.team_members import list_team_members, list_team_members_for_planner
from app.services.time_entries import (
    create_time_entry,
    delete_time_entry,
    get_opening_balance,
    list_opening_balances,
    list_time_entries,
    opening_to_read,
    time_entry_to_read,
    update_time_entry,
    upsert_opening_balance,
)
from app.services.timesheets import (
    export_timesheet_csv,
    fill_from_roster,
    fill_regular_week,
    get_timesheet,
    list_timesheet_summaries,
    month_bounds,
)
from app.services.worker_groups import (
    create_worker_group,
    delete_worker_group,
    list_worker_groups,
    update_worker_group,
    worker_group_to_read,
)

worker_groups_router = APIRouter(prefix="/worker-groups", tags=["worker-groups"])
hours_router = APIRouter(prefix="/hours", tags=["hours"])


@worker_groups_router.get("", response_model=list[WorkerGroupRead])
def get_worker_groups(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkerGroupRead]:
    rows = list_worker_groups(db, organization_id=user.organization_id, active_only=active_only)
    return [worker_group_to_read(row) for row in rows]


@worker_groups_router.post("", response_model=WorkerGroupRead, status_code=status.HTTP_201_CREATED)
def post_worker_group(
    payload: WorkerGroupCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkerGroupRead:
    try:
        row = create_worker_group(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return worker_group_to_read(row)


@worker_groups_router.patch("/{worker_group_id}", response_model=WorkerGroupRead)
def patch_worker_group(
    worker_group_id: int,
    payload: WorkerGroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkerGroupRead:
    try:
        row = update_worker_group(
            db,
            worker_group_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Worker group not found")
    return worker_group_to_read(row)


@worker_groups_router.delete("/{worker_group_id}")
def delete_worker_group_endpoint(
    worker_group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> dict[str, bool]:
    try:
        deleted = delete_worker_group(
            db, worker_group_id, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Worker group not found")
    return {"deleted": True}


def _hours_members(db: Session, user: User):
    if is_admin(user):
        return list_team_members(db, organization_id=user.organization_id, active_only=True)
    return list_team_members_for_planner(db, user, active_only=True)


@hours_router.get("/summaries", response_model=list[TimesheetSummaryRead])
def get_hours_summaries(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> list[TimesheetSummaryRead]:
    start, end = month_bounds(year, month)
    members = _hours_members(db, user)
    return list_timesheet_summaries(
        db, organization_id=user.organization_id, members=members, from_date=start, to_date=end
    )


@hours_router.get("/openings", response_model=list[TimeAccountOpeningRead])
def get_openings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[TimeAccountOpeningRead]:
    return [opening_to_read(row) for row in list_opening_balances(db, organization_id=user.organization_id)]


@hours_router.get("/members/{team_member_id}/employment-periods", response_model=list[EmploymentPeriodRead])
def get_employment_periods(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EmploymentPeriodRead]:
    try:
        assert_hours_member_access(db, user, team_member_id, write=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    rows = list_employment_periods(db, team_member_id=team_member_id, organization_id=user.organization_id)
    return [employment_period_to_read(row) for row in rows]


@hours_router.put("/members/{team_member_id}/employment-periods", response_model=list[EmploymentPeriodRead])
def put_employment_periods(
    team_member_id: int,
    payload: EmploymentPeriodsReplace,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[EmploymentPeriodRead]:
    try:
        rows = replace_employment_periods(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            periods=payload.periods,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [employment_period_to_read(row) for row in rows]


@hours_router.get("/members/{team_member_id}/opening", response_model=TimeAccountOpeningRead | None)
def get_member_opening(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        assert_hours_member_access(db, user, team_member_id, write=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    row = get_opening_balance(db, team_member_id=team_member_id, organization_id=user.organization_id)
    if row is None:
        return None
    return opening_to_read(row)


@hours_router.put("/members/{team_member_id}/opening", response_model=TimeAccountOpeningRead)
def put_member_opening(
    team_member_id: int,
    payload: TimeAccountOpeningUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TimeAccountOpeningRead:
    try:
        row = upsert_opening_balance(
            db,
            payload,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return opening_to_read(row)


@hours_router.get("/members/{team_member_id}/timesheet", response_model=TimesheetRead)
def get_member_timesheet(
    team_member_id: int,
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimesheetRead:
    try:
        assert_hours_member_access(db, user, team_member_id, write=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if from_date is None or to_date is None:
        if year is None or month is None:
            today = date.today()
            year = year or today.year
            month = month or today.month
        from_date, to_date = month_bounds(year, month)
    try:
        return get_timesheet(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            from_date=from_date,
            to_date=to_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@hours_router.get("/members/{team_member_id}/timesheet.csv", response_class=PlainTextResponse)
def get_member_timesheet_csv(
    team_member_id: int,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        assert_hours_member_access(db, user, team_member_id, write=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    start, end = month_bounds(year, month)
    try:
        sheet = get_timesheet(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            from_date=start,
            to_date=end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlainTextResponse(
        export_timesheet_csv(sheet),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="timesheet-{team_member_id}-{year}-{month:02d}.csv"'},
    )


@hours_router.get("/members/{team_member_id}/entries", response_model=list[TimeEntryRead])
def get_member_entries(
    team_member_id: int,
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TimeEntryRead]:
    try:
        assert_hours_member_access(db, user, team_member_id, write=False)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    rows = list_time_entries(
        db,
        team_member_id=team_member_id,
        organization_id=user.organization_id,
        from_date=from_date,
        to_date=to_date,
    )
    return [time_entry_to_read(row) for row in rows]


@hours_router.post("/members/{team_member_id}/entries", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
def post_member_entry(
    team_member_id: int,
    payload: TimeEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> TimeEntryRead:
    try:
        assert_hours_member_access(db, user, team_member_id, write=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        row = create_time_entry(
            db,
            payload,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return time_entry_to_read(row)


@hours_router.patch("/entries/{entry_id}", response_model=TimeEntryRead)
def patch_entry(
    entry_id: int,
    payload: TimeEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> TimeEntryRead:
    from app.models import TimeEntry

    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Time entry not found")
    try:
        assert_hours_member_access(db, user, row.team_member_id, write=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        updated = update_time_entry(
            db, entry_id, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return time_entry_to_read(updated)


@hours_router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> dict[str, bool]:
    from app.models import TimeEntry

    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Time entry not found")
    try:
        assert_hours_member_access(db, user, row.team_member_id, write=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    deleted = delete_time_entry(
        db, entry_id, organization_id=user.organization_id, actor=user.email, source="rest"
    )
    return {"deleted": deleted}


@hours_router.post("/members/{team_member_id}/fill-from-roster")
def post_fill_from_roster(
    team_member_id: int,
    payload: TimesheetFillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> dict[str, int]:
    try:
        assert_hours_member_access(db, user, team_member_id, write=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        created = fill_from_roster(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"created": created}


@hours_router.post("/members/{team_member_id}/fill-regular-week")
def post_fill_regular_week(
    team_member_id: int,
    payload: TimesheetFillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> dict[str, int]:
    try:
        assert_hours_member_access(db, user, team_member_id, write=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        created = fill_regular_week(
            db,
            team_member_id=team_member_id,
            organization_id=user.organization_id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"created": created}
