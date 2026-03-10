from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database.init_db import init_db
from app.routers import auth, dashboard, detection, health, images, map, odm, reports, tasks
from app.utils.logging import configure_logging, get_logger
from app.utils.responses import error, success

configure_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Backend API for durian tree detection from drone images. "
            "Supports orthomosaic upload (up to 5 GB), YOLO-based durian tree detection, "
            "OpenDroneMap orthomosaic generation, map tile serving, PDF reporting, and analytics."
        ),
        openapi_tags=[
            {"name": "auth",      "description": "JWT authentication — register, login, profile"},
            {"name": "images",    "description": "Orthomosaic image upload and management (TIFF/JPG/PNG, up to 5 GB)"},
            {"name": "detection", "description": "YOLO durian tree detection — async via Celery"},
            {"name": "tasks",     "description": "Universal Celery task status polling"},
            {"name": "map",       "description": "Orthomosaic tile map endpoints"},
            {"name": "odm",       "description": "OpenDroneMap orthomosaic generation from drone ZIP archives"},
            {"name": "reports",   "description": "PDF detection report generation"},
            {"name": "dashboard", "description": "Detection analytics and trends"},
            {"name": "health",    "description": "System health monitoring"},
        ],
        docs_url="/docs",
        redoc_url="/redoc",
    )

    allow_origins = (
        [o.strip() for o in settings.cors_allow_origins.split(",")]
        if settings.cors_allow_origins else ["*"]
    )
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
        logger.info("API started", extra={"event": "api_startup", "version": settings.app_version})

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(images.router)
    app.include_router(detection.router)
    app.include_router(tasks.router)
    app.include_router(map.router)
    app.include_router(odm.router)
    app.include_router(reports.router)
    app.include_router(dashboard.router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return success({"name": settings.app_name, "version": settings.app_version})

    return app


app = create_app()