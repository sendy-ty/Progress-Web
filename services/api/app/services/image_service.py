from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Image, User
from app.utils.file_utils import ensure_dir


def build_public_url(stored_filename: str) -> str:
    base = settings.public_upload_base_url
    if not base:
        return f"/uploads/{stored_filename}"
    return f"{base.rstrip('/')}/{stored_filename}"


def build_public_report_url(relative_path: str) -> str:
    base = settings.public_reports_base_url
    if not base:
        return f"/reports/{relative_path.lstrip('/')}"
    return f"{base.rstrip('/')}/{relative_path.lstrip('/')}"


def save_upload_metadata(
    *,
    db: Session,
    user: User,
    original_filename: str,
    content_type: str | None,
    stored_filename: str,
    file_path: str,
    file_size_bytes: int,
) -> Image:
    """
    Persist image metadata to the database only — performs NO file I/O.

    The caller must stream the file to disk *before* calling this so that
    file_size_bytes is accurate and the file already exists at file_path.
    This replaces the old save_upload() which wrote an empty ghost file.
    """
    img = Image(
        user_id=user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        file_path=file_path,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return img


def list_images(*, db: Session, user: User, limit: int, offset: int) -> list[Image]:
    return (
        db.execute(
            select(Image)
            .where(Image.user_id == user.id)
            .order_by(Image.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )


def get_image(*, db: Session, user: User, image_id: int) -> Image:
    img = db.get(Image, image_id)
    if not img or img.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return img


def delete_image(*, db: Session, user: User, image_id: int) -> None:
    img = get_image(db=db, user=user, image_id=image_id)
    try:
        if img.file_path and os.path.isfile(img.file_path):
            os.remove(img.file_path)
    finally:
        db.delete(img)
        db.commit()
