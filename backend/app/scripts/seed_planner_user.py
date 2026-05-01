import os

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Organization, ShiftGroup, User, UserShiftGroup
from app.services.authz import ROLE_PLANNER


def main() -> None:
    email = os.environ.get("PLANNER_SEED_EMAIL", "christian.porschen@ukmuenster.de").lower()
    password = os.environ.get("PLANNER_SEED_PASSWORD", "change-me-planner")
    with SessionLocal() as db:
        org = db.get(Organization, settings.default_organization_id)
        if org is None:
            org = Organization(id=settings.default_organization_id, name="Default", plan_tier="team")
            db.add(org)
            db.flush()
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            print(f"User already exists: {existing.email} (role={existing.role})")
            return
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=ROLE_PLANNER,
            locale="de",
            organization_id=org.id,
        )
        db.add(user)
        db.flush()
        group_ids = list(db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == org.id)))
        for gid in group_ids:
            db.add(UserShiftGroup(user_id=user.id, shift_group_id=gid))
        db.commit()
        print(f"Planner user ready: {user.email} (linked to {len(group_ids)} shift group(s))")


if __name__ == "__main__":
    main()
