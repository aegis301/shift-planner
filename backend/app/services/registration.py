from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Organization, User
from app.services.audit import record_audit
from app.services.join_requests import create_pending_join_request
from app.services.organizations import (
    assert_organization_slug_available,
    create_organization_record,
    get_organization_by_slug,
    validate_organization_slug,
)
from app.services.users import get_user_in_organization

ROLE_ADMIN = "admin"
ROLE_APPLICANT = "applicant"


def register_create_organization(
    db: Session,
    *,
    organization_name: str,
    organization_slug: str,
    email: str,
    password: str,
    locale: str,
) -> tuple[User, Organization]:
    slug = validate_organization_slug(organization_slug)
    assert_organization_slug_available(db, slug)
    org = create_organization_record(db, name=organization_name, slug=slug)
    db.flush()
    existing = get_user_in_organization(db, email, org.id)
    if existing is not None:
        db.rollback()
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role=ROLE_ADMIN,
        locale=locale,
        organization_id=org.id,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=user.email,
        source="rest",
        action="register_create_organization",
        entity_type="organization",
        entity_id=org.id,
        details={"user_id": user.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not complete registration") from exc
    db.refresh(user)
    db.refresh(org)
    return user, org


def register_join_organization(
    db: Session,
    *,
    organization_slug: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    message: str | None,
    locale: str,
) -> tuple[User, Organization]:
    org = get_organization_by_slug(db, organization_slug)
    if org is None:
        raise ValueError("Organization not found")
    existing = get_user_in_organization(db, email, org.id)
    if existing is not None:
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role=ROLE_APPLICANT,
        locale=locale,
        organization_id=org.id,
    )
    db.add(user)
    db.flush()
    create_pending_join_request(
        db,
        organization_id=org.id,
        requester_user_id=user.id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        message=message.strip() if message else None,
    )
    record_audit(
        db,
        actor=user.email,
        source="rest",
        action="register_join_organization",
        entity_type="user",
        entity_id=user.id,
        details={"organization_id": org.id},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not complete registration") from exc
    db.refresh(user)
    return user, org
