"""
Structured logging utility.

All services should obtain a logger via:

    from app.utils.logging import get_logger
    logger = get_logger(__name__)

Log records include: timestamp, service name, event, and any extra fields
(image_id, task_id, project_id, etc.) passed as keyword arguments.

The format is JSON-compatible for production log aggregators (ELK, Loki, etc.)
and plain-text friendly when viewed with `docker logs`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """
    Emit one JSON line per log record.

    Example output:
    {"ts":"2026-03-10T10:46:07Z","level":"INFO","service":"app.services.detection_service",
     "event":"detection_queued","image_id":42,"task_id":"abc-123"}
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":      datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level":   record.levelname,
            "service": record.name,
            "event":   record.getMessage(),
        }
        # Merge any extra fields injected by the caller
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "message",
                "module", "msecs", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName",
            ):
                payload[key] = val

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """
    Configure root logger with StructuredFormatter.
    Call once at application startup (main.py).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "celery.app.trace"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger by name. Use __name__ as the name."""
    return logging.getLogger(name)
