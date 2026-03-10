from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Durian Tree Counter API"
    app_version: str = "5.0.0"
    cors_allow_origins: str = "*"

    # Security
    jwt_secret_key: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database
    database_url: str = "postgresql+psycopg2://webcount:webcount@postgres:5432/webcount"
    auto_create_db: bool = True

    # Storage
    upload_dir: str = "/app/data/uploads"
    reports_dir: str = "/app/data/reports"
    annotated_dir: str = "/app/data/reports/annotated"
    pdf_dir: str = "/app/data/reports/pdf"
    orthomosaic_dir: str = "/app/data/reports/orthomosaic"
    # Tiles served by NGINX at /reports/tiles/{image_id}/{z}/{x}/{y}.png
    tiles_dir: str = "/app/data/reports/tiles"
    # Max width (px) for annotated preview — avoids loading full-res TIFF into RAM
    annotated_preview_max_width: int = 3000
    # Tile zoom range for gdal2tiles (0=world overview, 14=street level detail)
    tile_min_zoom: int = 0
    tile_max_zoom: int = 14

    # ODM — projects stored under data/odm/projects/{project_id}/
    odm_base_dir: str = "/app/data/odm"
    odm_projects_dir: str = "/app/data/odm/projects"

    # Host paths (only needed when API triggers docker via docker.sock)
    host_project_dir: str | None = None

    # YOLO service (ai-yolo container)
    yolo_url: AnyHttpUrl = "http://ai-yolo:8001/detect"
    yolo_timeout_seconds: int = 180

    # Celery / Redis
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # Public URLs (served by NGINX)
    public_upload_base_url: str | None = None
    public_reports_base_url: str | None = None


settings = Settings()
