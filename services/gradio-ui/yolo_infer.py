from ultralytics import YOLO
import cv2
import os
import logging
from typing import Tuple

MODEL_PATH = "models/best-durian.pt"
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

CONF_THRESHOLD = 0.5
IMG_SIZE = 1280

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

_model = None

def load_model() -> YOLO:
    global _model
    if _model is None:
        logger.info("Loading YOLO model...")
        _model = YOLO(MODEL_PATH)
        logger.info("YOLO model loaded")
    return _model

def detect_tree(image_path: str) -> Tuple[str, int]:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    model = load_model()

    results = model(
        image_path,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        verbose=False
    )

    boxes = results[0].boxes
    count = len(boxes) if boxes is not None else 0

    rendered = results[0].plot()

    output_path = os.path.join(
        OUTPUT_DIR,
        os.path.basename(image_path)
    )

    cv2.imwrite(output_path, rendered)

    return output_path, count
