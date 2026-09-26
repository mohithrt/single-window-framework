"""Optional Redis cache with a safe in-process fallback.

Redis is deliberately opt-in so the local no-Docker developer workflow remains
unchanged. Set REDIS_ENABLED=true and REDIS_URL to enable the shared cache.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import settings

try:
    import redis
except ImportError:  # pragma: no cover - dependency is optional at runtime
    redis = None


_LOCAL: dict[str, tuple[float, str]] = {}


class CacheService:
    def __init__(self) -> None:
        self.enabled = bool(settings.redis_enabled and redis is not None)
        self._client = None
        if self.enabled:
            try:
                self._client = redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                )
            except Exception:
                self.enabled = False

    def get(self, key: str) -> Any | None:
        if self._client is not None:
            try:
                value = self._client.get(key)
                return None if value is None else json.loads(value)
            except Exception:
                pass
        item = _LOCAL.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= time.time():
            _LOCAL.pop(key, None)
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        ttl = ttl or max(1, settings.redis_cache_ttl_seconds)
        encoded = json.dumps(value, default=str)
        if self._client is not None:
            try:
                self._client.setex(key, ttl, encoded)
                return True
            except Exception:
                pass
        _LOCAL[key] = (time.time() + ttl, encoded)
        return False

    def delete(self, key: str) -> None:
        if self._client is not None:
            try:
                self._client.delete(key)
            except Exception:
                pass
        _LOCAL.pop(key, None)

    def health(self) -> dict[str, Any]:
        if not settings.redis_enabled:
            return {"configured": False, "available": False, "mode": "disabled"}
        if self._client is None:
            return {"configured": True, "available": False, "mode": "fallback"}
        try:
            self._client.ping()
            return {"configured": True, "available": True, "mode": "redis"}
        except Exception as exc:
            return {"configured": True, "available": False, "mode": "fallback", "error": type(exc).__name__}
