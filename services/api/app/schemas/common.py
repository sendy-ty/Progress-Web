from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    status: str = Field(examples=["success"])
    data: T | None = None
    message: str = Field(default="", examples=[""])

