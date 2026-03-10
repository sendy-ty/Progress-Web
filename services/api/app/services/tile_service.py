"""
Orthomosaic tile generation service — GDAL backend.

Uses gdal2tiles.py (CLI tool shipped with gdal-bin) to generate a proper
XYZ/TMS-compatible PNG tile pyramid from any TIFF, GeoTIFF, or JPEG input.

Zoom levels:  0–14 (configurable via TILE_MIN_ZOOM / TILE_MAX_ZOOM settings)
Tile format:  256×256 PNG
Storage:      data/reports/tiles/{image_id}/{z}/{x}/{y}.png
NGINX URL:    /reports/tiles/{image_id}/{z}/{x}/{y}.png

If gdal2tiles is not found, falls back to the PIL-based generator so that
development environments without GDAL installed still work.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.services.image_service import build_public_report_url
from app.utils.logging import get_logger

logger = get_logger(__name__)

TILE_SIZE = 256


def _tile_base_dir(image_id: int) -> Path:
    return Path(settings.tiles_dir) / str(image_id)


def tiles_exist(image_id: int) -> bool:
    """Return True if tiles were already generated (z=0 tile present)."""
    return (_tile_base_dir(image_id) / "0" / "0" / "0.png").exists()


def _gdal2tiles_available() -> bool:
    """Check whether gdal2tiles.py is on the PATH."""
    return shutil.which("gdal2tiles.py") is not None or shutil.which("gdal2tiles") is not None


def _gdal2tiles_cmd() -> str:
    """Return the correct gdal2tiles command name."""
    return "gdal2tiles.py" if shutil.which("gdal2tiles.py") else "gdal2tiles"


def _generate_tiles_gdal(image_id: int, image_path: str) -> str:
    """
    Generate tiles using gdal2tiles.py.

    gdal2tiles produces a proper TMS tile pyramid with:
    - Correct geographic projection handling for GeoTIFFs
    - Native zoom-level selection based on image resolution
    - Alpha-channel transparency support
    - Parallel tile writing (--processes flag)
    """
    base_dir = _tile_base_dir(image_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    min_zoom = getattr(settings, "tile_min_zoom", 0)
    max_zoom = getattr(settings, "tile_max_zoom", 14)

    cmd = [
        _gdal2tiles_cmd(),
        "-p", "mercator",
        "-z", f"{min_zoom}-{max_zoom}",
        image_path,
        str(base_dir),
    ]

    logger.info(
        "Starting GDAL tile generation",
        extra={"event": "tile_generation_started", "image_id": image_id, "cmd": " ".join(cmd)},
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,   # 30-minute cap for huge TIFFs
    )

    if result.returncode != 0:
        logger.error(
            "gdal2tiles failed",
            extra={"event": "tile_generation_failed", "image_id": image_id, "stderr": result.stderr[:500]},
        )
        raise RuntimeError(f"gdal2tiles failed for image {image_id}: {result.stderr[:300]}")

    logger.info(
        "GDAL tile generation complete",
        extra={"event": "tile_generation_completed", "image_id": image_id},
    )
    return str(base_dir)


def _generate_tiles_pil(image_id: int, image_path: str) -> str:
    """
    PIL fallback tile generator (used when GDAL is not available).
    Produces visual-only tiles — not geo-referenced.
    """
    import math
    from PIL import Image

    base_dir = _tile_base_dir(image_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    MAX_ZOOM_PIL = 4

    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    orig_w, orig_h = img.size
    natural_max = math.ceil(math.log2(max(orig_w, orig_h) / TILE_SIZE)) if max(orig_w, orig_h) > TILE_SIZE else 0
    max_zoom = min(natural_max, MAX_ZOOM_PIL)

    for z in range(0, max_zoom + 1):
        grid = 2 ** z
        zoom_px = grid * TILE_SIZE
        zoom_img = img.resize((zoom_px, zoom_px), Image.LANCZOS)

        for x in range(grid):
            x_dir = base_dir / str(z) / str(x)
            x_dir.mkdir(parents=True, exist_ok=True)
            for y in range(grid):
                tile = zoom_img.crop((x * TILE_SIZE, y * TILE_SIZE, (x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE))
                tile.save(x_dir / f"{y}.png", format="PNG", optimize=True)

    logger.warning(
        "PIL tile generation used (GDAL not available) — tiles are not geo-referenced",
        extra={"event": "tile_generation_pil_fallback", "image_id": image_id},
    )
    return str(base_dir)


def generate_tiles(image_id: int, image_path: str) -> str:
    """
    Generate XYZ tile pyramid. Uses GDAL when available, falls back to PIL.

    Args:
        image_id:    DB Image.id used as the tile directory name.
        image_path:  Absolute path to the source TIFF/JPG on disk.

    Returns:
        Absolute path to the tile base directory.
    """
    if tiles_exist(image_id):
        logger.info(
            "Tiles already exist, skipping regeneration",
            extra={"event": "tile_generation_skipped", "image_id": image_id},
        )
        return str(_tile_base_dir(image_id))

    if _gdal2tiles_available():
        return _generate_tiles_gdal(image_id, image_path)
    else:
        logger.warning("gdal2tiles not found — using PIL fallback", extra={"image_id": image_id})
        return _generate_tiles_pil(image_id, image_path)


def get_tile_url_template(image_id: int) -> str | None:
    if not tiles_exist(image_id):
        return None
    base = build_public_report_url(f"tiles/{image_id}/{{z}}/{{x}}/{{y}}.png")
    if not base:
        return f"/reports/tiles/{image_id}/{{z}}/{{x}}/{{y}}.png"
    return base


def get_tile_metadata(image_id: int) -> dict:
    if not tiles_exist(image_id):
        return {"available": False, "tile_url": None, "min_zoom": None, "max_zoom": None}

    base_dir = _tile_base_dir(image_id)
    zoom_dirs = [int(p.name) for p in base_dir.iterdir() if p.is_dir() and p.name.isdigit()]
    actual_max = max(zoom_dirs) if zoom_dirs else 0

    return {
        "available": True,
        "tile_url": get_tile_url_template(image_id),
        "min_zoom": 0,
        "max_zoom": actual_max,
        "tile_size": TILE_SIZE,
    }
