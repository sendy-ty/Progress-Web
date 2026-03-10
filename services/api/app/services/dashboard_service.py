from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database.models import Detection, Image, User


def summary(*, db: Session) -> dict:
    total_users = db.execute(select(func.count(User.id))).scalar_one()
    total_images = db.execute(select(func.count()).select_from(Image)).scalar_one()
    total_trees = db.execute(select(func.coalesce(func.sum(Detection.tree_count), 0)).select_from(Detection)).scalar_one()

    return {
        "total_users": int(total_users),
        "total_images": int(total_images),
        "total_durian_trees_detected": int(total_trees),
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

    # N+1 is okay at small sizes; use latest detection run's tree_count per image.
    out: list[dict] = []
    for img in imgs:
        row = (
            db.execute(
                select(Detection.tree_count)
                .where(Detection.image_id == img.id)
                .order_by(Detection.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        tree_count = row[0] if row else 0
        out.append(
            {
                "image_id": img.id,
                "created_at": img.created_at.isoformat(),
                "original_filename": img.original_filename,
                "tree_count": int(tree_count),
            }
        )
    return out

