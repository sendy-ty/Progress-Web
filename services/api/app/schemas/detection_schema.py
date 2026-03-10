from __future__ import annotations

from pydantic import BaseModel, Field


class DetectionItem(BaseModel):
    """Single detection: bounding box only. Confidence scores are never returned."""

    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        examples=[[120, 200, 340, 400]],
        description="Bounding box in xyxy pixel coordinates: [x1, y1, x2, y2]",
    )


class DetectionRunResponse(BaseModel):
    tree_count: int
    detections: list[DetectionItem]


class AsyncTaskResponse(BaseModel):
    """Response for async (Celery-queued) operations."""
    task_id: str
    status: str = Field(description="queued | processing | completed | failed")
