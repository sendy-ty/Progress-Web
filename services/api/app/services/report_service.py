"""
PDF report generation service.

Report contents (full spec):
  Page 1
  ├── Title:  "Durian Tree Detection Report"
  ├── User:   username + email
  ├── Image:  original filename + upload timestamp
  ├── Model:  AI model version used for detection
  ├── Summary: total trees detected
  ├── Section: Orthomosaic Preview (downscaled thumbnail — never full TIFF)
  └── Section: Annotated Detection Image (bboxes drawn on preview)
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Detection, Image, User
from app.services.annotated_service import get_or_create_annotated_url
from app.services.image_service import build_public_report_url
from app.utils.annotate_image import create_thumbnail
from app.utils.file_utils import generate_filename

# Max width for images embedded in the PDF (avoids huge in-memory PIL decode)
_PDF_THUMB_MAX_WIDTH = 1200


def _make_thumb_for_pdf(src_path: str, suffix: str = ".jpg") -> str | None:
    """
    Create a temporary JPEG thumbnail of `src_path` for embedding in the PDF.
    Returns the temp file path, or None if the source file can't be opened.
    The caller must delete the temp file when done.
    """
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        create_thumbnail(src_path, tmp.name, max_width=_PDF_THUMB_MAX_WIDTH)
        return tmp.name
    except Exception:
        return None


def _draw_section_header(c: canvas.Canvas, x: float, y: float, text: str) -> None:
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#2d6a4f"))
    c.drawString(x, y, text)
    c.setFillColor(colors.black)


def _draw_divider(c: canvas.Canvas, y: float, page_w: float, margin: float) -> None:
    c.setStrokeColor(colors.HexColor("#b7e4c7"))
    c.setLineWidth(0.5)
    c.line(margin, y, page_w - margin, y)
    c.setStrokeColor(colors.black)


def generate_pdf_report(*, db: Session, user: User, image_id: int) -> str:
    """
    Generate a structured PDF detection report and return its public URL.
    """
    img = db.get(Image, image_id)
    if not img or img.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    det = (
        db.execute(
            select(Detection)
            .where(Detection.image_id == img.id)
            .order_by(Detection.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    tree_count    = det.tree_count    if det else 0
    model_version = det.model_version if det else "N/A"

    # Ensure the annotated preview exists; generate if missing
    try:
        get_or_create_annotated_url(db=db, user=user, image_id=img.id)
    except HTTPException:
        pass  # No detections yet — annotated image will be skipped in PDF

    annotated_path = str(Path(settings.annotated_dir) / f"{img.id}.jpg")

    # ── Build output path ──────────────────────────────────────────────────
    filename = generate_filename(user.username, "report", ".pdf")
    out_path = str(Path(settings.pdf_dir) / filename)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    uploaded_at  = img.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if img.created_at else "N/A"

    # ── Create downscaled thumbnails for embedding ─────────────────────────
    # (avoids loading a multi-GB TIFF raw into reportlab's image reader)
    ortho_thumb   = _make_thumb_for_pdf(img.file_path)     if os.path.isfile(img.file_path)  else None
    annot_thumb   = _make_thumb_for_pdf(annotated_path)   if os.path.isfile(annotated_path) else None

    tmp_files = [f for f in [ortho_thumb, annot_thumb] if f]

    try:
        _build_pdf(
            out_path=out_path,
            user=user,
            img=img,
            tree_count=tree_count,
            model_version=model_version,
            generated_at=generated_at,
            uploaded_at=uploaded_at,
            ortho_thumb=ortho_thumb,
            annot_thumb=annot_thumb,
        )
    finally:
        # Clean up temp thumbnail files regardless of success/failure
        for f in tmp_files:
            try:
                os.remove(f)
            except OSError:
                pass

    url = build_public_report_url(f"pdf/{filename}")
    return url or f"/reports/pdf/{filename}"


def _build_pdf(
    *,
    out_path: str,
    user: User,
    img: Image,
    tree_count: int,
    model_version: str,
    generated_at: str,
    uploaded_at: str,
    ortho_thumb: str | None,
    annot_thumb: str | None,
) -> None:
    """Render the PDF onto a single A4 canvas."""
    c = canvas.Canvas(out_path, pagesize=A4)
    page_w, page_h = A4
    margin = 2.0 * cm
    content_w = page_w - 2 * margin
    y = page_h - margin

    # ── Title bar ──────────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#1b4332"))
    c.rect(0, page_h - 2.8 * cm, page_w, 2.8 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(margin, page_h - 1.9 * cm, "Durian Tree Detection Report")
    c.setFont("Helvetica", 9)
    c.drawRightString(page_w - margin, page_h - 2.4 * cm, f"Generated: {generated_at}")
    c.setFillColor(colors.black)

    y = page_h - 3.4 * cm

    # ── User information ───────────────────────────────────────────────────
    _draw_section_header(c, margin, y, "User Information")
    y -= 0.5 * cm
    _draw_divider(c, y, page_w, margin)
    y -= 0.5 * cm

    c.setFont("Helvetica", 10)
    for label, value in [("Username", user.username), ("Email", getattr(user, "email", "N/A"))]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(margin + 3.5 * cm, y, str(value))
        y -= 0.55 * cm

    y -= 0.3 * cm

    # ── Image information ──────────────────────────────────────────────────
    _draw_section_header(c, margin, y, "Image Information")
    y -= 0.5 * cm
    _draw_divider(c, y, page_w, margin)
    y -= 0.5 * cm

    c.setFont("Helvetica", 10)
    for label, value in [
        ("Filename",       img.original_filename),
        ("Upload time",    uploaded_at),
        ("File size",      f"{img.file_size_bytes / (1024**2):.1f} MB" if img.file_size_bytes else "N/A"),
    ]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(margin + 3.5 * cm, y, str(value))
        y -= 0.55 * cm

    y -= 0.3 * cm

    # ── Detection summary ──────────────────────────────────────────────────
    _draw_section_header(c, margin, y, "Detection Summary")
    y -= 0.5 * cm
    _draw_divider(c, y, page_w, margin)
    y -= 0.5 * cm

    for label, value in [
        ("Total trees detected", str(tree_count)),
        ("AI model version",     model_version),
    ]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(margin + 4.5 * cm, y, str(value))
        y -= 0.55 * cm

    y -= 0.5 * cm

    img_box_h = 7.5 * cm

    # ── Orthomosaic preview ────────────────────────────────────────────────
    if ortho_thumb and os.path.isfile(ortho_thumb):
        _draw_section_header(c, margin, y, "Orthomosaic Preview")
        y -= 0.4 * cm
        _draw_divider(c, y, page_w, margin)
        y -= 0.4 * cm
        c.drawImage(
            ortho_thumb,
            margin, y - img_box_h,
            width=content_w,
            height=img_box_h,
            preserveAspectRatio=True,
            anchor="sw",
        )
        y -= img_box_h + 0.8 * cm

    # ── Annotated detection image ──────────────────────────────────────────
    if annot_thumb and os.path.isfile(annot_thumb):
        _draw_section_header(c, margin, y, "Annotated Detection Image")
        y -= 0.4 * cm
        _draw_divider(c, y, page_w, margin)
        y -= 0.4 * cm
        c.drawImage(
            annot_thumb,
            margin, y - img_box_h,
            width=content_w,
            height=img_box_h,
            preserveAspectRatio=True,
            anchor="sw",
        )

    c.showPage()
    c.save()
