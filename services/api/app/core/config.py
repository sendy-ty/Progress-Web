from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Durian Tree Counter API"
    app_version: str = "4.0.0"
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

    # YOLO service
    yolo_url: AnyHttpUrl = "http://ai-yolo:5000/infer"
    yolo_timeout_seconds: int = 180

    # Public URLs (optional)
    public_upload_base_url: str | None = None


settings = Settings()

