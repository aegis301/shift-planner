from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.solver_runs import process_one_queued_run

logger = logging.getLogger("solver_worker")


def run_forever(*, poll_interval_seconds: float | None = None) -> None:
    interval = (
        settings.solver_worker_poll_interval_seconds
        if poll_interval_seconds is None
        else poll_interval_seconds
    )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.info("solver worker polling every %s seconds", interval)
    while True:
        try:
            with SessionLocal() as db:
                processed = process_one_queued_run(db)
            if processed is None:
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("solver worker stopped")
            return
        except Exception:
            logger.exception("solver worker loop failed")
            time.sleep(interval)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
