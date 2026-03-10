"""
Task status polling endpoint.

GET /tasks/status/{task_id}

Returns task progress (0-100) and status labels:
  queued | processing | completed | failed
"""
from __future__ import annotations

from fastapi import APIRouter
from app.schemas.common import Envelope
from app.utils.responses import success

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Map Celery native states → API labels
_STATE_MAP: dict[str, str] = {
    "PENDING":  "queued",
    "RECEIVED": "queued",
    "STARTED":  "processing",
    "PROGRESS": "processing",
    "SUCCESS":  "completed",
    "FAILURE":  "failed",
    "RETRY":    "processing",
    "REVOKED":  "failed",
}


@router.get(
    "/status/{task_id}",
    response_model=Envelope[dict],
    summary="Get Celery task progress and status",
    description=(
        "Poll this endpoint after queuing any background task "
        "(detection, ODM, tile generation, PDF report).\n\n"
        "**Status values:** `queued` | `processing` | `completed` | `failed`\n\n"
        "**Progress:** 0–100 integer, updated at each task milestone."
    ),
    responses={
        200: {
            "description": "Task status and progress",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "task_id": "a1b2c3d4-...",
                            "status": "processing",
                            "progress": 40,
                            "message": "Running ODM processing",
                        }
                    }
                }
            }
        }
    },
)
def task_status(task_id: str) -> dict:
    from app.core.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)

    state = result.state
    status = _STATE_MAP.get(state, state.lower())
    meta = result.info if isinstance(result.info, dict) else {}

    payload: dict = {
        "task_id":  task_id,
        "status":   status,
        "progress": meta.get("progress", 100 if state == "SUCCESS" else 0),
        "message":  meta.get("message", ""),
    }

    # Include task result data when completed
    if state == "SUCCESS" and isinstance(result.result, dict):
        payload["result"] = result.result

    # Surface error details on failure
    if state == "FAILURE":
        payload["error"] = str(result.info) if result.info else "Unknown error"

    return success(payload)
