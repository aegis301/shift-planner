from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Account, Organization, User
from app.services.audit import record_audit
from app.services.join_requests import create_pending_join_request
from app.services.organizations import (
    assert_organization_slug_available,
    create_organization_record,
    get_organization_by_slug,
    validate_organization_slug,
)
from app.services.users import get_account_by_email

ROLE_ADMIN = "admin"
ROLE_APPLICANT = "applicant"


def register_account_only(db: Session, *, email: str, password: str, locale: str) -> Account:
    em = email.lower()
    if get_account_by_email(db, em) is not None:
        raise ValueError("Email already registered")
    acc = Account(email=em, hashed_password=hash_password(password), locale=locale)
    db.add(acc)
    db.flush()
    record_audit(
        db,
        actor=em,
        source="rest",
        action="register_account_only",
        entity_type="account",
        entity_id=str(acc.id),
        details={},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not complete registration") from exc
    db.refresh(acc)
    return acc


def onboarding_create_organization(
    db: Session,
    *,
    account: Account,
    organization_name: str,
    organization_slug: str,
) -> tuple[User, Organization]:
    slug = validate_organization_slug(organization_slug)
    assert_organization_slug_available(db, slug)
    org = create_organization_record(db, name=organization_name, slug=slug)
    db.flush()
    existing_membership = db.scalar(
        select(User).where(User.account_id == account.id, User.organization_id == org.id)
    )
    if existing_membership is not None:
        db.rollback()
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        account_id=account.id,
        organization_id=org.id,
        role=ROLE_ADMIN,
        locale=account.locale,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=user.email,
        source="rest",
        action="onboarding_create_organization",
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


def create_additional_organization_membership(
    db: Session,
    *,
    current_membership: User,
    organization_name: str,
    organization_slug: str,
) -> tuple[User, Organization]:
    slug = validate_organization_slug(organization_slug)
    assert_organization_slug_available(db, slug)
    org = create_organization_record(db, name=organization_name, slug=slug)
    db.flush()
    existing_membership = db.scalar(
        select(User).where(User.account_id == current_membership.account_id, User.organization_id == org.id)
    )
    if existing_membership is not None:
        db.rollback()
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        account_id=current_membership.account_id,
        organization_id=org.id,
        role=ROLE_ADMIN,
        locale=current_membership.locale,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=current_membership.email,
        source="rest",
        action="create_additional_organization_membership",
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


def onboarding_join_organization(
    db: Session,
    *,
    account: Account,
    organization_slug: str,
    first_name: str,
    last_name: str,
    message: str | None,
) -> tuple[User, Organization]:
    org = get_organization_by_slug(db, organization_slug.strip().lower())
    if org is None:
        raise ValueError("Organization not found")
    existing = db.scalar(select(User).where(User.account_id == account.id, User.organization_id == org.id))
    if existing is not None:
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        account_id=account.id,
        organization_id=org.id,
        role=ROLE_APPLICANT,
        locale=account.locale,
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
        action="onboarding_join_organization",
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
    em = email.lower()
    acc = get_account_by_email(db, em)
    if acc is None:
        acc = Account(email=em, hashed_password=hash_password(password), locale=locale)
        db.add(acc)
        db.flush()
    else:
        if not verify_password(password, acc.hashed_password):
            db.rollback()
            raise ValueError("Invalid password for this email")
    existing_membership = db.scalar(
        select(User).where(User.account_id == acc.id, User.organization_id == org.id)
    )
    if existing_membership is not None:
        db.rollback()
        raise ValueError("An account with this email already exists for this organization")
    user = User(account_id=acc.id, organization_id=org.id, role=ROLE_ADMIN, locale=locale)
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
    em = email.lower()
    acc = get_account_by_email(db, em)
    if acc is None:
        acc = Account(email=em, hashed_password=hash_password(password), locale=locale)
        db.add(acc)
        db.flush()
    else:
        if not verify_password(password, acc.hashed_password):
            raise ValueError("Invalid password for this email")
    existing = db.scalar(select(User).where(User.account_id == acc.id, User.organization_id == org.id))
    if existing is not None:
        raise ValueError("An account with this email already exists for this organization")
    user = User(account_id=acc.id, organization_id=org.id, role=ROLE_APPLICANT, locale=locale)
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


def request_join_additional_organization(
    db: Session,
    *,
    current_membership: User,
    organization_slug: str,
    password: str,
    first_name: str,
    last_name: str,
    message: str | None,
) -> User:
    slug = organization_slug.strip().lower()
    org = get_organization_by_slug(db, slug)
    if org is None:
        raise ValueError("Organization not found")
    if org.id == current_membership.organization_id:
        raise ValueError("Already a member of this organization")
    acc = current_membership.account
    if not verify_password(password, acc.hashed_password):
        raise ValueError("Invalid password for this email")
    existing = db.scalar(select(User).where(User.account_id == acc.id, User.organization_id == org.id))
    if existing is not None:
        raise ValueError("An account with this email already exists for this organization")
    user = User(
        account_id=acc.id,
        organization_id=org.id,
        role=ROLE_APPLICANT,
        locale=current_membership.locale,
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
        actor=current_membership.email,
        source="rest",
        action="request_join_additional_organization",
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
    return user
