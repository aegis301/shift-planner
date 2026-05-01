import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization
from app.services.audit import record_audit

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_organization_slug(raw: str) -> str:
    return raw.strip().lower()


def validate_organization_slug(raw: str) -> str:
    slug = normalize_organization_slug(raw)
    if len(slug) < 3 or len(slug) > 64:
        raise ValueError("Organization code must be between 3 and 64 characters")
    if not _SLUG_RE.match(slug):
        raise ValueError("Organization code may only use lowercase letters, digits, and hyphens")
    return slug


def get_organization_by_slug(db: Session, slug: str) -> Organization | None:
    normalized = normalize_organization_slug(slug)
    if not normalized:
        return None
    return db.scalar(select(Organization).where(Organization.slug == normalized))


def assert_organization_slug_available(db: Session, slug: str) -> None:
    if get_organization_by_slug(db, slug) is not None:
        raise ValueError("This organization code is already taken")


def create_organization_record(
    db: Session,
    *,
    name: str,
    slug: str,
    plan_tier: str = "team",
) -> Organization:
    org = Organization(name=name.strip(), slug=slug, plan_tier=plan_tier)
    db.add(org)
    db.flush()
    return org


def update_organization_settings(
    db: Session,
    organization: Organization,
    *,
    name: str | None,
    organization_slug: str | None,
    actor: str,
    source: str,
) -> Organization:
    details: dict[str, Any] = {}
    if name is not None and name.strip() != organization.name:
        details["name"] = {"from": organization.name, "to": name.strip()}
        organization.name = name.strip()
    if organization_slug is not None:
        new_slug = validate_organization_slug(organization_slug)
        if new_slug != organization.slug:
            assert_organization_slug_available(db, new_slug)
            details["slug"] = {"from": organization.slug, "to": new_slug}
            organization.slug = new_slug
    if details:
        record_audit(
            db,
            actor=actor,
            source=source,
            action="update",
            entity_type="organization",
            entity_id=organization.id,
            details=details,
        )
        db.commit()
        db.refresh(organization)
    return organization
