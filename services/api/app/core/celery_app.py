"""
Celery application factory.

Broker and backend: Redis
Beat schedule:      cleanup_old_files runs daily at 02:00 UTC
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "durian_worker",
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend),
    include=["app.services.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Time zone
    timezone="UTC",
    enable_utc=True,

    # Tracking
    task_track_started=True,

    # One task at a time per worker slot — prevents ODM jobs from starving detection
    worker_prefetch_multiplier=1,

    # Keep task results for 24 h so clients can poll status
    result_expires=86400,

    # Retry on unexpected worker crash
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Beat periodic tasks
    beat_schedule={
        "cleanup-old-files-daily": {
            "task": "tasks.cleanup_old_files",
            "schedule": crontab(hour=2, minute=0),   # every day at 02:00 UTC
            "options": {"queue": "celery"},
        },
    },
)
