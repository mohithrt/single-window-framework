"""Small Redis-backed job queue with an in-process fallback."""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from app.cache_service import CacheService

_LOCAL_QUEUES: dict[str, deque[str]] = {}


class QueueService:
    def __init__(self) -> None:
        self.cache = CacheService()

    @property
    def redis(self):
        return getattr(self.cache, "_client", None)

    def enqueue(self, name: str, payload: dict[str, Any]) -> bool:
        encoded = json.dumps(payload, default=str)
        if self.redis is not None:
            try:
                self.redis.rpush(f"queue:{name}", encoded)
                return True
            except Exception:
                pass
        _LOCAL_QUEUES.setdefault(name, deque()).append(encoded)
        return False

    def dequeue(self, name: str, timeout: int = 2) -> dict[str, Any] | None:
        encoded = None
        if self.redis is not None:
            try:
                result = self.redis.blpop(f"queue:{name}", timeout=max(0, timeout))
                if result:
                    encoded = result[1]
            except Exception:
                pass
        if encoded is None:
            queue = _LOCAL_QUEUES.setdefault(name, deque())
            if queue:
                encoded = queue.popleft()
        if encoded is None:
            return None
        return json.loads(encoded)

    def health(self) -> dict[str, Any]:
        if self.redis is None:
            return {"configured": False, "available": False, "mode": "local"}
        try:
            self.redis.ping()
            return {"configured": True, "available": True, "mode": "redis"}
        except Exception:
            return {"configured": True, "available": False, "mode": "local"}
