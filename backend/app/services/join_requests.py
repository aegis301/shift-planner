from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Doctor, OrganizationJoinRequest, User
from app.schemas import ApproveJoinCreateDoctorInput, DoctorCreate, DoctorUpdate, JoinRequestRead
from app.services.audit import record_audit
from app.services.doctors import create_doctor, update_doctor
from app.services.users import get_user

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"

RESOLUTION_CREATED_DOCTOR = "created_doctor"
RESOLUTION_LINKED_DOCTOR = "linked_existing_doctor"


def join_request_to_read(row: OrganizationJoinRequest) -> JoinRequestRead:
    req = row.requester
    email = req.email if req else ""
    return JoinRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        requester_user_id=row.requester_user_id,
        requester_email=email,
        first_name=row.first_name,
        last_name=row.last_name,
        message=row.message,
        status=row.status,
        resolution=row.resolution,
        resolved_doctor_id=row.resolved_doctor_id,
        created_at=row.created_at,
    )


def create_pending_join_request(
    db: Session,
    *,
    organization_id: int,
    requester_user_id: int,
    first_name: str,
    last_name: str,
    message: str | None,
) -> OrganizationJoinRequest:
    existing = db.scalar(
        select(OrganizationJoinRequest).where(
            OrganizationJoinRequest.organization_id == organization_id,
            OrganizationJoinRequest.requester_user_id == requester_user_id,
            OrganizationJoinRequest.status == STATUS_PENDING,
        )
    )
    if existing is not None:
        raise ValueError("You already have a pending request for this organization")
    row = OrganizationJoinRequest(
        organization_id=organization_id,
        requester_user_id=requester_user_id,
        first_name=first_name,
        last_name=last_name,
        message=message,
        status=STATUS_PENDING,
    )
    db.add(row)
    db.flush()
    return row


def list_join_requests_for_org(
    db: Session, *, organization_id: int, status: str | None = None
) -> list[OrganizationJoinRequest]:
    stmt = (
        select(OrganizationJoinRequest)
        .where(OrganizationJoinRequest.organization_id == organization_id)
        .options(joinedload(OrganizationJoinRequest.requester))
        .order_by(OrganizationJoinRequest.created_at.desc())
    )
    if status:
        stmt = stmt.where(OrganizationJoinRequest.status == status)
    return list(db.scalars(stmt).unique().all())


def get_pending_join_request_for_user(db: Session, *, user_id: int) -> OrganizationJoinRequest | None:
    return db.scalars(
        select(OrganizationJoinRequest)
        .where(
            OrganizationJoinRequest.requester_user_id == user_id,
            OrganizationJoinRequest.status == STATUS_PENDING,
        )
        .order_by(OrganizationJoinRequest.created_at.desc())
        .options(joinedload(OrganizationJoinRequest.requester))
        .limit(1)
    ).first()


def get_join_request_in_org(
    db: Session, *, request_id: int, organization_id: int
) -> OrganizationJoinRequest | None:
    row = db.get(OrganizationJoinRequest, request_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def cancel_join_request_by_requester(db: Session, *, request_id: int, user_id: int) -> bool:
    row = db.get(OrganizationJoinRequest, request_id)
    if row is None or row.requester_user_id != user_id:
        return False
    if row.status != STATUS_PENDING:
        return False
    row.status = STATUS_CANCELLED
    row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=str(user_id),
        source="rest",
        action="cancel_join_request",
        entity_type="organization_join_request",
        entity_id=row.id,
    )
    db.commit()
    return True


def reject_join_request(
    db: Session,
    *,
    row: OrganizationJoinRequest,
    admin_user: User,
    reason: str | None,
) -> OrganizationJoinRequest:
    if row.status != STATUS_PENDING:
        raise ValueError("Request is not pending")
    row.status = STATUS_REJECTED
    row.rejection_reason = reason.strip() if reason else None
    row.resolved_by_user_id = admin_user.id
    row.resolved_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=admin_user.email,
        source="rest",
        action="reject_join_request",
        entity_type="organization_join_request",
        entity_id=row.id,
        details={"reason": reason},
    )
    db.commit()
    db.refresh(row)
    return row


def approve_join_request_create_doctor(
    db: Session,
    *,
    row: OrganizationJoinRequest,
    admin_user: User,
    payload: ApproveJoinCreateDoctorInput,
) -> OrganizationJoinRequest:
    if row.status != STATUS_PENDING:
        raise ValueError("Request is not pending")
    requester = get_user(db, row.requester_user_id)
    if requester is None:
        raise ValueError("Requester not found")
    doctor_payload = DoctorCreate(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        employment_percentage=payload.employment_percentage,
        notes=payload.notes,
        shift_group_ids=payload.shift_group_ids,
        user_id=requester.id,
    )
    doctor = create_doctor(
        db,
        doctor_payload,
        organization_id=row.organization_id,
        actor=admin_user.email,
        source="rest",
    )
    requester = get_user(db, row.requester_user_id)
    if requester is not None:
        requester.role = "doctor"
    row = db.get(OrganizationJoinRequest, row.id)
    if row is not None:
        row.status = STATUS_APPROVED
        row.resolution = RESOLUTION_CREATED_DOCTOR
        row.resolved_doctor_id = doctor.id
        row.resolved_by_user_id = admin_user.id
        row.resolved_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=admin_user.email,
        source="rest",
        action="approve_join_request_create_doctor",
        entity_type="organization_join_request",
        entity_id=row.id if row else None,
        details={"doctor_id": doctor.id},
    )
    db.commit()
    if row:
        db.refresh(row)
    return row


def approve_join_request_link_doctor(
    db: Session,
    *,
    row: OrganizationJoinRequest,
    admin_user: User,
    doctor_id: int,
) -> OrganizationJoinRequest:
    if row.status != STATUS_PENDING:
        raise ValueError("Request is not pending")
    requester = get_user(db, row.requester_user_id)
    if requester is None:
        raise ValueError("Requester not found")
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.organization_id != row.organization_id or doctor.user_id is not None:
        raise ValueError("Doctor cannot be linked")
    updated = update_doctor(
        db,
        doctor_id,
        DoctorUpdate(user_id=requester.id),
        organization_id=row.organization_id,
        actor=admin_user.email,
        source="rest",
    )
    if updated is None:
        raise ValueError("Doctor update failed")
    requester = get_user(db, row.requester_user_id)
    if requester is not None:
        requester.role = "doctor"
    row = db.get(OrganizationJoinRequest, row.id)
    if row is not None:
        row.status = STATUS_APPROVED
        row.resolution = RESOLUTION_LINKED_DOCTOR
        row.resolved_doctor_id = doctor_id
        row.resolved_by_user_id = admin_user.id
        row.resolved_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=admin_user.email,
        source="rest",
        action="approve_join_request_link_doctor",
        entity_type="organization_join_request",
        entity_id=row.id if row else None,
        details={"doctor_id": doctor_id},
    )
    db.commit()
    if row:
        db.refresh(row)
    return row
