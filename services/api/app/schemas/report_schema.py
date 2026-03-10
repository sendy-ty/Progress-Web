from __future__ import annotations

from pydantic import BaseModel


class ReportGenerateResponse(BaseModel):
    report_url: str

