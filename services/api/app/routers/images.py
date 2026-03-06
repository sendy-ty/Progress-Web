from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.image_schema import ImagePublic
from app.schemas.common import Envelope
from app.services.image_service import build_public_url, delete_image, get_image, list_images, save_upload
from app.utils.file_utils import read_upload_validated
from app.utils.responses import success


router = APIRouter(prefix="/images", tags=["images"])


@router.post("/upload", response_model=Envelope[ImagePublic], summary="Upload an image")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    content = await read_upload_validated(file)
    img = save_upload(db=db, user=user, original_filename=file.filename, content_type=file.content_type, content=content)
    public = ImagePublic.model_validate(img).model_dump()
    public["url"] = build_public_url(img.stored_filename)
    return success(public, "Image uploaded")


@router.get("", response_model=Envelope[list[ImagePublic]], summary="List images")
def images(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    imgs = list_images(db=db, user=user, limit=limit, offset=offset)
    data = []
    for img in imgs:
        item = ImagePublic.model_validate(img).model_dump()
        item["url"] = build_public_url(img.stored_filename)
        data.append(item)
    return success(data)


@router.get("/{image_id}", response_model=Envelope[ImagePublic], summary="Get image metadata")
def image_detail(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    img = get_image(db=db, user=user, image_id=image_id)
    item = ImagePublic.model_validate(img).model_dump()
    item["url"] = build_public_url(img.stored_filename)
    return success(item)


@router.delete("/{image_id}", response_model=Envelope[dict], summary="Delete an image")
def image_delete(
    image_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    delete_image(db=db, user=user, image_id=image_id)
    return success({}, "Image deleted")

