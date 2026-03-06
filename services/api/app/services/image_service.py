from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Image, User
from app.utils.file_utils import atomic_write_bytes, ensure_dir, safe_uuid_filename


def build_public_url(stored_filename: str) -> str | None:
    if not settings.public_upload_base_url:
        return None
    return f"{settings.public_upload_base_url.rstrip('/')}/{stored_filename}"


def save_upload(*, db: Session, user: User, original_filename: str, content_type: str | None, content: bytes) -> Image:
    ensure_dir(settings.upload_dir)
    stored_filename = safe_uuid_filename(original_filename)
    abs_path = str(Path(settings.upload_dir) / stored_filename)
    atomic_write_bytes(abs_path, content)

    img = Image(
        user_id=user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_size_bytes=len(content),
        file_path=abs_path,
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

