from __future__ import annotations

from typing import Any

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from app.core.config import settings


class YoloClient:
    """
    HTTP client for the ai-yolo inference service.

    Key behaviour: the image file is streamed directly from disk via an
    open file handle using requests_toolbelt.MultipartEncoder — the full image 
    is never loaded into the API process memory.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._url = str(base_url or settings.yolo_url)

    def detect(
        self,
        *,
        filename: str,
        file_path: str,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Stream image from disk to YOLO service.

        Args:
            filename:     Original filename (used as the multipart part name).
            file_path:    Absolute path to the image on disk.
            content_type: MIME type, e.g. "image/tiff".

        Returns:
            Dict with keys: tree_count (int), detections (list), model_version (str).
        """
        with open(file_path, "rb") as fobj:
            encoder = MultipartEncoder(
                fields={
                    "file": (filename, fobj, content_type or "application/octet-stream")
                }
            )
            resp = requests.post(
                self._url,
                data=encoder,
                headers={"Content-Type": encoder.content_type},
                timeout=settings.yolo_timeout_seconds,
            )
        resp.raise_for_status()
        data = resp.json()
        if "tree_count" not in data or "detections" not in data:
            raise ValueError("Invalid YOLO response: missing 'tree_count' or 'detections'")
        return data
