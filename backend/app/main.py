from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Phase 1 backend shell for HockeyOps AI.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "message": "Phase 1 backend shell is running.",
    }


@app.get("/api/health")
async def healthcheck() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "frontend_origin": settings.frontend_origin,
        "capwages_configured": bool(settings.capwages_api_key),
    }
