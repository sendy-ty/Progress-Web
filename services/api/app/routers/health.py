from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import Envelope
from app.utils.responses import success


router = APIRouter(tags=["health"])


@router.get("/health", response_model=Envelope[dict], summary="Health check")
def health() -> dict:
    return success({"status": "ok"})

