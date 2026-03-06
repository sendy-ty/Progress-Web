from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import Detection, Image, User
from app.utils.yolo_client import YoloClient


def _get_image_owned(*, db: Session, user: User, image_id: int) -> Image:
    img = db.get(Image, image_id)
    if not img or img.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return img


def run_detection(*, db: Session, user: User, image_id: int) -> dict:
    img = _get_image_owned(db=db, user=user, image_id=image_id)
    try:
        content = open(img.file_path, "rb").read()
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file missing on server")

    yolo = YoloClient()
    try:
        yolo_result = yolo.infer(filename=img.original_filename, content=content, content_type=img.content_type)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"YOLO service error: {e}")

    # Replace previous detections for this image
    db.execute(delete(Detection).where(Detection.image_id == img.id))

    detections_in = yolo_result.get("detections") or []
    det_rows: list[Detection] = []
    for d in detections_in:
        det_rows.append(
            Detection(
                image_id=img.id,
                confidence=float(d.get("confidence", 0.0)),
                bbox=list(d.get("bbox", [])),
                tree_type=str(d.get("tree_type") or "durian"),
            )
        )
    db.add_all(det_rows)
    db.commit()

    return {
        "tree_count": int(yolo_result.get("tree_count") or len(det_rows)),
        "detections": [
            {"confidence": det.confidence, "bbox": det.bbox, "tree_type": det.tree_type} for det in det_rows
        ],
        "annotated_image_base64": yolo_result.get("annotated_image"),
    }


def get_results(*, db: Session, user: User, image_id: int) -> dict:
    img = _get_image_owned(db=db, user=user, image_id=image_id)
    dets = db.execute(select(Detection).where(Detection.image_id == img.id).order_by(Detection.id.asc())).scalars().all()
    return {
        "tree_count": len(dets),
        "detections": [{"confidence": d.confidence, "bbox": d.bbox, "tree_type": d.tree_type} for d in dets],
        "annotated_image_base64": None,
    }

