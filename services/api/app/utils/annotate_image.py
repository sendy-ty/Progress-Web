"""
Annotated image generation utility.

Memory strategy for large orthomosaics
---------------------------------------
A 5 GB TIFF loaded at full resolution would exhaust RAM. Instead:
1. The image is opened lazily via PIL (defers pixel access).
2. If the width exceeds `MAX_PREVIEW_WIDTH`, the image is downscaled
   proportionally before any pixel data is decoded into RAM.
3. Bounding-box coordinates from YOLO (in original-image pixel space)
   are scaled to match the preview dimensions.
4. The result is saved as JPEG — the original TIFF is never modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw

# Hard cap for preview width.  Overridable at call sites via `max_width`.
MAX_PREVIEW_WIDTH: int = 3000


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _open_preview(image_path: str, max_width: int = MAX_PREVIEW_WIDTH) -> Tuple[Image.Image, float]:
    """
    Open an image from disk and downscale it to at most `max_width` pixels wide.

    For large TIFFs PIL uses lazy loading — the full pixel array is not
    decoded until a pixel-consuming operation is performed.  By calling
    `resize()` we control exactly how much data is held in memory.

    Returns:
        (preview_image, scale_factor)
        scale_factor < 1.0 means the image was shrunk; 1.0 means unchanged.
    """
    img = Image.open(image_path)

    # Convert to RGB (handles palette, RGBA, multi-band TIFF → single 3-band)
    if img.mode != "RGB":
        img = img.convert("RGB")

    orig_w, orig_h = img.size
    if orig_w > max_width:
        scale = max_width / orig_w
        new_w = max_width
        new_h = int(orig_h * scale)
        # LANCZOS gives the sharpest downscale; releases the full-res buffer afterwards
        img = img.resize((new_w, new_h), Image.LANCZOS)
    else:
        scale = 1.0

    return img, scale


def draw_detections(
    *,
    image_path: str,
    detections: list[dict],
    output_path: str,
    max_width: int = MAX_PREVIEW_WIDTH,
) -> None:
    """
    Draw bounding boxes on a downscaled preview and save as JPEG.

    Args:
        image_path:  Absolute path to the source orthomosaic (TIFF/JPG/PNG).
        detections:  List of {"bbox": [x1, y1, x2, y2]} in original pixel coords.
        output_path: Destination path for the annotated preview JPEG.
        max_width:   Preview width cap in pixels (default 3000).

    The original image at `image_path` is never modified.
    """
    preview, scale = _open_preview(image_path, max_width=max_width)
    draw = ImageDraw.Draw(preview)
    pw, ph = preview.size

    # Box thickness scales proportionally with preview size
    box_width = max(2, int(3 * scale)) if scale < 1.0 else 3

    for det in detections:
        bbox = det.get("bbox") if isinstance(det, dict) else det
        if not bbox or len(bbox) != 4:
            continue

        # Scale original-space coords to preview-space coords
        x1, y1, x2, y2 = [float(v) * scale for v in bbox]
        x1 = _clamp(x1, 0, pw)
        x2 = _clamp(x2, 0, pw)
        y1 = _clamp(y1, 0, ph)
        y2 = _clamp(y2, 0, ph)

        draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=box_width)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, format="JPEG", quality=90)


def create_thumbnail(
    image_path: str,
    output_path: str,
    max_width: int = MAX_PREVIEW_WIDTH,
) -> str:
    """
    Create a plain (no bboxes) downscaled JPEG thumbnail of any image.
    Used by the PDF report to embed a preview of the orthomosaic
    without loading the full TIFF into memory.

    Returns output_path for convenience.
    """
    preview, _ = _open_preview(image_path, max_width=max_width)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, format="JPEG", quality=85)
    return output_path
