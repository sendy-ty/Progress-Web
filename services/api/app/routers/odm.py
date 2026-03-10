"""
ODM orthomosaic pipeline endpoints.

Workflow:
  1. POST /odm/upload-zip              → stream ZIP to disk, extract images
  2. POST /odm/process/{project_id}    → enqueue Celery task (returns immediately)
  3. GET  /odm/{project_id}/status     → poll DB status
  4. GET  /odm/{project_id}/result     → get orthomosaic URL + linked image_id

Ownership: all endpoints check that the requesting user owns the project.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.common import Envelope
from app.schemas.odm_schema import (
    OdmProcessResponse,
    OdmResultResponse,
    OdmStatusResponse,
    OdmUploadZipResponse,
)
from app.services.odm_service import (
    create_project,
    extract_zip_from_disk,
    get_project_for_user,
    get_result_url,
    set_status,
)
from app.utils.logging import get_logger
from app.utils.responses import success

router = APIRouter(prefix="/odm", tags=["odm"])
logger = get_logger(__name__)

_CHUNK_SIZE = 1024 * 1024 * 8   # 8 MB
_MAX_ZIP_BYTES = 500 * 1024 ** 2  # 500 MB


async def _stream_zip_to_tmp(upload: UploadFile) -> str:
    """
    Stream uploaded ZIP to a NamedTemporaryFile without loading it into memory.
    Returns the temp file path (caller is responsible for deletion).
    """
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = tmp.name
        while True:
            chunk = await upload.read(_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_ZIP_BYTES:
                tmp.close()
                os.remove(tmp_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="ZIP file exceeds 500 MB limit",
                )
            tmp.write(chunk)
    return tmp_path


_ALLOWED_ZIP_MIMES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "multipart/x-zip",
}


@router.post(
    "/upload-zip",
    response_model=Envelope[OdmUploadZipResponse],
    summary="Stream a ZIP of drone images and create an ODM project",
    description=(
        "Upload a ZIP archive containing JPG/PNG drone images. "
        "The file is streamed to disk in 8 MB chunks (max 500 MB). "
        "A new ODM project UUID is returned for subsequent processing."
    ),
    responses={
        200: {"content": {"application/json": {"example": {
            "success": True,
            "data": {"project_id": "uuid-...", "status": "pending", "image_count": 120}
        }}}},
        400: {"description": "Not a ZIP file or ZIP contains no valid images"},
        413: {"description": "ZIP exceeds 500 MB limit"},
    },
)
async def upload_zip(
    file: UploadFile = File(..., description="ZIP archive containing JPG/PNG drone images (max 500 MB)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .zip archive")

    # Validate MIME type before streaming
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in _ALLOWED_ZIP_MIMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MIME type '{content_type}' for a ZIP upload",
        )

    # ── Stream ZIP to temp file (no full-file memory load) ─────────────────
    tmp_path = await _stream_zip_to_tmp(file)

    try:
        import zipfile
        if not zipfile.is_zipfile(tmp_path):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or corrupt ZIP file")

        project_id = str(uuid4())
        create_project(db=db, project_id=project_id, user_id=user.id)

        extracted = extract_zip_from_disk(project_id=project_id, zip_path=tmp_path)
        if not extracted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ZIP contains no valid images (.jpg, .jpeg, .png)",
            )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    logger.info(
        "ODM ZIP uploaded",
        extra={
            "event":       "odm_zip_uploaded",
            "project_id":  project_id,
            "image_count": len(extracted),
            "user":        user.username,
        },
    )
    return success(
        OdmUploadZipResponse(project_id=project_id, status="pending", image_count=len(extracted)),
        message="ZIP uploaded and images extracted",
    )


@router.post(
    "/process/{project_id}",
    response_model=Envelope[OdmProcessResponse],
    summary="Enqueue ODM orthomosaic processing (non-blocking Celery task)",
    description=(
        "Queues ODM processing for an existing project. Returns a `task_id` immediately. "
        "Poll `GET /tasks/status/{task_id}` for progress. "
        "Once completed, use `GET /odm/{project_id}/result` to get the orthomosaic URL."
    ),
    responses={
        200: {"content": {"application/json": {"example": {
            "success": True,
            "data": {"project_id": "uuid-...", "status": "queued", "task_id": "celery-task-id"}
        }}}},
        403: {"description": "Project belongs to a different user"},
        404: {"description": "Project not found"},
    },
)
async def process(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    get_project_for_user(db=db, project_id=project_id, user=user)

    from app.services.tasks import run_odm_pipeline
    task = run_odm_pipeline.delay(project_id=project_id)

    logger.info(
        "ODM processing queued",
        extra={
            "event":      "odm_processing_queued",
            "project_id": project_id,
            "task_id":    task.id,
            "user":       user.username,
        },
    )
    return success(
        OdmProcessResponse(project_id=project_id, status="queued", task_id=task.id),
        message="ODM processing queued",
    )


@router.get(
    "/{project_id}/status",
    response_model=Envelope[OdmStatusResponse],
    summary="Get ODM project status",
)
async def get_project_status(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    proj = get_project_for_user(db=db, project_id=project_id, user=user)
    return success(OdmStatusResponse(project_id=proj.id, status=proj.status))


@router.get(
    "/{project_id}/result",
    response_model=Envelope[OdmResultResponse],
    summary="Get orthomosaic result URL and linked image_id for YOLO detection",
)
async def get_project_result(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    proj = get_project_for_user(db=db, project_id=project_id, user=user)
    url = get_result_url(project_id) if proj.status == "completed" and proj.result_path else None
    return success(
        OdmResultResponse(
            project_id=proj.id,
            status=proj.status,
            orthomosaic_url=url,
            odm_image_id=proj.odm_image_id,
        )
    )
