from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    images: Mapped[list["Image"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="images")
    detections: Mapped[list["Detection"]] = relationship(back_populates="image", cascade="all, delete-orphan")


class Detection(Base):
    """One row per detection run (per image). bboxes: list of [x1,y1,x2,y2]. No confidence scores stored."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), index=True, nullable=False)
    tree_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bboxes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # [[x1,y1,x2,y2], ...]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    image: Mapped[Image] = relationship(back_populates="detections")


class OdmProject(Base):
    __tablename__ = "odm_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="pending")
    result_path: Mapped[str | None] = mapped_column(Text)

    # After ODM completes, the orthomosaic TIFF is registered as an Image record.
    # This FK lets users feed the ODM output directly into the YOLO detection pipeline.
    odm_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    odm_image: Mapped["Image | None"] = relationship("Image", foreign_keys=[odm_image_id])
