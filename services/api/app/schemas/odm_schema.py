from __future__ import annotations

from pydantic import BaseModel, Field


class OdmUploadZipResponse(BaseModel):
    project_id: str = Field(description="Created ODM project UUID")
    status: str = Field(default="pending")
    image_count: int = Field(description="Number of images extracted from ZIP")


class OdmProcessResponse(BaseModel):
    project_id: str
    status: str = Field(description="queued | processing | completed | failed")
    task_id: str | None = Field(default=None, description="Celery task ID for status polling")


class OdmStatusResponse(BaseModel):
    project_id: str
    status: str = Field(description="pending | queued | processing | completed | failed")


class OdmResultResponse(BaseModel):
    project_id: str
    status: str
    orthomosaic_url: str | None = Field(
        default=None,
        description="Public URL for the orthomosaic TIFF once completed",
    )
    odm_image_id: int | None = Field(
        default=None,
        description="Image record ID for the orthomosaic — pass to POST /detection/run/{image_id}",
    )
