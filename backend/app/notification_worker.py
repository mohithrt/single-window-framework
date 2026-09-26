"""Process queued external notification jobs.

Run with:
    python -m app.notification_worker
"""

from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.notification_delivery import NotificationDelivery
from app.queue_service import QueueService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mahaclear.notification_worker")


def run_once() -> bool:
    job = QueueService().dequeue("notifications", timeout=2)
    if not job:
        return False
    results = NotificationDelivery().deliver_now(
        email=job.get("email"),
        phone=job.get("phone"),
        subject=job.get("subject", "MahaClear notification"),
        message=job.get("message", ""),
        metadata=job.get("metadata") or {},
    )
    logger.info("notification delivery result=%s", results)
    return True


def main() -> None:
    logger.info("Notification worker started")
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Notification worker failed; retrying")
            time.sleep(2)


if __name__ == "__main__":
    main()
