from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Account, Organization, ShiftGroup, User, UserShiftGroup
from app.services.authz import ROLE_PLANNER
from app.services.users import get_account_by_email, get_user_in_organization


def main() -> None:
    email = (settings.planner_seed_email or "planner@example.com").strip().lower()
    password = settings.planner_seed_password
    with SessionLocal() as db:
        org = db.get(Organization, settings.default_organization_id)
        if org is None:
            org = Organization(
                id=settings.default_organization_id, name="Default", slug="default", plan_tier="team"
            )
            db.add(org)
            db.flush()
        elif not org.slug:
            org.slug = "default"
            db.flush()
        existing = get_user_in_organization(db, email, org.id)
        group_ids = list(db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == org.id)))
        if existing:
            if existing.role != ROLE_PLANNER:
                print(f"User already exists: {existing.email} (role={existing.role}); use a different planner_seed_email")
                return
            existing.account.hashed_password = hash_password(password)
            existing.organization_id = org.id
            db.execute(delete(UserShiftGroup).where(UserShiftGroup.user_id == existing.id))
            for gid in group_ids:
                db.add(UserShiftGroup(user_id=existing.id, shift_group_id=gid))
            db.commit()
            print(f"Planner user updated: {existing.email} (linked to {len(group_ids)} shift group(s))")
            return
        acc = get_account_by_email(db, email)
        if acc is None:
            acc = Account(email=email, hashed_password=hash_password(password))
            db.add(acc)
            db.flush()
        user = User(account_id=acc.id, organization_id=org.id, role=ROLE_PLANNER, locale="de")
        db.add(user)
        db.flush()
        for gid in group_ids:
            db.add(UserShiftGroup(user_id=user.id, shift_group_id=gid))
        db.commit()
        print(f"Planner user ready: {user.email} (linked to {len(group_ids)} shift group(s))")


if __name__ == "__main__":
    main()
