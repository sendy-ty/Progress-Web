from __future__ import annotations

from app.database.models import Base
from app.database.session import engine


def init_db() -> None:
    # For production, prefer migrations (Alembic). For this project we auto-create tables
    # to keep Docker-based dev setups simple and reproducible.
    Base.metadata.create_all(bind=engine)

