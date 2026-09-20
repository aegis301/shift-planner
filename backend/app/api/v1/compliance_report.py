from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import ComplianceReportRead
from app.services.authz import assert_planning_shift_group_scope
from app.services.compliance_report import build_compliance_report
from app.services.exports import export_compliance_report_pdf, export_compliance_report_xlsx

router = APIRouter(tags=["compliance-report"])


def _load_report(
    db: Session, user: User, planning_period_id: int, shift_group_id: int | None
) -> ComplianceReportRead:
    assert_planning_shift_group_scope(db, user, shift_group_id)
    return build_compliance_report(
        db,
        planning_period_id,
        organization_id=user.organization_id,
        shift_group_id=shift_group_id,
    )


@router.get("/compliance-report/{planning_period_id}", response_model=ComplianceReportRead)
def get_compliance_report(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> ComplianceReportRead:
    try:
        return _load_report(db, user, planning_period_id, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/exports/compliance-report/{planning_period_id}.xlsx")
def get_compliance_report_xlsx(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
        body = export_compliance_report_xlsx(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="compliance-report-{planning_period_id}.xlsx"'
        },
    )


@router.get("/exports/compliance-report/{planning_period_id}.pdf")
def get_compliance_report_pdf(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
):
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
        body = export_compliance_report_pdf(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="compliance-report-{planning_period_id}.pdf"'
        },
    )
