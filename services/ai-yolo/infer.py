"""
YOLO durian tree detection service.

Memory strategy for large orthomosaics:
- Images are opened lazily via PIL from the upload file handle (no full read into RAM).
- Images wider/taller than MAX_DIM are downscaled before inference to cap memory usage.
- The original-pixel bounding boxes are reconstructed by inverting the scale factor.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from ultralytics import YOLO
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ai-yolo")

app = FastAPI(title="YOLO Durian Detection Service")

model = YOLO("models/best-durian-seg.pt")

# Maximum dimension (width or height) for inference input.
# Larger images are downscaled proportionally before being fed to the model.
MAX_DIM = 2048


async def _run_detection(file: UploadFile) -> dict[str, Any]:
    """Stream image from upload handle, downscale if needed, run YOLO."""
    try:
        # Open lazily from the SpooledTemporaryFile — avoids full-file
        # memory copy that the old `await file.read()` path caused.
        image = Image.open(file.file)

        if image.mode != "RGB":
            image = image.convert("RGB")

        original_size = image.size  # (w, h) before any resize

        # Downscale very large orthomosaics to prevent OOM
        scale = 1.0
        if max(image.size) > MAX_DIM:
            scale = MAX_DIM / max(image.size)
            image.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

        logger.info(
            "Running YOLO inference | original=%sx%s scaled=%sx%s scale=%.4f",
            original_size[0], original_size[1],
            image.size[0], image.size[1],
            scale,
        )

        results = model(image)
        boxes = results[0].boxes
        count = len(boxes)
        detections: list[dict[str, Any]] = []

        if count:
            xyxy = boxes.xyxy.cpu().tolist()
            confs = boxes.conf.cpu().tolist() if boxes.conf is not None else [0.0] * count
            for bb, cf in zip(xyxy, confs):
                # Scale bounding boxes back to original-image pixel coordinates
                detections.append(
                    {
                        "confidence": float(cf),
                        "bbox": [
                            float(bb[0]) / scale,
                            float(bb[1]) / scale,
                            float(bb[2]) / scale,
                            float(bb[3]) / scale,
                        ],
                        "tree_type": "durian",
                    }
                )

        logger.info(
            "YOLO inference complete | trees=%d detections=%d",
            count, len(detections),
        )

        return {
            "tree_count": count,
            "detections": detections,
            "model_version": "best-durian-seg",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("YOLO inference failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    """Primary endpoint: YOLO detection. Returns tree_count and detections (bbox)."""
    return await _run_detection(file)


@app.post("/infer")
async def infer_image(file: UploadFile = File(...)):
    """Legacy endpoint; aliases /detect."""
    return await _run_detection(file)


@app.get("/health")
async def health():
    return {"status": "ok"}
