from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.detection_schema import DetectionRunResponse
from app.schemas.common import Envelope
from app.services.detection_service import get_results, run_detection
from app.utils.responses import success


router = APIRouter(prefix="/detection", tags=["detection"])


@router.post("/run/{image_id}", response_model=Envelope[DetectionRunResponse], summary="Run YOLO detection for an uploaded image")
def run(image_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    result = run_detection(db=db, user=user, image_id=image_id)
    # Validate shape for Swagger docs (while returning envelope)
    DetectionRunResponse.model_validate(result)
    return success(result, "Detection complete")


@router.get("/results/{image_id}", response_model=Envelope[DetectionRunResponse], summary="Get detection results for an image")
def results(image_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    result = get_results(db=db, user=user, image_id=image_id)
    DetectionRunResponse.model_validate(result)
    return success(result)

