"""
ODM orthomosaic pipeline service.

Storage layout:
    data/odm/projects/{project_id}/
        images/     ← extracted drone JPG/PNG images
        results/    ← copy of ODM output

ODM container path (shared volume):
    /datasets/projects/{project_id}/images/

After ODM completes:
    - orthomosaic copied to data/reports/orthomosaic/{project_id}.tif
    - an Image record is created for the TIF so it can be fed into YOLO
    - OdmProject.odm_image_id is set to that Image record
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Image, OdmProject, User
from app.utils.file_utils import ensure_dir, extract_zip_images_from_disk, generate_filename

logger = logging.getLogger(__name__)


# ── Internal path helpers ──────────────────────────────────────────────────

def _project_dir(project_id: str) -> Path:
    return Path(settings.odm_projects_dir) / project_id


def _images_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "images"


def _results_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "results"


# ── Public API ─────────────────────────────────────────────────────────────

def create_project(*, db: Session, project_id: str, user_id: int) -> OdmProject:
    """Create DB record + directory structure for a new ODM project."""
    proj = OdmProject(id=project_id, user_id=user_id, status="pending", result_path=None)
    db.add(proj)
    db.commit()
    db.refresh(proj)

    ensure_dir(str(_images_dir(project_id)))
    ensure_dir(str(_results_dir(project_id)))
    return proj


def extract_zip_from_disk(*, project_id: str, zip_path: str) -> list[str]:
    """
    Extract image files (.jpg/.jpeg/.png) from a ZIP already on disk.
    Returns list of extracted filenames.
    ZIP is never loaded into memory — extraction reads from the file on disk.
    """
    dest = str(_images_dir(project_id))
    return extract_zip_images_from_disk(zip_path, dest)


def set_status(
    *,
    db: Session,
    project_id: str,
    status_value: str,
    result_path: str | None = None,
    odm_image_id: int | None = None,
) -> None:
    proj = db.get(OdmProject, project_id)
    if not proj:
        return
    proj.status = status_value
    if result_path is not None:
        proj.result_path = result_path
    if odm_image_id is not None:
        proj.odm_image_id = odm_image_id
    db.commit()


def run_odm(*, db: Session, project_id: str) -> None:
    """
    Execute ODM inside the odm container via docker exec.

    After success:
    1. Copies orthomosaic TIFF to data/reports/orthomosaic/
    2. Creates an Image record for the TIFF (owned by the project's user)
    3. Sets OdmProject.odm_image_id so the result is reachable via /detection/run
    """
    set_status(db=db, project_id=project_id, status_value="processing")

    proj = db.get(OdmProject, project_id)
    if not proj:
        raise RuntimeError(f"ODM project {project_id} not found in database")

    # ODM reads from /datasets/projects/{project_id}/images/
    cmd = [
        "docker", "exec", "odm",
        "odm",
        "--project-path", "/datasets/projects",
        "--project-name", project_id,
    ]
    logger.info("Starting ODM for project %s: %s", project_id, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.error("ODM failed for project %s:\n%s", project_id, result.stderr or result.stdout)
        set_status(db=db, project_id=project_id, status_value="failed")
        raise RuntimeError(f"ODM failed: {result.stderr or result.stdout or 'unknown error'}")

    # ODM output path inside the shared volume
    odm_out_tif = _project_dir(project_id) / "odm_orthophoto" / "odm_orthophoto.tif"
    if not odm_out_tif.exists():
        set_status(db=db, project_id=project_id, status_value="failed")
        raise FileNotFoundError(f"ODM orthophoto not found at {odm_out_tif}")

    # ── Copy to reports/orthomosaic/ (served by NGINX) ────────────────────
    ortho_dir = Path(settings.orthomosaic_dir)
    ortho_dir.mkdir(parents=True, exist_ok=True)
    result_tif = ortho_dir / f"{project_id}.tif"
    shutil.copyfile(odm_out_tif, result_tif)

    # Also copy to project results/ folder for reference
    results_tif = _results_dir(project_id) / "orthomosaic.tif"
    shutil.copyfile(odm_out_tif, results_tif)

    # ── Register the orthomosaic as an Image record ───────────────────────
    # Naming convention: {username}-odm-{datetime}.tif
    user_id = proj.user_id
    user = db.get(User, user_id) if user_id else None
    username = user.username if user else "system"
    stored_filename = generate_filename(username, "odm", ".tif")
    # Symlink / copy into uploads so it is reachable via /uploads/
    upload_path = Path(settings.upload_dir) / stored_filename
    shutil.copyfile(result_tif, upload_path)

    odm_image = Image(
        user_id=user_id,
        original_filename=f"orthomosaic_{project_id}.tif",
        stored_filename=stored_filename,
        content_type="image/tiff",
        file_size_bytes=upload_path.stat().st_size,
        file_path=str(upload_path),
    )
    db.add(odm_image)
    db.commit()
    db.refresh(odm_image)

    set_status(
        db=db,
        project_id=project_id,
        status_value="completed",
        result_path=str(result_tif),
        odm_image_id=odm_image.id,
    )
    logger.info(
        "ODM project %s completed. Orthomosaic Image id=%s", project_id, odm_image.id
    )

    # Enqueue tile generation as an independent Celery task so the map viewer
    # can display tiles without blocking the ODM completion response.
    try:
        from app.services.tasks import generate_tiles as _tile_task
        _tile_task.delay(image_id=odm_image.id, image_path=str(upload_path))
        logger.info("Tile generation queued for image_id=%s", odm_image.id)
    except Exception:
        logger.warning(
            "Could not queue tile generation for image_id=%s — tiles will be unavailable",
            odm_image.id,
            exc_info=True,
        )


def get_project_for_user(*, db: Session, project_id: str, user: User) -> OdmProject:
    proj = db.get(OdmProject, project_id)
    if not proj or (proj.user_id is not None and proj.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ODM project not found")
    return proj


def get_result_url(project_id: str) -> str:
    base = (settings.public_reports_base_url or "").rstrip("/")
    if base:
        return f"{base}/orthomosaic/{project_id}.tif"
    return f"/reports/orthomosaic/{project_id}.tif"
