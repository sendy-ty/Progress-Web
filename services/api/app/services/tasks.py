"""
Celery background tasks with progress tracking.

Task list:
  run_odm_pipeline    — ODM orthomosaic generation (up to 1 h)
  run_yolo_detection  — YOLO tree detection
  run_pdf_report      — PDF report generation
  generate_tiles      — XYZ tile pyramid (GDAL or PIL)
  cleanup_old_files   — Scheduled storage housekeeping (daily @ 02:00 UTC)

Progress tracking:
  Tasks call self.update_state(state="PROGRESS", meta={...}) at key milestones.
  Clients poll GET /tasks/status/{task_id} which reads celery_app.AsyncResult.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.config import settings
from app.database.session import SessionLocal
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _progress(task_self, pct: int, message: str) -> None:
    """Push a PROGRESS state update to the Celery result backend."""
    task_self.update_state(
        state="PROGRESS",
        meta={"progress": pct, "status": "processing", "message": message},
    )
    logger.info(message, extra={"task_id": task_self.request.id, "progress": pct})


# ── Tasks ──────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.run_odm_pipeline",
    max_retries=0,
    acks_late=True,
    time_limit=3700,
    soft_time_limit=3680,
)
def run_odm_pipeline(self, project_id: str) -> dict:
    """
    ODM orthomosaic generation pipeline with progress reporting.

    Progress milestones:
      10% — project status set to 'processing'
      40% — ODM docker exec started
      80% — ODM finished, copying orthomosaic
      90% — Image record created
     100% — tile generation queued
    """
    db = SessionLocal()
    try:
        _progress(self, 10, f"Initialising ODM project {project_id}")
        from app.services.odm_service import run_odm, set_status

        _progress(self, 40, "Running ODM processing (this may take up to 1 hour)")
        run_odm(db=db, project_id=project_id)

        _progress(self, 100, "ODM complete — tile generation queued")
        logger.info(
            "ODM pipeline completed",
            extra={"event": "odm_completed", "project_id": project_id, "task_id": self.request.id},
        )
        return {"project_id": project_id, "status": "completed", "progress": 100}

    except Exception:
        from app.services.odm_service import set_status as _set
        _set(db=db, project_id=project_id, status_value="failed")
        logger.exception(
            "ODM pipeline failed",
            extra={"event": "odm_failed", "project_id": project_id, "task_id": self.request.id},
        )
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="tasks.run_yolo_detection",
    max_retries=0,
    acks_late=True,
    time_limit=600,
    soft_time_limit=570,
)
def run_yolo_detection(self, image_id: int, user_id: int) -> dict:
    """YOLO detection with progress reporting."""
    db = SessionLocal()
    try:
        _progress(self, 10, f"Preparing detection for image {image_id}")

        from app.database.models import User
        from app.services.detection_service import run_detection

        user = db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        _progress(self, 40, "Streaming image to YOLO inference service")
        result = run_detection(db=db, user=user, image_id=image_id)

        _progress(self, 90, "Generating annotated preview image")
        logger.info(
            "YOLO detection completed",
            extra={"event": "detection_completed", "image_id": image_id,
                   "tree_count": result.get("tree_count"), "task_id": self.request.id},
        )
        return {"image_id": image_id, "status": "completed", "progress": 100, **result}

    except Exception:
        logger.exception(
            "YOLO detection failed",
            extra={"event": "detection_failed", "image_id": image_id, "task_id": self.request.id},
        )
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="tasks.run_pdf_report",
    max_retries=0,
    acks_late=True,
    time_limit=120,
    soft_time_limit=100,
)
def run_pdf_report(self, image_id: int, user_id: int) -> dict:
    """PDF report generation with progress reporting."""
    db = SessionLocal()
    try:
        _progress(self, 20, "Loading detection results for report")

        from app.database.models import User
        from app.services.report_service import generate_pdf_report

        user = db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        _progress(self, 60, "Rendering PDF")
        url = generate_pdf_report(db=db, user=user, image_id=image_id)

        logger.info(
            "PDF report generated",
            extra={"event": "report_generated", "image_id": image_id,
                   "report_url": url, "task_id": self.request.id},
        )
        return {"image_id": image_id, "status": "completed", "progress": 100, "report_url": url}

    except Exception:
        logger.exception(
            "PDF report generation failed",
            extra={"event": "report_failed", "image_id": image_id, "task_id": self.request.id},
        )
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="tasks.generate_tiles",
    max_retries=0,
    acks_late=True,
    time_limit=1800,
    soft_time_limit=1750,
)
def generate_tiles(self, image_id: int, image_path: str) -> dict:
    """
    XYZ tile pyramid generation (GDAL backend, PIL fallback).
    Idempotent — skips if tiles already exist.
    """
    try:
        _progress(self, 10, f"Starting tile generation for image {image_id}")

        from app.services.tile_service import generate_tiles as _gen_tiles, tiles_exist
        if tiles_exist(image_id):
            logger.info(
                "Tile generation skipped — tiles already exist",
                extra={"event": "tile_generation_skipped", "image_id": image_id},
            )
            return {"image_id": image_id, "status": "completed", "progress": 100, "skipped": True}

        _progress(self, 30, "Running gdal2tiles")
        tile_dir = _gen_tiles(image_id=image_id, image_path=image_path)

        _progress(self, 100, "Tile generation complete")
        logger.info(
            "Tile generation completed",
            extra={"event": "tile_generation_completed", "image_id": image_id, "tile_dir": tile_dir},
        )
        return {"image_id": image_id, "status": "completed", "progress": 100, "tile_dir": tile_dir}

    except Exception:
        logger.exception(
            "Tile generation failed",
            extra={"event": "tile_generation_failed", "image_id": image_id},
        )
        raise


@celery_app.task(
    bind=True,
    name="tasks.cleanup_old_files",
    max_retries=0,
)
def cleanup_old_files(self) -> dict:
    """
    Scheduled storage housekeeping (runs daily at 02:00 UTC via Celery Beat).

    Deletes:
      - ODM project working directories older than 7 days
        (data/odm/projects/{project_id}/ — excludes final .tif in reports/)
      - Temporary thumbnails created for PDF embedding (*.tmp.jpg)

    NEVER deletes:
      - data/uploads/            — original orthomosaic images
      - data/reports/pdf/        — detection PDF reports
      - data/reports/orthomosaic/— final orthomosaic TIFFs
      - data/reports/tiles/      — generated tile pyramids
      - data/reports/annotated/  — annotated detection images
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    deleted_dirs: list[str] = []
    deleted_files: list[str] = []

    # ── ODM project working directories ───────────────────────────────────
    odm_projects_dir = Path(settings.odm_projects_dir)
    if odm_projects_dir.exists():
        for project_dir in odm_projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            mtime = datetime.fromtimestamp(project_dir.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                try:
                    shutil.rmtree(project_dir)
                    deleted_dirs.append(str(project_dir))
                    logger.info(
                        "Deleted old ODM project dir",
                        extra={"event": "cleanup_deleted_dir", "path": str(project_dir)},
                    )
                except OSError as exc:
                    logger.warning("Could not delete %s: %s", project_dir, exc)

    # ── Stale temp thumbnail files (*.tmp.jpg left on error) ──────────────
    import tempfile
    tmp_dir = Path(tempfile.gettempdir())
    for f in tmp_dir.glob("tmp*.jpg"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                deleted_files.append(str(f))
        except OSError:
            pass

    summary = {
        "deleted_odm_dirs": len(deleted_dirs),
        "deleted_tmp_files": len(deleted_files),
        "cutoff_days": 7,
        "status": "completed",
    }
    logger.info("Storage cleanup completed", extra={"event": "cleanup_completed", **summary})
    return summary
