from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.dashboard_schema import DashboardSummary, LatestImageItem, TrendItem
from app.schemas.common import Envelope
from app.services.dashboard_service import latest_images, summary, trends
from app.utils.responses import success


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=Envelope[DashboardSummary], summary="Dashboard summary")
def dashboard_summary(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    data = summary(db=db)
    DashboardSummary.model_validate(data)
    return success(data)


@router.get("/trends", response_model=Envelope[list[TrendItem]], summary="Detections trend (grouped by date)")
def dashboard_trends(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    data = trends(db=db, days=days)
    for item in data:
        TrendItem.model_validate(item)
    return success(data)


@router.get("/latest-images", response_model=Envelope[list[LatestImageItem]], summary="Latest uploaded images with tree counts")
def dashboard_latest_images(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    data = latest_images(db=db, user=user, limit=limit)
    return success(data)

