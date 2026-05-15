from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .clients.capwages import CapWagesClient
from .clients.nhl import NHLClient
from .config import get_settings
from .services.normalization import PlayerNormalizer
from .services.orchestration import HockeyOpsOrchestrator
from .services.tools import PlayerToolService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.nhl_client = NHLClient(settings)
    app.state.capwages_client = CapWagesClient(settings)
    app.state.player_normalizer = PlayerNormalizer()
    app.state.player_tool_service = PlayerToolService(
        settings=settings,
        nhl_client=app.state.nhl_client,
        capwages_client=app.state.capwages_client,
        normalizer=app.state.player_normalizer,
    )
    app.state.hockeyops_orchestrator = HockeyOpsOrchestrator(
        settings=settings,
        tool_service=app.state.player_tool_service,
    )
    try:
        yield
    finally:
        await app.state.nhl_client.aclose()
        await app.state.capwages_client.aclose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Phase 5 backend shell with Responses API orchestration over deterministic backend tools for HockeyOps AI.",
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
        "message": "Phase 5 backend shell is running.",
    }


@app.get("/api/health")
async def healthcheck() -> dict[str, str | bool | float]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "frontend_origin": settings.frontend_origin,
        "nhl_api_base_url": str(settings.nhl_api_base_url),
        "capwages_api_base_url": str(settings.capwages_api_base_url),
        "source_timeout_seconds": settings.source_request_timeout_seconds,
        "openai_model": settings.openai_model,
        "openai_configured": bool(settings.openai_api_key),
        "capwages_configured": bool(settings.capwages_api_key),
    }
