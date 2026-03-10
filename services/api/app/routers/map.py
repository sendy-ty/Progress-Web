"""
Map API endpoints.

GET /map/durian-trees              → GeoJSON (placeholder until geo-referencing is added)
GET /map/orthomosaic/{image_id}    → Orthomosaic metadata + tile URL template
POST /map/tiles/{image_id}         → Trigger manuel tile generation for any image
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.common import Envelope
from app.services.image_service import build_public_url, get_image
from app.utils.responses import success

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/durian-trees", summary="GeoJSON of detected durian trees (placeholder)")
async def durian_trees(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    # Geo-referencing requires per-detection lat/lon which is not yet implemented.
    # Returns an empty FeatureCollection until that pipeline is added.
    return {"type": "FeatureCollection", "features": []}


@router.get(
    "/orthomosaic/{image_id}",
    response_model=Envelope[dict],
    summary="Get orthomosaic metadata, public URL, and tile endpoint for map display",
)
async def orthomosaic_info(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """
    Returns everything a frontend map viewer needs to display an orthomosaic:

    - image metadata (id, filename, size, upload time)
    - public orthomosaic URL (served by NGINX, direct file download)
    - tile URL template for XYZ slippy-map display: {z}/{x}/{y}.png
    - tile availability status and zoom range

    If tiles have not been generated yet, trigger generation via:
        POST /map/tiles/{image_id}
    """
    img = get_image(db=db, user=user, image_id=image_id)

    from app.services.tile_service import get_tile_metadata
    tiles = get_tile_metadata(image_id=image_id)

    orthomosaic_url = build_public_url(img.stored_filename)

    payload = {
        # Image metadata
        "image_id":          img.id,
        "filename":          img.original_filename,
        "stored_filename":   img.stored_filename,
        "content_type":      img.content_type,
        "file_size_bytes":   img.file_size_bytes,
        "uploaded_at":       img.created_at.isoformat(),

        # Direct file access
        "orthomosaic_url":   orthomosaic_url,

        # Tile pyramid for slippy-map viewers (Leaflet / MapLibre / OpenLayers)
        "tiles":             tiles,
    }

    return success(payload)


@router.post(
    "/tiles/{image_id}",
    response_model=Envelope[dict],
    summary="Trigger tile generation for an uploaded orthomosaic (Celery task)",
)
async def trigger_tiles(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """
    Enqueue a Celery task to generate XYZ tiles for `image_id`.
    Returns immediately with a task_id for status polling.

    Use GET /detection/status/{task_id} to monitor progress.
    Once complete, GET /map/orthomosaic/{image_id} will include tile URLs.
    """
    img = get_image(db=db, user=user, image_id=image_id)

    from app.services.tile_service import tiles_exist
    if tiles_exist(image_id):
        from app.services.tile_service import get_tile_metadata
        return success(
            {"image_id": image_id, "status": "already_exists", **get_tile_metadata(image_id)},
            "Tiles already generated",
        )

    from app.services.tasks import generate_tiles
    task = generate_tiles.delay(image_id=image_id, image_path=img.file_path)

    return success(
        {"image_id": image_id, "task_id": task.id, "status": "queued"},
        "Tile generation queued",
    )
