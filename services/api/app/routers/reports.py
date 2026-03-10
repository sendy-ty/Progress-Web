from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.common import Envelope
from app.schemas.detection_schema import AsyncTaskResponse
from app.schemas.report_schema import ReportGenerateResponse
from app.services.report_service import generate_pdf_report
from app.utils.logging import get_logger
from app.utils.responses import success

router = APIRouter(prefix="/reports", tags=["reports"])
logger = get_logger(__name__)


@router.post(
    "/generate/{image_id}",
    response_model=Envelope[ReportGenerateResponse],
    summary="Generate PDF detection report (synchronous)",
    description=(
        "Generates a PDF report containing orthomosaic preview, annotated detection image, "
        "username, email, model version, upload timestamp, and total tree count. "
        "Returns the public URL of the generated PDF immediately. "
        "For large images use `POST /reports/async/{image_id}` instead."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {"report_url": "http://host/reports/pdf/sandy-report-20260310-103000.pdf"},
                    }
                }
            }
        },
        403: {"description": "Image belongs to a different user"},
        404: {"description": "Image not found or no detections recorded yet"},
    },
)
def generate(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    url = generate_pdf_report(db=db, user=user, image_id=image_id)
    logger.info(
        "PDF report generated",
        extra={"event": "report_generated", "image_id": image_id, "report_url": url, "user": user.username},
    )
    return success(ReportGenerateResponse(report_url=url), "Report generated")


@router.post(
    "/async/{image_id}",
    response_model=Envelope[AsyncTaskResponse],
    summary="Queue PDF generation (Celery task, non-blocking)",
    description=(
        "Enqueues PDF report generation as a background task. "
        "Returns a `task_id` immediately. Poll `GET /tasks/status/{task_id}` for progress."
    ),
    responses={
        200: {"content": {"application/json": {"example": {
            "success": True,
            "data": {"task_id": "celery-task-id", "status": "queued"}
        }}}},
    },
)
def generate_async(
    image_id: int,
    user=Depends(get_current_user),
) -> dict:
    from app.services.tasks import run_pdf_report
    task = run_pdf_report.delay(image_id=image_id, user_id=user.id)
    logger.info(
        "PDF report queued",
        extra={"event": "report_queued", "image_id": image_id, "task_id": task.id, "user": user.username},
    )
    return success(
        AsyncTaskResponse(task_id=task.id, status="queued").model_dump(),
        "Report generation queued",
    )
