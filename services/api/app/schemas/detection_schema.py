from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DetectionItem(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0, examples=[0.91])
    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        examples=[[120, 200, 340, 400]],
        description="Bounding box in xyxy pixel coordinates: [x1,y1,x2,y2]",
    )
    tree_type: str = Field(default="durian", examples=["durian"])


class DetectionRunResponse(BaseModel):
    tree_count: int
    detections: list[DetectionItem]
    annotated_image_base64: str | None = Field(default=None, description="Annotated image as base64 JPEG (optional)")


class DetectionRecord(BaseModel):
    id: int
    image_id: int
    confidence: float
    bbox: list[float]
    tree_type: str
    created_at: datetime

    class Config:
        from_attributes = True

