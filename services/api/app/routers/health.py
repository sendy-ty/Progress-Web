"""
Extended health monitoring endpoint.

GET /health — checks all critical dependencies and returns a structured report.
"""
from __future__ import annotations

import shutil

from fastapi import APIRouter
from app.schemas.common import Envelope
from app.utils.responses import success
from app.core.config import settings
from app.utils.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


def _check_database() -> str:
    try:
        from app.database.session import engine
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Health: database check failed: %s", exc)
        return f"error: {exc}"


def _check_redis() -> str:
    try:
        import redis as _redis
        r = _redis.from_url(settings.celery_broker_url, socket_connect_timeout=2)
        r.ping()
        return "ok"
    except Exception as exc:
        logger.warning("Health: Redis check failed: %s", exc)
        return f"error: {exc}"


def _check_celery_workers() -> int:
    """Return number of active Celery workers (0 if none or unreachable)."""
    try:
        from app.core.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active()
        return len(active) if active else 0
    except Exception:
        return 0


def _disk_usage_percent(path: str) -> float:
    try:
        usage = shutil.disk_usage(path)
        return round(usage.used / usage.total * 100, 1)
    except OSError:
        return -1.0


@router.get(
    "/health",
    response_model=Envelope[dict],
    summary="Extended health check",
    description="Checks database, Redis, Celery workers, and disk usage.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "status": "healthy",
                            "database": "ok",
                            "redis": "ok",
                            "celery_workers": 2,
                            "disk_usage_percent": 45.3,
                        }
                    }
                }
            }
        }
    },
)
def health() -> dict:
    db_status    = _check_database()
    redis_status = _check_redis()
    workers      = _check_celery_workers()
    disk_pct     = _disk_usage_percent(settings.upload_dir)

    overall = "healthy"
    if db_status != "ok" or redis_status != "ok":
        overall = "degraded"
    if workers == 0:
        overall = "degraded"

    return success({
        "status":              overall,
        "database":            db_status,
        "redis":               redis_status,
        "celery_workers":      workers,
        "disk_usage_percent":  disk_pct,
        "upload_dir":          settings.upload_dir,
    })
