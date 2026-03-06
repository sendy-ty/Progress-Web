from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database.models import Detection, Image, User


def summary(*, db: Session) -> dict:
    total_users = db.execute(select(func.count(User.id))).scalar_one()
    total_images = db.execute(select(func.count()).select_from(Image)).scalar_one()

    total_detections = db.execute(select(func.count()).select_from(Detection)).scalar_one()
    avg_conf = db.execute(select(func.avg(Detection.confidence))).scalar_one()

    return {
        "total_users": int(total_users),
        "total_images": int(total_images),
        "total_durian_trees_detected": int(total_detections),
        "average_detection_confidence": float(avg_conf) if avg_conf is not None else None,
    }


def trends(*, db: Session, days: int) -> list[dict]:
    # Group by date in DB timezone; for analytics this is fine.
    rows = (
        db.execute(
            select(
                func.date(Detection.created_at).label("date"),
                func.count(Detection.id).label("total_detections"),
            )
            .where(Detection.created_at >= func.now() - text(f"INTERVAL '{int(days)} days'"))
            .group_by(func.date(Detection.created_at))
            .order_by(func.date(Detection.created_at))
        )
        .all()
    )

    # Also include tree totals (= detections count) for now
    return [
        {
            "date": str(r.date),
            "total_detections": int(r.total_detections),
            "total_trees": int(r.total_detections),
        }
        for r in rows
    ]


def latest_images(*, db: Session, user: User, limit: int) -> list[dict]:
    imgs = (
        db.execute(select(Image).where(Image.user_id == user.id).order_by(Image.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )

    # N+1 is okay at small sizes; keep simple. Can be optimized with a grouped query later.
    out: list[dict] = []
    for img in imgs:
        tree_count = db.execute(select(func.count()).select_from(Detection).where(Detection.image_id == img.id)).scalar_one()
        out.append(
            {
                "image_id": img.id,
                "created_at": img.created_at.isoformat(),
                "original_filename": img.original_filename,
                "tree_count": int(tree_count),
            }
        )
    return out

