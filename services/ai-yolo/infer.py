from fastapi import FastAPI, UploadFile, File
from ultralytics import YOLO
from PIL import Image
import io
import base64
from typing import Any

app = FastAPI()

model = YOLO("models/best-durian-seg.pt")

@app.post("/infer")
async def infer_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    results = model(image)

    boxes = results[0].boxes
    count = len(boxes)

    detections: list[dict[str, Any]] = []
    if count:
        xyxy = boxes.xyxy.cpu().tolist()
        confs = boxes.conf.cpu().tolist() if boxes.conf is not None else [0.0] * count
        for bb, cf in zip(xyxy, confs):
            detections.append(
                {
                    "confidence": float(cf),
                    "bbox": [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])],
                    "tree_type": "durian",
                }
            )

    plotted = results[0].plot()

    result_image = Image.fromarray(plotted)

    buffer = io.BytesIO()
    result_image.save(buffer, format="JPEG")
    buffer.seek(0)

    img_base64 = base64.b64encode(buffer.read()).decode("utf-8")

    return {
        "tree_count": count,
        "detections": detections,
        "annotated_image": img_base64,
    }
