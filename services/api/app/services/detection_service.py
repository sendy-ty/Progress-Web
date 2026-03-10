"""
YOLO detection pipeline.

Input:  orthomosaic image already uploaded via POST /images/upload.
Output: tree_count + detections [{bbox:[x1,y1,x2,y2]}]
        annotated image saved to data/reports/annotated/{image_id}.jpg

Memory strategy: the image file is streamed from disk to the YOLO service
via an open file handle — the full image is never loaded into the API process.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Detection, Image, User
from app.services.annotated_service import generate_annotated_image
from app.utils.yolo_client import YoloClient

logger = logging.getLogger(__name__)


def _get_image_owned(*, db: Session, user: User, image_id: int) -> Image:
    img = db.get(Image, image_id)
    if not img or img.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return img


def _extract_bboxes(detections_in: list) -> list[list[float]]:
    """Extract [x1,y1,x2,y2] from YOLO detections. Confidence scores are discarded."""
    bboxes: list[list[float]] = []
    for d in detections_in:
        bbox = d.get("bbox") if isinstance(d, dict) else d
        if not bbox or len(bbox) != 4:
            continue
        bboxes.append([float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])])
    return bboxes


def run_detection(*, db: Session, user: User, image_id: int) -> dict:
    """
    Run YOLO detection on an orthomosaic image.

    Flow:
    1. Verify image ownership
    2. Stream image file to ai-yolo /detect (no in-memory load)
    3. Strip confidence scores from response
    4. Upsert Detection record (one row per run)
    5. Generate annotated JPEG via PIL (green bboxes, no labels)
    6. Return {tree_count, detections}
    """
    img = _get_image_owned(db=db, user=user, image_id=image_id)

    if not img.file_path or not Path(img.file_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file missing on server",
        )

    yolo = YoloClient()
    try:
        yolo_result = yolo.detect(
            filename=img.original_filename,
            file_path=img.file_path,
            content_type=img.content_type or "image/jpeg",
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"YOLO service error: {e}")

    logger.info(
        "Raw YOLO response received",
        extra={
            "event": "yolo_raw_response",
            "image_id": image_id,
            "tree_count": yolo_result.get("tree_count"),
            "detection_count": len(yolo_result.get("detections") or []),
            "model_version": yolo_result.get("model_version", "unknown"),
        },
    )

    bboxes = _extract_bboxes(yolo_result.get("detections") or [])
    tree_count = int(yolo_result.get("tree_count") or len(bboxes))
    model_version = str(yolo_result.get("model_version", "unknown"))

    # Upsert: replace previous detection run for this image
    db.execute(delete(Detection).where(Detection.image_id == img.id))
    db.add(Detection(
        image_id=img.id,
        tree_count=tree_count,
        model_version=model_version,
        bboxes=bboxes,
    ))
    db.commit()

    # Generate annotated image synchronously after detection.
    # Failure is logged but does NOT fail the detection response —
    # the result is already persisted in DB.
    annotated_abs = str(Path(settings.annotated_dir) / f"{img.id}.jpg")
    try:
        generate_annotated_image(
            image_path=img.file_path,
            bboxes=bboxes,
            output_path=annotated_abs,
        )
    except Exception:
        logger.warning(
            "Annotated image generation failed for image_id=%s — "
            "detection result is saved, annotated file unavailable.",
            img.id,
            exc_info=True,
        )

    return {
        "tree_count": tree_count,
        "detections": [{"bbox": bbox} for bbox in bboxes],
    }


def get_results(*, db: Session, user: User, image_id: int) -> dict:
    """Return the most recent stored detection result for an image."""
    img = _get_image_owned(db=db, user=user, image_id=image_id)
    row = (
        db.execute(
            select(Detection)
            .where(Detection.image_id == img.id)
            .order_by(Detection.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not row:
        return {"tree_count": 0, "detections": []}
    bboxes = row.bboxes or []
    return {
        "tree_count": row.tree_count,
        "detections": [{"bbox": bbox} for bbox in bboxes],
    }