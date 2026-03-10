from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ImagePublic(BaseModel):
    id: int
    original_filename: str
    stored_filename: str
    content_type: str | None
    file_size_bytes: int | None
    created_at: datetime
    url: str | None = Field(default=None, description="Public URL if configured")

    class Config:
        from_attributes = True


class AnnotatedImagePublic(BaseModel):
    image_id: int
    annotated_url: str | None = Field(default=None, description="Public URL to annotated image if available")

