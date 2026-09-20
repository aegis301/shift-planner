from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Organization
from app.services.duty_activity_privacy import purge_expired_duty_activity_episodes


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge duty-activity episodes past organization retention.")
    parser.add_argument("--organization-id", type=int, default=None)
    parser.add_argument("--as-of", type=str, default=None, help="ISO date used as the retention as-of date")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    with SessionLocal() as db:
        if args.organization_id is not None:
            organization_ids = [args.organization_id]
        else:
            organization_ids = list(db.scalars(select(Organization.id)))
        for organization_id in organization_ids:
            deleted = purge_expired_duty_activity_episodes(
                db,
                organization_id=organization_id,
                actor="purge_duty_activity",
                source="script",
                as_of=as_of,
            )
            print(f"organization {organization_id}: deleted {deleted}")


if __name__ == "__main__":
    main()
