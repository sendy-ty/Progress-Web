from __future__ import annotations

from typing import Any

import requests

from app.core.config import settings


class YoloClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._url = str(base_url or settings.yolo_url)

    def infer(self, *, filename: str, content: bytes, content_type: str | None) -> dict[str, Any]:
        resp = requests.post(
            self._url,
            files={"file": (filename, content, content_type or "application/octet-stream")},
            timeout=settings.yolo_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if "tree_count" not in data or "detections" not in data:
            raise ValueError("Invalid YOLO response")
        return data

