from __future__ import annotations

from sqlalchemy import text

from app.database.models import Base
from app.database.session import engine


def init_db() -> None:
    # Create all tables defined in models. For production, prefer Alembic migrations.
    Base.metadata.create_all(bind=engine)

    # Additive ALTER TABLE statements for rolling upgrades on existing volumes.
    # All statements are idempotent (IF NOT EXISTS).
    with engine.begin() as conn:
        # detections: v4 → v5 schema (one row per run, bboxes JSON)
        # Step 1: add new columns if missing
        for stmt in [
            "ALTER TABLE detections ADD COLUMN IF NOT EXISTS tree_count INTEGER DEFAULT 0",
            "ALTER TABLE detections ADD COLUMN IF NOT EXISTS model_version VARCHAR(50)",
            "ALTER TABLE detections ADD COLUMN IF NOT EXISTS bboxes JSON",
        ]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # Step 2: backfill NULLs before adding NOT NULL constraints
        for stmt in [
            "UPDATE detections SET bboxes = '[]'::json WHERE bboxes IS NULL",
            "UPDATE detections SET tree_count = 0 WHERE tree_count IS NULL",
        ]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # Step 3: drop legacy columns that no longer exist in the ORM model
        for stmt in [
            "ALTER TABLE detections DROP COLUMN IF EXISTS confidence",
            "ALTER TABLE detections DROP COLUMN IF EXISTS bbox",
            "ALTER TABLE detections DROP COLUMN IF EXISTS tree_type",
            "ALTER TABLE detections DROP COLUMN IF EXISTS extra",
            "ALTER TABLE detections DROP COLUMN IF EXISTS latitude",
            "ALTER TABLE detections DROP COLUMN IF EXISTS longitude",
        ]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # odm_projects: v4 → v5 schema (user_id, result_path, odm_image_id)
        for stmt in [
            "ALTER TABLE odm_projects ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE odm_projects ADD COLUMN IF NOT EXISTS result_path TEXT",
            "ALTER TABLE odm_projects ADD COLUMN IF NOT EXISTS odm_image_id INTEGER REFERENCES images(id) ON DELETE SET NULL",
        ]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
