from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.services.solver_fixture import (
    PROFILES,
    SolverFixtureError,
    SolverFixtureSafetyError,
    default_target_year_month,
    seed_solver_fixture,
)


def main() -> None:
    default_year, default_month = default_target_year_month()
    parser = argparse.ArgumentParser(
        description="Seed a deterministic planning month plus history for solver work."
    )
    parser.add_argument("--profile", choices=PROFILES, default="comfortable")
    parser.add_argument("--rng-seed", type=int, default=1)
    parser.add_argument("--history-months", type=int, default=6)
    parser.add_argument("--year", type=int, default=default_year)
    parser.add_argument("--month", type=int, default=default_month)
    parser.add_argument("--organization-id", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            result = seed_solver_fixture(
                db,
                profile=args.profile,
                rng_seed=args.rng_seed,
                history_months=args.history_months,
                year=args.year,
                month=args.month,
                organization_id=args.organization_id,
                force=args.force,
            )
    except SolverFixtureSafetyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except SolverFixtureError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        f"Seeded {result.profile} org {result.organization_id} "
        f"({result.organization_slug}) target {result.year}-{result.month:02d} "
        f"period {result.target_period_id}"
    )


if __name__ == "__main__":
    main()
