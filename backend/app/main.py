from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .clients.capwages import CapWagesClient
from .clients.nhl import NHLClient
from .config import get_settings
from .errors import MissingConfigurationError
from .errors import UpstreamRequestError
from .models import ApiErrorResponse
from .models import AskQuestionRequest
from .models import AskQuestionResponse
from .models import AskQuestionSupportData
from .models import OrchestratorDiagnosticsResponse
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
allowed_frontend_origins = list(
    dict.fromkeys(
        [
            settings.frontend_origin,
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Phase 6 backend API surface with Responses API orchestration over deterministic backend tools for HockeyOps AI.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "message": "Phase 6 backend API is running.",
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
        "ask_route_enabled": True,
    }


@app.get(
    "/api/diagnostics/orchestrator",
    response_model=OrchestratorDiagnosticsResponse,
)
async def orchestrator_diagnostics() -> OrchestratorDiagnosticsResponse:
    return OrchestratorDiagnosticsResponse(
        app_version=settings.app_version,
        openai_model=settings.openai_model,
        openai_configured=bool(settings.openai_api_key),
        openai_max_tool_rounds=settings.openai_max_tool_rounds,
        openai_max_output_tokens=settings.openai_max_output_tokens,
    )


@app.post(
    "/api/ask",
    response_model=AskQuestionResponse,
    responses={
        502: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def ask_question(payload: AskQuestionRequest) -> AskQuestionResponse:
    orchestrator: HockeyOpsOrchestrator = app.state.hockeyops_orchestrator

    try:
        result = await orchestrator.answer_question(payload.question)
    except MissingConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except UpstreamRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return AskQuestionResponse(
        question=payload.question,
        answer_text=result.answer_text,
        limitations=result.limitations,
        support_data=AskQuestionSupportData(tool_invocations=result.tool_invocations),
        model=result.model,
        response_id=result.response_id,
    )
