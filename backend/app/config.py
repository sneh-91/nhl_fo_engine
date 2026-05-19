from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
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
    moneypuck_enabled: bool = Field(default=True, alias="MONEYPUCK_ENABLED")
    moneypuck_2025_regular_skaters_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_regular" / "skaters.csv",
        alias="MONEYPUCK_2025_REGULAR_SKATERS_PATH",
    )
    moneypuck_2025_regular_goalies_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_regular" / "goalies.csv",
        alias="MONEYPUCK_2025_REGULAR_GOALIES_PATH",
    )
    moneypuck_2025_regular_teams_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_regular" / "teams.csv",
        alias="MONEYPUCK_2025_REGULAR_TEAMS_PATH",
    )
    moneypuck_2025_playoff_skaters_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_playoffs" / "skaters.csv",
        alias="MONEYPUCK_2025_PLAYOFF_SKATERS_PATH",
    )
    moneypuck_2025_playoff_goalies_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_playoffs" / "goalies.csv",
        alias="MONEYPUCK_2025_PLAYOFF_GOALIES_PATH",
    )
    moneypuck_2025_playoff_teams_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "2025_playoffs" / "teams.csv",
        alias="MONEYPUCK_2025_PLAYOFF_TEAMS_PATH",
    )
    team_context_2025_26_path: Path = Field(
        default=ROOT_DIR / "data" / "moneypuck" / "team_context" / "2025-26.json",
        alias="TEAM_CONTEXT_2025_26_PATH",
    )
    moneypuck_cache_ttl_seconds: int = Field(default=900, alias="MONEYPUCK_CACHE_TTL_SECONDS")
    nhl_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
    nhl_referer: str = "https://www.nhl.com/"
    nhl_origin: str = "https://www.nhl.com"
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_answer_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_ANSWER_MODEL")
    openai_classifier_model: str = Field(default="gpt-5.4-nano", alias="OPENAI_CLASSIFIER_MODEL")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    openai_judge_model: str = Field(default="gpt-5-mini", alias="OPENAI_JUDGE_MODEL")
    openai_reasoning_effort: str | None = None
    openai_max_tool_rounds: int = 8
    openai_max_output_tokens: int = 2000
    nhl_rules_rag_enabled: bool = Field(default=True, alias="NHL_RULES_RAG_ENABLED")
    nhl_rules_chroma_path: Path = Field(
        default=ROOT_DIR / "data" / "nhl" / "vector_store" / "chroma",
        alias="NHL_RULES_CHROMA_PATH",
    )
    nhl_rules_chroma_collection: str = Field(default="nhl_rules", alias="NHL_RULES_CHROMA_COLLECTION")
    nhl_rules_top_k: int = Field(default=6, alias="NHL_RULES_TOP_K")
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
