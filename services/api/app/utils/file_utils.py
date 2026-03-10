from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
ALLOWED_ZIP_CONTENT_TYPE = "application/zip"
ALLOWED_ARCHIVE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024   # 5 GB
MAX_ZIP_BYTES = 500 * 1024 * 1024            # 500 MB


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_uuid_filename(original_filename: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
        suffix = ".jpg"
    return f"{uuid4().hex}{suffix}"


def generate_filename(username: str, process_type: str, extension: str) -> str:
    """
    Generate a deterministic, human-readable filename.

    Format:  {username}-{process_type}-{YYYYMMDD}-{HHMMSS}{ext}

    Examples:
        sandy-upload-20260310-103000.tif
        sandy-detection-annotated-20260310-103000.jpg
        sandy-report-20260310-103000.pdf
        sandy-odm-20260310-103000.tif
    """
    username_safe = (username or "user").strip().lower().replace(" ", "-")
    process_safe = process_type.strip().lower().replace(" ", "-")
    if not extension.startswith("."):
        extension = f".{extension}"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{username_safe}-{process_safe}-{timestamp}{extension.lower()}"


def atomic_write_bytes(dst_path: str, content: bytes) -> None:
    """Write bytes atomically via a temp file to avoid partial writes."""
    dst = Path(dst_path)
    tmp = dst.with_suffix(dst.suffix + f".{uuid4().hex}.tmp")
    ensure_dir(str(dst.parent))
    tmp.write_bytes(content)
    os.replace(tmp, dst)


async def read_upload_validated(file: UploadFile) -> bytes:
    """Read and validate an image UploadFile (legacy helper, kept for compatibility)."""
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


def validate_zip_file(content: bytes, content_type: str | None) -> None:
    """Validate an in-memory ZIP (legacy helper, kept for compatibility)."""
    if content_type and content_type != ALLOWED_ZIP_CONTENT_TYPE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a ZIP archive")
    if len(content) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="ZIP file too large")
    if not content or not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or empty ZIP file")


def extract_zip_images_to_dir(zip_content: bytes, dest_dir: str) -> list[str]:
    """Extract images from an in-memory ZIP (legacy helper, kept for compatibility)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            base = Path(name).name
            if not base:
                continue
            suffix = Path(base).suffix.lower()
            if suffix not in ALLOWED_ARCHIVE_IMAGE_EXTENSIONS:
                continue
            safe_name = base
            out_path = dest / safe_name
            if out_path.resolve().parent != dest.resolve():
                continue
            data = zf.read(name)
            if not data:
                continue
            out_path.write_bytes(data)
            extracted.append(safe_name)
    return extracted


def extract_zip_images_from_disk(zip_path: str, dest_dir: str) -> list[str]:
    """
    Extract image files (.jpg/.jpeg/.png) from a ZIP already on disk.

    Unlike extract_zip_images_to_dir(), this function reads from a file
    path — the ZIP is never fully loaded into memory.  This is the
    recommended function for production use with large ZIP archives.

    Args:
        zip_path:  Absolute path to the ZIP file on disk.
        dest_dir:  Directory where images will be extracted.

    Returns:
        List of extracted filenames (basenames only, no subdirectory paths).
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            base = Path(name).name
            if not base:
                continue
            suffix = Path(base).suffix.lower()
            if suffix not in ALLOWED_ARCHIVE_IMAGE_EXTENSIONS:
                continue

            # Guard against path traversal
            out_path = dest / base
            if out_path.resolve().parent != dest.resolve():
                continue

            # Stream member directly from ZIP to disk — no full decompression in RAM
            with zf.open(name) as src, open(out_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    dst.write(chunk)

            extracted.append(base)

    return extracted
