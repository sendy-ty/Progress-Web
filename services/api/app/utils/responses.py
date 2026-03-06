from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    status: str
    data: T | None = None
    message: str = ""


def success(data: Any = None, message: str = "") -> dict[str, Any]:
    return {"status": "success", "data": data, "message": message}


def error(message: str, data: Any = None) -> dict[str, Any]:
    return {"status": "error", "data": data, "message": message}

