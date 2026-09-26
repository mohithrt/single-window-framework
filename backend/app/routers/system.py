"""System dependency and capability health endpoints."""

from __future__ import annotations

import shutil
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cache_service import CacheService
from app.core.config import settings
from app.database import get_db
from app.dependencies import require_roles
from app.integration_service import provider_catalog
from app.models import RoleCode
from app.queue_service import QueueService

router = APIRouter(prefix="/system", tags=["system health"], dependencies=[Depends(require_roles(RoleCode.ADMIN))])
Database = Annotated[Session, Depends(get_db)]


@router.get("/health")
def system_health(db: Database) -> dict:
    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "engine": "postgresql"}
    except Exception as exc:
        checks["database"] = {"status": "error", "error": type(exc).__name__}

    checks["cache"] = CacheService().health()
    checks["queue"] = QueueService().health()
    checks["ocr"] = {
        "status": "ok" if shutil.which("tesseract") else "unavailable",
        "tesseract_installed": bool(shutil.which("tesseract")),
    }
    checks["llm"] = {
        "status": "configured" if settings.llm_api_key else "rule_based",
        "model": settings.llm_model,
    }
    integrations = provider_catalog()
    checks["integrations"] = {
        "status": "configured" if any(item["connected_to_government"] for item in integrations) else "mock",
        "configured_count": sum(1 for item in integrations if item["configured"]),
        "total": len(integrations),
    }
    degraded = any(item.get("status") in {"error", "unavailable"} for item in checks.values())
    return {
        "status": "degraded" if degraded else "ok",
        "service": "mahaclear-ai-api",
        "checks": checks,
        "features": {
            "redis_enabled": settings.redis_enabled,
            "external_notifications": settings.notification_mode not in {"mock", "disabled"},
            "configured_integrations": [item["code"] for item in integrations if item["configured"]],
        },
    }
