from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database.init_db import init_db
from app.routers import auth, dashboard, detection, health, images
from app.utils.responses import error, success


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Backend API for durian tree detection from drone images using YOLO segmentation, "
            "with authentication, uploads, detections, and analytics."
        ),
        openapi_tags=[
            {"name": "auth", "description": "Authentication (JWT)"},
            {"name": "images", "description": "Image upload and management"},
            {"name": "detection", "description": "YOLO detection integration"},
            {"name": "dashboard", "description": "Analytics endpoints"},
            {"name": "health", "description": "Health checks"},
        ],
    )

    allow_origins = [o.strip() for o in settings.cors_allow_origins.split(",")] if settings.cors_allow_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=error("Validation error", data=exc.errors()))

    @app.on_event("startup")
    def _startup() -> None:
        if settings.auto_create_db:
            init_db()

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(images.router)
    app.include_router(detection.router)
    app.include_router(dashboard.router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return success({"name": settings.app_name, "version": settings.app_version})

    return app


app = create_app()