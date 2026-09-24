"""Periodic database-backed SLA sweep. Run as `python -m app.sla_worker`."""

import logging
import time

from app.core.config import settings
from app.database import SessionLocal
from app.sla_service import SlaService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mahaclear.sla_worker")


def run_once() -> int:
    with SessionLocal() as db:
        escalated = SlaService().check_and_escalate(db)
        return len(escalated)


def main() -> None:
    interval = max(15, settings.sla_check_interval_seconds)
    logger.info("SLA worker started; interval=%s seconds", interval)
    while True:
        try:
            count = run_once()
            if count:
                logger.info("Created %s SLA escalations", count)
        except Exception:
            logger.exception("SLA sweep failed; it will retry after the interval")
        time.sleep(interval)


if __name__ == "__main__":
    main()
