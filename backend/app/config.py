from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    app_name: str = "HockeyOps AI"
    app_version: str = "0.5.0-phase6"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    nhl_api_base_url: HttpUrl = "https://api-web.nhle.com/v1/"
    capwages_api_base_url: HttpUrl = "https://capwages.com/api/gateway/v1/"
    source_request_timeout_seconds: float = 20.0
    max_parallel_source_requests: int = 8
    roster_cache_ttl_seconds: int = 900
    player_cache_ttl_seconds: int = 900
    nhl_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
    nhl_referer: str = "https://www.nhl.com/"
    nhl_origin: str = "https://www.nhl.com"
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = "gpt-5.4-mini"
    openai_reasoning_effort: str | None = None
    openai_max_tool_rounds: int = 8
    openai_max_output_tokens: int = 2000
    capwages_api_key: str | None = Field(default=None, alias="CAPWAGES_API_KEY")

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
