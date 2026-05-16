from __future__ import annotations

from collections.abc import Mapping

import httpx

from ..config import Settings
from ..errors import UpstreamRequestError


class NHLClient:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            base_url=str(settings.nhl_api_base_url),
            timeout=settings.source_request_timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": settings.nhl_user_agent,
                "Referer": settings.nhl_referer,
                "Origin": settings.nhl_origin,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Mapping[str, str] | None = None) -> dict:
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise UpstreamRequestError(
                source="NHL API",
                path=path,
                status_code=error.response.status_code,
                message=error.response.text,
            ) from error
        except httpx.RequestError as error:
            raise UpstreamRequestError(
                source="NHL API",
                path=path,
                message=str(error),
            ) from error

        return response.json()

    async def get_standings(self) -> dict:
        return await self._get("standings/now")

    async def get_roster(self, team_abbrev: str) -> dict:
        return await self._get(f"roster/{team_abbrev}/current")

    async def get_player_landing(self, player_id: int) -> dict:
        return await self._get(f"player/{player_id}/landing")

    async def get_club_stats(self, team_abbrev: str) -> dict:
        return await self._get(f"club-stats/{team_abbrev}/now")

    async def get_skater_stats_leaders(self, season_id: int, game_type_id: int) -> dict:
        return await self._get(f"skater-stats-leaders/{season_id}/{game_type_id}")

    async def get_goalie_stats_leaders(self, season_id: int, game_type_id: int) -> dict:
        return await self._get(f"goalie-stats-leaders/{season_id}/{game_type_id}")
