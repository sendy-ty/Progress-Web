"""
Detection endpoints.

Workflow (async, recommended for large orthomosaics):
  1. POST /detection/run/{image_id}    → enqueue Celery task, return task_id
  2. GET  /detection/status/{task_id}  → poll until "completed" or "failed"
  3. GET  /detection/results/{image_id}→ retrieve stored bboxes from DB

Response contract:
  - Bounding boxes only: [{bbox: [x1, y1, x2, y2]}]
  - Confidence scores are NEVER returned.
  - Users can only access their own images (HTTP 403 if not owner).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.common import Envelope
from app.schemas.detection_schema import AsyncTaskResponse, DetectionRunResponse
from app.services.detection_service import get_results
from app.utils.logging import get_logger
from app.utils.responses import success

router = APIRouter(prefix="/detection", tags=["detection"])
logger = get_logger(__name__)

# Celery state → API status label
_STATE_MAP: dict[str, str] = {
    "PENDING": "queued",
    "STARTED": "processing",
    "SUCCESS": "completed",
    "FAILURE": "failed",
    "RETRY":   "processing",
    "REVOKED": "failed",
}


@router.post(
    "/run/{image_id}",
    response_model=Envelope[AsyncTaskResponse],
    summary="Queue YOLO detection (Celery task, non-blocking)",
    description=(
        "Enqueues a YOLO detection task for the given image. Returns a `task_id` immediately. "
        "Poll `GET /tasks/status/{task_id}` for progress (0-100). "
        "Once completed, fetch bboxes from `GET /detection/results/{image_id}`. "
        "**Note:** Only the image owner can trigger detection (HTTP 403 otherwise)."
    ),
    responses={
        200: {
            "content": {"application/json": {"example": {
                "success": True,
                "data": {"task_id": "a1b2c3-...", "status": "queued"}
            }}}
        },
        403: {"description": "Image belongs to a different user"},
        404: {"description": "Image not found"},
    },
)
def run(
    image_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Validate ownership before queuing — fail fast with clear error
    from app.services.detection_service import _get_image_owned
    _get_image_owned(db=db, user=user, image_id=image_id)

    from app.services.tasks import run_yolo_detection
    task = run_yolo_detection.delay(image_id=image_id, user_id=user.id)

    logger.info(
        "Detection task queued",
        extra={"event": "detection_queued", "image_id": image_id,
               "task_id": task.id, "user": user.username},
    )
    return success(
        AsyncTaskResponse(task_id=task.id, status="queued").model_dump(),
        "Detection queued — poll /tasks/status/{task_id} for progress",
    )


@router.get(
    "/status/{task_id}",
    response_model=Envelope[AsyncTaskResponse],
    summary="Poll status of a queued detection or report task",
)
def detection_status(task_id: str) -> dict:
    """
    Returns the Celery task state mapped to:
      queued | processing | completed | failed

    Note: 'completed' means the detection has been written to the DB.
    Fetch the actual bboxes with GET /detection/results/{image_id}.
    """
    from app.core.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    mapped = _STATE_MAP.get(result.state, result.state.lower())
    return success(AsyncTaskResponse(task_id=task_id, status=mapped).model_dump())


@router.get(
    "/results/{image_id}",
    response_model=Envelope[DetectionRunResponse],
    summary="Get stored detection results (bboxes) for an image",
)
def results(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """
    Returns the most recent detection run for an image.
    Bboxes are in original-image pixel coordinates [x1, y1, x2, y2].
    No confidence scores are returned.
    """
    result = get_results(db=db, user=user, image_id=image_id)
    DetectionRunResponse.model_validate(result)
    return success(result)
