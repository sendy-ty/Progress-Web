from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.common import Envelope
from app.schemas.image_schema import AnnotatedImagePublic, ImagePublic
from app.services.annotated_service import get_or_create_annotated_url
from app.services.image_service import (
    build_public_url,
    delete_image,
    get_image,
    list_images,
    save_upload_metadata,
)
from app.utils.file_utils import ensure_dir, generate_filename
from app.utils.logging import get_logger
from app.utils.responses import success

logger = get_logger(__name__)

router = APIRouter(prefix="/images", tags=["images"])

_CHUNK_SIZE = 1024 * 1024 * 8          # 8 MB chunks
_MAX_UPLOAD_BYTES = 5 * 1024 ** 3      # 5 GB hard cap
_ALLOWED_SUFFIXES = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}
# Accepted MIME types — validated before any bytes are written to disk
_ALLOWED_MIME_TYPES = {
    "image/tiff",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/octet-stream",  # some clients send this for TIFF
}


async def _stream_to_disk(upload: UploadFile, filepath: str) -> int:
    """
    Write an UploadFile to disk in 8 MB chunks.
    Never holds more than one chunk in memory.
    Returns the total number of bytes written.
    Raises HTTP 413 if the file exceeds 5 GB.
    """
    size = 0
    with open(filepath, "wb") as buf:
        while True:
            chunk = await upload.read(_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_UPLOAD_BYTES:
                buf.close()
                os.remove(filepath)
                raise HTTPException(
                    status_code=413,
                    detail="File exceeds maximum allowed upload size of 5 GB",
                )
            buf.write(chunk)
    return size


@router.post(
    "/upload",
    response_model=Envelope[ImagePublic],
    summary="Upload an orthomosaic image — TIFF, JPG, or PNG, up to 5 GB",
    description=(
        "Stream-upload a georeferenced orthomosaic image directly to disk. "
        "The full file is never loaded into API memory. "
        "Supported formats: TIFF, JPG, PNG. Maximum size: 5 GB."
    ),
    responses={
        200: {"description": "Image uploaded and registered"},
        400: {"description": "Unsupported file type or invalid MIME type"},
        413: {"description": "File exceeds 5 GB limit"},
    },
)
async def upload_image(
    file: UploadFile = File(..., description="Orthomosaic image file (TIFF/JPG/PNG, max 5 GB)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    suffix = Path(file.filename or "upload.tif").suffix.lower() or ".tif"
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: TIFF, JPG, PNG",
        )

    # Validate MIME type before writing anything to disk
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MIME type '{content_type}'. Allowed: image/tiff, image/jpeg, image/png",
        )

    ensure_dir(settings.upload_dir)
    
    import shutil
    free_space = shutil.disk_usage(settings.upload_dir).free
    if free_space < 10 * 1024**3:
        raise HTTPException(
            status_code=507,
            detail="Insufficient Storage: Free disk space is less than 10GB",
        )

    stored_filename = generate_filename(user.username, "upload", suffix)
    filepath = str(Path(settings.upload_dir) / stored_filename)

    # ── 1. Stream file to disk (no full-file memory load) ──────────────────
    file_size = await _stream_to_disk(file, filepath)

    # ── 2. Persist metadata only — file is already on disk ─────────────────
    img = save_upload_metadata(
        db=db,
        user=user,
        original_filename=file.filename or stored_filename,
        content_type=file.content_type,
        stored_filename=stored_filename,
        file_path=filepath,
        file_size_bytes=file_size,
    )

    logger.info(
        "Image uploaded",
        extra={
            "event":     "image_uploaded",
            "image_id":  img.id,
            "user":      user.username,
            "original_filename":  img.original_filename,
            "size_mb":   round(file_size / 1024 / 1024, 2),
        },
    )

    item = ImagePublic.model_validate(img).model_dump()
    item["url"] = build_public_url(img.stored_filename)
    return success(item, "Image uploaded")


@router.get("", response_model=Envelope[list[ImagePublic]], summary="List uploaded images")
def images(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    imgs = list_images(db=db, user=user, limit=limit, offset=offset)
    data = []
    for img in imgs:
        item = ImagePublic.model_validate(img).model_dump()
        item["url"] = build_public_url(img.stored_filename)
        data.append(item)
    return success(data)


@router.get("/{image_id}", response_model=Envelope[ImagePublic], summary="Get image metadata")
def image_detail(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    img = get_image(db=db, user=user, image_id=image_id)
    item = ImagePublic.model_validate(img).model_dump()
    item["url"] = build_public_url(img.stored_filename)
    return success(item)


@router.delete("/{image_id}", response_model=Envelope[dict], summary="Delete an image")
def image_delete(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    delete_image(db=db, user=user, image_id=image_id)
    return success({}, "Image deleted")


@router.get(
    "/{image_id}/annotated",
    response_model=Envelope[AnnotatedImagePublic],
    summary="Get URL for annotated detection image",
)
def annotated_image(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    url = get_or_create_annotated_url(db=db, user=user, image_id=image_id)
    return success(AnnotatedImagePublic(image_id=image_id, annotated_url=url))