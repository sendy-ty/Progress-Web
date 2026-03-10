"""
Annotated image generation service.
Draws bounding boxes only (no confidence labels, no class names).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Detection, Image, User
from app.services.image_service import build_public_report_url
from app.utils.annotate_image import draw_detections


def generate_annotated_image(
    *,
    image_path: str,
    bboxes: list[list[float]],
    output_path: str,
) -> str:
    """
    Render bounding boxes onto the source image and save as JPEG.

    Args:
        image_path:  Absolute path to the source orthomosaic image.
        bboxes:      List of [x1,y1,x2,y2] pixel coordinates.
        output_path: Destination path for the annotated JPEG.

    Returns:
        output_path (for convenience).
    """
    detections = [{"bbox": bbox} for bbox in bboxes]
    draw_detections(image_path=image_path, detections=detections, output_path=output_path)
    return output_path


def get_or_create_annotated_url(*, db: Session, user: User, image_id: int) -> str:
    """
    Return the public URL for an annotated image.
    If the file does not yet exist on disk, regenerate it from stored detections.

    Raises HTTP 404 if the image is not found or no detections exist yet.
    """
    img = db.get(Image, image_id)
    if not img or img.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    annotated_abs = str(Path(settings.annotated_dir) / f"{img.id}.jpg")

    # Fast path: annotated file already exists on disk
    if os.path.isfile(annotated_abs):
        return build_public_report_url(f"annotated/{img.id}.jpg")

    # Slow path: load stored detection and re-render
    det = (
        db.execute(
            select(Detection)
            .where(Detection.image_id == img.id)
            .order_by(Detection.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    # BUG FIX (v4): previously indexed `dets[0]` on a scalar ORM object.
    # `det` is now correctly a single Detection row or None.
    if not det or not det.bboxes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No detections found for this image. Run detection first.",
        )

    bboxes: list[list[float]] = det.bboxes or []
    generate_annotated_image(
        image_path=img.file_path,
        bboxes=bboxes,
        output_path=annotated_abs,
    )
    return build_public_report_url(f"annotated/{img.id}.jpg")
