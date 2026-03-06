from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_uuid_filename(original_filename: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        # Default to .jpg if unknown; content-type validation happens separately.
        suffix = ".jpg"
    return f"{uuid4().hex}{suffix}"


async def read_upload_validated(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    return content


def atomic_write_bytes(dst_path: str, content: bytes) -> None:
    dst = Path(dst_path)
    tmp = dst.with_suffix(dst.suffix + f".{uuid4().hex}.tmp")
    ensure_dir(str(dst.parent))
    tmp.write_bytes(content)
    os.replace(tmp, dst)

