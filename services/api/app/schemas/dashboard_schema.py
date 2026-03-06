from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_users: int
    total_images: int
    total_durian_trees_detected: int
    average_detection_confidence: float | None


class TrendItem(BaseModel):
    date: str
    total_detections: int
    total_trees: int


class LatestImageItem(BaseModel):
    image_id: int
    created_at: str
    original_filename: str
    tree_count: int

