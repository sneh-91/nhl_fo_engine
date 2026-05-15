from __future__ import annotations

from collections.abc import Mapping

import httpx

from ..config import Settings
from ..errors import MissingConfigurationError, UpstreamRequestError


class CapWagesClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.capwages_api_key
        self._client = httpx.AsyncClient(
            base_url=str(settings.capwages_api_base_url),
            timeout=settings.source_request_timeout_seconds,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise MissingConfigurationError(
                "CAPWAGES_API_KEY is missing. Add it to the root .env before using CapWages."
            )
        return {"Authorization": f"ApiKey {self._api_key}"}

    async def _get(self, path: str, params: Mapping[str, str] | None = None) -> dict:
        try:
            response = await self._client.get(path, params=params, headers=self._headers())
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise UpstreamRequestError(
                source="CapWages API",
                path=path,
                status_code=error.response.status_code,
                message=error.response.text,
            ) from error
        except httpx.RequestError as error:
            raise UpstreamRequestError(
                source="CapWages API",
                path=path,
                message=str(error),
            ) from error

        return response.json()

    async def get_players(self, *, page: int = 1, limit: int = 25) -> dict:
        params = {"page": str(page), "limit": str(limit)}
        return await self._get("players", params=params)

    async def get_player_detail(self, slug: str) -> dict:
        return await self._get(f"players/{slug}")
