from __future__ import annotations

import asyncio
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from ..clients.capwages import CapWagesClient
from ..clients.nhl import NHLClient
from ..config import Settings
from ..errors import AmbiguousPlayerError, IdentityResolutionError, PlayerNotFoundError, UpstreamRequestError
from ..models import (
    ActiveContractView,
    BasicStats,
    ComparisonFact,
    GoalieLeaderboardEntry,
    GoalieLeaderboardQuery,
    GoalieLeaderboardResult,
    GoalieAnalytics,
    GoalieRecentForm,
    GoalieStats,
    MergeNote,
    MoneyPuckCoverage,
    NormalizedPlayer,
    PlayerComparisonResult,
    PlayerContractToolResult,
    PlayerProfileToolResult,
    PlayerSearchFilters,
    PlayerSearchResult,
    PlayerSummaryDataResult,
    SkaterLeaderboardEntry,
    SkaterLeaderboardQuery,
    SkaterLeaderboardResult,
    TeamSummaryDataResult,
    TeamToolQuery,
    PlayerToolQuery,
    RecentForm,
    SourceCoverage,
    SkaterAnalytics,
    SkaterStats,
    TeamAnalytics,
    TeamIdentity,
    TeamSourceCoverage,
    TeamStats,
    ToolPlayerData,
    ToolTeamData,
)
from .moneypuck import MoneyPuckService
from .normalization import PlayerNormalizer


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._items[key] = CacheEntry(
            expires_at=time.time() + ttl_seconds,
            value=value,
        )


@dataclass(frozen=True)
class LeagueRosterPlayer:
    nhl_id: int
    full_name: str
    normalized_name: str
    team_name: str
    team_abbrev: str
    position: str
    shoots_catches: str | None
    birth_date: str | None


@dataclass(frozen=True)
class LeagueTeam:
    team_abbrev: str
    team_name: str
    team_common_name: str | None
    place_name: str | None
    team_logo: str | None
    standings_row: dict[str, Any]


def _normalize_text(value: str) -> str:
    collapsed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(character if character.isalnum() or character.isspace() else " " for character in collapsed)
    return " ".join(stripped.split())


def _default_text(value: dict | None) -> str | None:
    if not isinstance(value, dict):
        return None
    default_value = value.get("default")
    return default_value.strip() if isinstance(default_value, str) and default_value.strip() else None


def _calculate_age(birth_date: str | None) -> int | None:
    if not birth_date:
        return None

    year, month, day = (int(part) for part in birth_date.split("-"))
    today = date.today()
    age = today.year - year
    if (today.month, today.day) < (month, day):
        age -= 1
    return age


def _parse_toi_seconds(value: str | None) -> int | None:
    if not value or ":" not in value:
        return None
    minutes, seconds = value.split(":", 1)
    if not minutes.isdigit() or not seconds.isdigit():
        return None
    return int(minutes) * 60 + int(seconds)


def _safe_rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 3)


def _format_toi_seconds(total_seconds: int | None) -> str | None:
    if total_seconds is None or total_seconds < 0:
        return None
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _player_type_from_position(position: str | None) -> Literal["skater", "goalie"]:
    return "goalie" if (position or "").upper() == "G" else "skater"


LEADERBOARD_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "points": ("points", "Points"),
    "goals": ("goals", "Goals"),
    "assists": ("assists", "Assists"),
    "plus_minus": ("plusMinus", "Plus-Minus"),
    "power_play_goals": ("goalsPp", "Power-Play Goals"),
    "short_handed_goals": ("goalsSh", "Short-Handed Goals"),
    "penalty_minutes": ("penaltyMins", "Penalty Minutes"),
    "faceoff_pct": ("faceoffLeaders", "Faceoff Percentage"),
    "time_on_ice": ("toi", "Time On Ice"),
}

GOALIE_LEADERBOARD_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "wins": ("wins", "Wins"),
    "shutouts": ("shutouts", "Shutouts"),
    "save_pct": ("savePctg", "Save Percentage"),
    "goals_against_avg": ("goalsAgainstAverage", "Goals-Against Average"),
}


class PlayerToolService:
    def __init__(
        self,
        settings: Settings,
        nhl_client: NHLClient,
        capwages_client: CapWagesClient,
        normalizer: PlayerNormalizer,
        moneypuck_service: MoneyPuckService,
    ) -> None:
        self._settings = settings
        self._nhl_client = nhl_client
        self._capwages_client = capwages_client
        self._normalizer = normalizer
        self._moneypuck_service = moneypuck_service
        self._semaphore = asyncio.Semaphore(settings.max_parallel_source_requests)
        self._roster_cache = TTLCache()
        self._landing_cache = TTLCache()
        self._tool_player_cache = TTLCache()
        self._leaderboard_cache = TTLCache()
        self._team_cache = TTLCache()

    async def get_player_profile(self, query: PlayerToolQuery) -> PlayerProfileToolResult:
        landing = await self._get_landing_for_query(query)
        tool_player = self._build_tool_player_data(landing, None, query.season_type)
        return PlayerProfileToolResult(
            identity=tool_player.identity,
            profile=tool_player.profile,
            player_type=tool_player.player_type,
            stats_context=tool_player.stats_context,
            stats=tool_player.stats,
            regular_season_stats=tool_player.regular_season_stats,
            playoff_stats=tool_player.playoff_stats,
            recent_form=tool_player.recent_form,
            skater_stats=tool_player.skater_stats,
            goalie_stats=tool_player.goalie_stats,
            regular_season_skater_stats=tool_player.regular_season_skater_stats,
            playoff_skater_stats=tool_player.playoff_skater_stats,
            regular_season_goalie_stats=tool_player.regular_season_goalie_stats,
            playoff_goalie_stats=tool_player.playoff_goalie_stats,
            goalie_recent_form=tool_player.goalie_recent_form,
            skater_analytics=tool_player.skater_analytics,
            goalie_analytics=tool_player.goalie_analytics,
            moneypuck_coverage=tool_player.moneypuck_coverage,
            source_coverage=SourceCoverage(nhl_available=True),
            limitations=[
                "This tool returns NHL profile/basic stat data and current-season MoneyPuck player analytics when available.",
            ],
        )

    async def get_player_contract(self, query: PlayerToolQuery) -> PlayerContractToolResult:
        tool_player = await self._get_tool_player_for_query(query)
        return PlayerContractToolResult(
            identity=tool_player.identity,
            contract=tool_player.contract,
            active_contract=tool_player.active_contract,
            source_coverage=tool_player.source_coverage,
            limitations=self._shared_limitations(),
        )

    async def get_player_summary_data(self, query: PlayerToolQuery) -> PlayerSummaryDataResult:
        tool_player = await self._get_tool_player_for_query(query)
        return PlayerSummaryDataResult(
            player=tool_player,
            limitations=self._shared_limitations(),
        )

    async def get_team_summary_data(self, query: TeamToolQuery) -> TeamSummaryDataResult:
        tool_team = await self.get_tool_team_data(query.team, query.season_type)
        return TeamSummaryDataResult(
            team=tool_team,
            limitations=self._shared_team_limitations(query.season_type),
        )

    async def search_players(self, filters: PlayerSearchFilters) -> PlayerSearchResult:
        roster = await self._get_league_roster()
        seeded = [player for player in roster if self._matches_seed_filters(player, filters)]

        detailed = await asyncio.gather(
            *(self._get_tool_player_for_roster_player(player, filters.season_type) for player in seeded)
        )
        filtered = [player for player in detailed if self._matches_detailed_filters(player, filters)]
        sorted_players = self._sort_players(filtered, filters.sort_by)[: filters.limit]

        return PlayerSearchResult(
            filters=filters,
            total_matches=len(filtered),
            players=sorted_players,
            limitations=self._shared_limitations(),
        )

    async def compare_players(
        self,
        player_a_query: PlayerToolQuery,
        player_b_query: PlayerToolQuery,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> PlayerComparisonResult:
        player_a, player_b = await asyncio.gather(
            self._get_tool_player_for_query(player_a_query, season_type),
            self._get_tool_player_for_query(player_b_query, season_type),
        )
        if player_a.player_type != player_b.player_type:
            raise ValueError("Skater and goalie statistical comparisons are not supported in the same comparison tool.")
        return PlayerComparisonResult(
            player_a=player_a,
            player_b=player_b,
            comparisons=self._build_comparison_facts(player_a, player_b),
            limitations=self._shared_limitations(),
        )

    async def get_skater_leaderboard(self, query: SkaterLeaderboardQuery) -> SkaterLeaderboardResult:
        season_id = self._current_nhl_season_id()
        game_type_id = 2 if query.season_type == "regular_season" else 3
        payload = await self._get_skater_leaderboard_payload(season_id, game_type_id)

        category_key, category_label = LEADERBOARD_CATEGORY_MAP[query.category]
        rows = payload.get(category_key)
        if not isinstance(rows, list):
            raise ValueError(
                f"NHL leaderboard payload did not include category '{category_key}'."
            )

        leaders: list[SkaterLeaderboardEntry] = []
        for index, row in enumerate(rows[: query.limit], start=1):
            if not isinstance(row, dict):
                continue

            first_name = _default_text(row.get("firstName")) or ""
            last_name = _default_text(row.get("lastName")) or ""
            full_name = " ".join(part for part in (first_name, last_name) if part).strip()
            if not full_name:
                continue

            value = row.get("value")
            if not isinstance(value, (int, float)):
                continue

            player_id = row.get("id")
            if not isinstance(player_id, int):
                continue

            leaders.append(
                SkaterLeaderboardEntry(
                    rank=index,
                    nhl_id=player_id,
                    full_name=full_name,
                    team_abbrev=str(row.get("teamAbbrev") or "") or None,
                    position=str(row.get("position") or "") or None,
                    headshot_url=str(row.get("headshot") or "") or None,
                    value=value,
                )
            )

        return SkaterLeaderboardResult(
            season_id=season_id,
            season_type=query.season_type,
            category=query.category,
            category_label=category_label,
            leaders=leaders,
            limitations=[
                "This tool returns current-season NHL skater leaderboard data only.",
            ],
        )

    async def get_goalie_leaderboard(self, query: GoalieLeaderboardQuery) -> GoalieLeaderboardResult:
        season_id = self._current_nhl_season_id()
        game_type_id = 2 if query.season_type == "regular_season" else 3
        payload = await self._get_goalie_leaderboard_payload(season_id, game_type_id)

        category_key, category_label = GOALIE_LEADERBOARD_CATEGORY_MAP[query.category]
        rows = payload.get(category_key)
        if not isinstance(rows, list):
            raise ValueError(
                f"NHL leaderboard payload did not include category '{category_key}'."
            )

        leaders: list[GoalieLeaderboardEntry] = []
        for index, row in enumerate(rows[: query.limit], start=1):
            if not isinstance(row, dict):
                continue

            first_name = _default_text(row.get("firstName")) or ""
            last_name = _default_text(row.get("lastName")) or ""
            full_name = " ".join(part for part in (first_name, last_name) if part).strip()
            if not full_name:
                continue

            value = row.get("value")
            if not isinstance(value, (int, float)):
                continue

            player_id = row.get("id")
            if not isinstance(player_id, int):
                continue

            leaders.append(
                GoalieLeaderboardEntry(
                    rank=index,
                    nhl_id=player_id,
                    full_name=full_name,
                    team_abbrev=str(row.get("teamAbbrev") or "") or None,
                    position=str(row.get("position") or "") or None,
                    headshot_url=str(row.get("headshot") or "") or None,
                    value=value,
                )
            )

        return GoalieLeaderboardResult(
            season_id=season_id,
            season_type=query.season_type,
            category=query.category,
            category_label=category_label,
            leaders=leaders,
            limitations=[
                "This tool returns current-season NHL goalie leaderboard data only.",
            ],
        )

    async def get_tool_team_data(
        self,
        team_query: str,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> ToolTeamData:
        team = await self._resolve_team(team_query)
        return await self._build_tool_team_data(team, season_type)

    async def _with_limit(self, coroutine):
        async with self._semaphore:
            return await coroutine

    def _current_nhl_season_id(self) -> int:
        today = date.today()
        start_year = today.year if today.month >= 7 else today.year - 1
        return int(f"{start_year}{start_year + 1}")

    async def _get_skater_leaderboard_payload(self, season_id: int, game_type_id: int) -> dict:
        cache_key = f"skater:{season_id}:{game_type_id}"
        cached = self._leaderboard_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._with_limit(self._nhl_client.get_skater_stats_leaders(season_id, game_type_id))
        self._leaderboard_cache.set(cache_key, payload, self._settings.player_cache_ttl_seconds)
        return payload

    async def _get_goalie_leaderboard_payload(self, season_id: int, game_type_id: int) -> dict:
        cache_key = f"goalie:{season_id}:{game_type_id}"
        cached = self._leaderboard_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._with_limit(self._nhl_client.get_goalie_stats_leaders(season_id, game_type_id))
        self._leaderboard_cache.set(cache_key, payload, self._settings.player_cache_ttl_seconds)
        return payload

    async def _get_standings_payload(self) -> dict:
        cached = self._team_cache.get("standings_payload")
        if cached is not None:
            return cached

        payload = await self._with_limit(self._nhl_client.get_standings())
        self._team_cache.set("standings_payload", payload, self._settings.roster_cache_ttl_seconds)
        return payload

    async def _get_league_teams(self) -> list[LeagueTeam]:
        cached = self._team_cache.get("league_teams")
        if cached is not None:
            return cached

        standings = await self._get_standings_payload()
        teams: list[LeagueTeam] = []
        for row in standings.get("standings", []):
            team_abbrev = _default_text(row.get("teamAbbrev"))
            team_name = _default_text(row.get("teamName"))
            if not team_abbrev or not team_name:
                continue

            teams.append(
                LeagueTeam(
                    team_abbrev=team_abbrev,
                    team_name=team_name,
                    team_common_name=_default_text(row.get("teamCommonName")),
                    place_name=_default_text(row.get("placeName")),
                    team_logo=str(row.get("teamLogo") or "") or None,
                    standings_row=row,
                )
            )

        self._team_cache.set("league_teams", teams, self._settings.roster_cache_ttl_seconds)
        return teams

    async def _resolve_team(self, query: str) -> LeagueTeam:
        teams = await self._get_league_teams()
        normalized_query = _normalize_text(query.replace("-", " "))

        def aliases(team: LeagueTeam) -> set[str]:
            values = {
                team.team_abbrev.casefold(),
                _normalize_text(team.team_name),
            }
            if team.team_common_name:
                values.add(_normalize_text(team.team_common_name))
            if team.place_name:
                values.add(_normalize_text(team.place_name))
                if team.team_common_name:
                    values.add(_normalize_text(f"{team.place_name} {team.team_common_name}"))
            return {value for value in values if value}

        exact_matches = [team for team in teams if normalized_query in aliases(team)]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise AmbiguousPlayerError(
                f"Multiple NHL teams matched '{query}': "
                + ", ".join(team.team_name for team in exact_matches[:4])
            )

        partial_matches = [
            team
            for team in teams
            if any(
                normalized_query in alias or alias in normalized_query
                for alias in aliases(team)
            )
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            raise AmbiguousPlayerError(
                f"Multiple NHL teams matched '{query}': "
                + ", ".join(team.team_name for team in partial_matches[:4])
            )

        raise PlayerNotFoundError(f"No NHL team matched '{query}'.")

    async def _get_club_stats_payload(
        self,
        team_abbrev: str,
        season_type: Literal["regular_season", "playoffs"],
    ) -> dict:
        cache_key = f"club_stats:{team_abbrev}:{season_type}"
        cached = self._team_cache.get(cache_key)
        if cached is not None:
            return cached

        if season_type == "playoffs":
            payload = await self._with_limit(
                self._nhl_client.get_club_stats_for_season(
                    team_abbrev,
                    self._current_nhl_season_id(),
                    3,
                )
            )
        else:
            payload = await self._with_limit(self._nhl_client.get_club_stats(team_abbrev))

        self._team_cache.set(cache_key, payload, self._settings.player_cache_ttl_seconds)
        return payload

    async def _get_league_roster(self) -> list[LeagueRosterPlayer]:
        cached = self._roster_cache.get("league_roster")
        if cached is not None:
            return cached

        standings = await self._with_limit(self._nhl_client.get_standings())
        team_rows = standings.get("standings", [])
        teams = []
        for row in team_rows:
            team_abbrev = _default_text(row.get("teamAbbrev"))
            team_name = _default_text(row.get("teamName"))
            if team_abbrev and team_name:
                teams.append((team_abbrev, team_name))

        roster_payloads = await asyncio.gather(
            *(self._with_limit(self._nhl_client.get_roster(team_abbrev)) for team_abbrev, _ in teams)
        )

        players: list[LeagueRosterPlayer] = []
        for (team_abbrev, team_name), roster_payload in zip(teams, roster_payloads, strict=True):
            players.extend(self._flatten_roster(team_abbrev, team_name, roster_payload))

        self._roster_cache.set("league_roster", players, self._settings.roster_cache_ttl_seconds)
        return players

    def _flatten_roster(self, team_abbrev: str, team_name: str, roster_payload: dict) -> list[LeagueRosterPlayer]:
        players: list[LeagueRosterPlayer] = []
        for section in ("forwards", "defensemen", "goalies"):
            for player in roster_payload.get(section, []):
                full_name = " ".join(
                    part
                    for part in (
                        _default_text(player.get("firstName")) or "",
                        _default_text(player.get("lastName")) or "",
                    )
                    if part
                ).strip()
                if not full_name:
                    continue
                players.append(
                    LeagueRosterPlayer(
                        nhl_id=player["id"],
                        full_name=full_name,
                        normalized_name=_normalize_text(full_name),
                        team_name=team_name,
                        team_abbrev=team_abbrev,
                        position=str(player.get("positionCode") or ""),
                        shoots_catches=str(player.get("shootsCatches") or "") or None,
                        birth_date=str(player.get("birthDate") or "") or None,
                    )
                )
        return players

    async def _get_landing_for_query(self, query: PlayerToolQuery) -> dict:
        if query.nhl_id is not None:
            return await self._get_player_landing(query.nhl_id)

        roster_player = await self._resolve_roster_player(query.player or "")
        return await self._get_player_landing(roster_player.nhl_id)

    async def _resolve_roster_player(self, query: str) -> LeagueRosterPlayer:
        roster = await self._get_league_roster()
        normalized_query = _normalize_text(query.replace("-", " "))

        exact_matches = [player for player in roster if player.normalized_name == normalized_query]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise AmbiguousPlayerError(
                f"Multiple active NHL roster players matched '{query}': "
                + ", ".join(player.full_name for player in exact_matches[:4])
            )

        partial_matches = [
            player
            for player in roster
            if normalized_query in player.normalized_name or player.normalized_name in normalized_query
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            raise AmbiguousPlayerError(
                f"Multiple active NHL roster players matched '{query}': "
                + ", ".join(player.full_name for player in partial_matches[:4])
            )

        raise PlayerNotFoundError(f"No active NHL roster player matched '{query}'.")

    async def _get_player_landing(self, nhl_id: int) -> dict:
        cached = self._landing_cache.get(str(nhl_id))
        if cached is not None:
            return cached

        landing = await self._with_limit(self._nhl_client.get_player_landing(nhl_id))
        self._landing_cache.set(str(nhl_id), landing, self._settings.player_cache_ttl_seconds)
        return landing

    async def _get_tool_player_for_query(
        self,
        query: PlayerToolQuery,
        season_type_override: Literal["regular_season", "playoffs"] | None = None,
    ) -> ToolPlayerData:
        season_type = season_type_override or query.season_type
        if query.nhl_id is not None:
            return await self._get_tool_player_by_nhl_id(query.nhl_id, season_type)

        roster_player = await self._resolve_roster_player(query.player or "")
        return await self._get_tool_player_for_roster_player(roster_player, season_type)

    async def _get_tool_player_for_roster_player(
        self,
        roster_player: LeagueRosterPlayer,
        season_type: Literal["regular_season", "playoffs", "both"] = "regular_season",
    ) -> ToolPlayerData:
        return await self._get_tool_player_by_nhl_id(roster_player.nhl_id, season_type)

    async def _get_tool_player_by_nhl_id(
        self,
        nhl_id: int,
        season_type: Literal["regular_season", "playoffs", "both"] = "regular_season",
    ) -> ToolPlayerData:
        cache_key = f"{nhl_id}:{season_type}"
        cached = self._tool_player_cache.get(cache_key)
        if cached is not None:
            return cached

        landing = await self._get_player_landing(nhl_id)
        capwages_detail = await self._get_capwages_detail_for_landing(landing)
        tool_player = self._build_tool_player_data(landing, capwages_detail, season_type)
        self._tool_player_cache.set(cache_key, tool_player, self._settings.player_cache_ttl_seconds)
        return tool_player

    async def _get_capwages_detail_for_landing(self, landing: dict) -> dict | None:
        player_slug = str(landing.get("playerSlug") or "").strip()
        if not player_slug:
            return None

        slug_parts = player_slug.split("-")
        capwages_slug = "-".join(slug_parts[:-1]) if slug_parts and slug_parts[-1].isdigit() else player_slug
        if not capwages_slug:
            return None

        try:
            return await self._with_limit(self._capwages_client.get_player_detail(capwages_slug))
        except UpstreamRequestError as error:
            if error.status_code == 404:
                return None
            raise

    async def _build_tool_team_data(
        self,
        team: LeagueTeam,
        season_type: Literal["regular_season", "playoffs"],
    ) -> ToolTeamData:
        source_coverage = TeamSourceCoverage(nhl_available=True)
        moneypuck_analytics = self._moneypuck_service.get_team_analytics(team.team_abbrev, season_type)
        moneypuck_coverage = self._build_team_moneypuck_coverage(team.team_abbrev, season_type)

        if season_type == "playoffs":
            club_stats = await self._get_club_stats_payload(team.team_abbrev, season_type)
            stats = self._build_playoff_team_stats(club_stats, moneypuck_analytics)
        else:
            stats = self._build_regular_season_team_stats(team, moneypuck_analytics)

        return ToolTeamData(
            identity=TeamIdentity(
                team_abbrev=team.team_abbrev,
                team_name=team.team_name,
                team_logo_url=team.team_logo,
            ),
            stats=stats,
            moneypuck_analytics=moneypuck_analytics,
            source_coverage=source_coverage,
            moneypuck_coverage=moneypuck_coverage,
        )

    def _build_team_moneypuck_coverage(
        self,
        team_abbrev: str,
        season_type: Literal["regular_season", "playoffs"],
    ) -> MoneyPuckCoverage:
        coverage = self._moneypuck_service.get_team_coverage(season_type)
        analytics = self._moneypuck_service.get_team_analytics(team_abbrev, season_type)
        if coverage.available and analytics is None:
            season_label = "regular-season" if season_type == "regular_season" else "playoff"
            coverage.notes.append(
                MergeNote(
                    code="missing_moneypuck_team_coverage",
                    detail=f"No MoneyPuck analytics row was found for team {team_abbrev} in the local 2025-26 {season_label} files.",
                )
            )
        return coverage

    def _build_regular_season_team_stats(
        self,
        team: LeagueTeam,
        analytics: TeamAnalytics | None,
    ) -> TeamStats:
        row = team.standings_row
        return TeamStats(
            season_id=row.get("seasonId") if isinstance(row.get("seasonId"), int) else None,
            season_type="regular_season",
            games_played=row.get("gamesPlayed") if isinstance(row.get("gamesPlayed"), int) else None,
            wins=row.get("wins") if isinstance(row.get("wins"), int) else None,
            losses=row.get("losses") if isinstance(row.get("losses"), int) else None,
            ot_losses=row.get("otLosses") if isinstance(row.get("otLosses"), int) else None,
            points=row.get("points") if isinstance(row.get("points"), int) else None,
            points_pct=float(row.get("pointPctg")) if isinstance(row.get("pointPctg"), (int, float)) else None,
            goals_for=row.get("goalFor") if isinstance(row.get("goalFor"), int) else None,
            goals_against=row.get("goalAgainst") if isinstance(row.get("goalAgainst"), int) else None,
            power_play_pct=analytics.power_play_pct if analytics is not None else None,
            penalty_kill_pct=analytics.penalty_kill_pct if analytics is not None else None,
            goals_for_pct=analytics.goals_for_pct if analytics is not None else None,
            expected_goals_for_pct=analytics.expected_goals_for_pct if analytics is not None else None,
            corsi_pct=analytics.corsi_pct if analytics is not None else None,
            pdo=analytics.pdo if analytics is not None else None,
        )

    def _build_playoff_team_stats(
        self,
        club_stats: dict,
        analytics: TeamAnalytics | None,
    ) -> TeamStats:
        goalie_rows = club_stats.get("goalies", []) if isinstance(club_stats.get("goalies"), list) else []
        wins = 0
        losses = 0
        wins_found = False
        losses_found = False

        for goalie in goalie_rows:
            if not isinstance(goalie, dict):
                continue
            goalie_wins = goalie.get("wins")
            goalie_losses = goalie.get("losses")
            if isinstance(goalie_wins, int):
                wins += goalie_wins
                wins_found = True
            if isinstance(goalie_losses, int):
                losses += goalie_losses
                losses_found = True

        season_raw = club_stats.get("season")
        season_id = int(season_raw) if isinstance(season_raw, str) and season_raw.isdigit() else None
        return TeamStats(
            season_id=season_id,
            season_type="playoffs",
            games_played=analytics.games_played if analytics is not None else None,
            wins=wins if wins_found else None,
            losses=losses if losses_found else None,
            goals_for=analytics.goals_for if analytics is not None else None,
            goals_against=analytics.goals_against if analytics is not None else None,
            power_play_pct=analytics.power_play_pct if analytics is not None else None,
            penalty_kill_pct=analytics.penalty_kill_pct if analytics is not None else None,
            goals_for_pct=analytics.goals_for_pct if analytics is not None else None,
            expected_goals_for_pct=analytics.expected_goals_for_pct if analytics is not None else None,
            corsi_pct=analytics.corsi_pct if analytics is not None else None,
            pdo=analytics.pdo if analytics is not None else None,
        )

    def _build_tool_player_data(
        self,
        landing: dict,
        capwages_detail: dict | None,
        season_type: Literal["regular_season", "playoffs", "both"] = "regular_season",
    ) -> ToolPlayerData:
        try:
            normalized = self._normalizer.normalize_player(landing, capwages_detail)
        except IdentityResolutionError:
            normalized = self._normalizer.normalize_player(landing, None)
            normalized.source_coverage.notes.append(
                MergeNote(
                    code="capwages_identity_mismatch",
                    detail="CapWages detail was discarded because it did not match the NHL player identity cleanly.",
                )
            )

        player_type = _player_type_from_position(normalized.profile.position)
        regular_season_stats: BasicStats | None = None
        playoff_stats: BasicStats | None = None
        skater_stats: SkaterStats | None = None
        goalie_stats: GoalieStats | None = None
        regular_season_skater_stats: SkaterStats | None = None
        playoff_skater_stats: SkaterStats | None = None
        regular_season_goalie_stats: GoalieStats | None = None
        playoff_goalie_stats: GoalieStats | None = None
        selected_recent_form = RecentForm()
        goalie_recent_form: GoalieRecentForm | None = None
        skater_analytics: SkaterAnalytics | None = None
        goalie_analytics: GoalieAnalytics | None = None
        regular_season_moneypuck_coverage = self._build_moneypuck_coverage(
            landing,
            player_type,
            "regular_season",
        )
        playoff_moneypuck_coverage = self._build_moneypuck_coverage(
            landing,
            player_type,
            "playoffs",
        )
        moneypuck_coverage = self._select_moneypuck_coverage_for_context(
            season_type,
            regular_season_moneypuck_coverage,
            playoff_moneypuck_coverage,
        )
        player_id = int(landing.get("playerId") or 0)

        if player_type == "goalie":
            regular_season_goalie_stats = self._build_goalie_stats(landing, "regular_season")
            playoff_goalie_stats = self._build_goalie_stats(landing, "playoffs")
            goalie_stats = self._select_goalie_stats_for_context(
                season_type,
                regular_season_goalie_stats,
                playoff_goalie_stats,
            )
            goalie_recent_form = self._build_goalie_recent_form(landing)
            regular_season_goalie_analytics = self._moneypuck_service.get_goalie_analytics(
                player_id,
                "regular_season",
            )
            playoff_goalie_analytics = self._moneypuck_service.get_goalie_analytics(
                player_id,
                "playoffs",
            )
            goalie_analytics = self._select_goalie_analytics_for_context(
                season_type,
                regular_season_goalie_analytics,
                playoff_goalie_analytics,
            )
        else:
            regular_season_skater_stats = self._build_skater_stats(landing, "regular_season")
            playoff_skater_stats = self._build_skater_stats(landing, "playoffs")
            skater_stats = self._select_skater_stats_for_context(
                season_type,
                regular_season_skater_stats,
                playoff_skater_stats,
            )
            regular_season_stats = self._to_basic_stats(regular_season_skater_stats)
            playoff_stats = self._to_basic_stats(playoff_skater_stats)
            selected_recent_form = self._build_recent_form(landing)
            regular_season_skater_analytics = self._moneypuck_service.get_skater_analytics(
                player_id,
                "regular_season",
            )
            playoff_skater_analytics = self._moneypuck_service.get_skater_analytics(
                player_id,
                "playoffs",
            )
            skater_analytics = self._select_skater_analytics_for_context(
                season_type,
                regular_season_skater_analytics,
                playoff_skater_analytics,
            )

        selected_stats = (
            self._to_basic_stats(skater_stats)
            if skater_stats is not None
            else BasicStats()
        )

        return ToolPlayerData(
            identity=normalized.identity,
            profile=normalized.profile,
            contract=normalized.contract,
            active_contract=self._build_active_contract_view(normalized),
            player_type=player_type,
            stats_context=season_type,
            stats=selected_stats,
            regular_season_stats=regular_season_stats,
            playoff_stats=playoff_stats,
            skater_stats=skater_stats,
            goalie_stats=goalie_stats,
            regular_season_skater_stats=regular_season_skater_stats,
            playoff_skater_stats=playoff_skater_stats,
            regular_season_goalie_stats=regular_season_goalie_stats,
            playoff_goalie_stats=playoff_goalie_stats,
            recent_form=selected_recent_form,
            goalie_recent_form=goalie_recent_form,
            skater_analytics=skater_analytics,
            goalie_analytics=goalie_analytics,
            moneypuck_coverage=moneypuck_coverage,
            source_coverage=normalized.source_coverage,
        )

    def _build_moneypuck_coverage(
        self,
        landing: dict,
        player_type: Literal["skater", "goalie"],
        season_type: Literal["regular_season", "playoffs"],
    ) -> MoneyPuckCoverage:
        coverage = self._moneypuck_service.get_coverage(season_type)
        player_id = int(landing.get("playerId") or 0)

        analytics_found = (
            self._moneypuck_service.get_goalie_analytics(player_id, season_type) is not None
            if player_type == "goalie"
            else self._moneypuck_service.get_skater_analytics(player_id, season_type) is not None
        )

        if coverage.available and not analytics_found:
            season_label = "regular-season" if season_type == "regular_season" else "playoff"
            coverage.notes.append(
                MergeNote(
                    code="missing_moneypuck_player_coverage",
                    detail=f"No MoneyPuck analytics row was found for this player in the local 2025-26 {season_label} files.",
                )
            )

        return coverage

    def _select_moneypuck_coverage_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_coverage: MoneyPuckCoverage,
        playoff_coverage: MoneyPuckCoverage,
    ) -> MoneyPuckCoverage:
        if season_type == "regular_season":
            return regular_season_coverage
        if season_type == "playoffs":
            return playoff_coverage

        coverage = MoneyPuckCoverage(
            available=False,
            season_id=regular_season_coverage.season_id or playoff_coverage.season_id,
            season_type=None,
            situation=regular_season_coverage.situation or playoff_coverage.situation,
        )
        coverage.notes.append(
            MergeNote(
                code="moneypuck_both_context_not_merged",
                detail="MoneyPuck analytics are available separately for regular season and playoffs, but the combined both-stats view does not merge them into one line.",
            )
        )
        return coverage

    def _current_season_id(self, landing: dict) -> int | None:
        featured_season = landing.get("featuredStats", {}).get("season")
        if isinstance(featured_season, int):
            return featured_season

        nhl_seasons = [
            row.get("season")
            for row in landing.get("seasonTotals", [])
            if isinstance(row, dict) and str(row.get("leagueAbbrev") or "").upper() == "NHL"
        ]
        valid_seasons = [season for season in nhl_seasons if isinstance(season, int)]
        return max(valid_seasons) if valid_seasons else None

    def _current_season_rows(
        self,
        landing: dict,
        season_id: int | None,
        game_type_id: int,
    ) -> list[dict[str, Any]]:
        if season_id is None:
            return []

        rows: list[dict[str, Any]] = []
        for row in landing.get("seasonTotals", []):
            if not isinstance(row, dict):
                continue
            if row.get("season") != season_id or row.get("gameTypeId") != game_type_id:
                continue
            if str(row.get("leagueAbbrev") or "").upper() != "NHL":
                continue
            rows.append(row)
        return rows

    def _aggregate_skater_stats_from_rows(self, season_id: int, rows: list[dict[str, Any]]) -> SkaterStats:
        games_played = sum(int(row.get("gamesPlayed", 0) or 0) for row in rows)
        goals = sum(int(row.get("goals", 0) or 0) for row in rows)
        assists = sum(int(row.get("assists", 0) or 0) for row in rows)
        points = sum(int(row.get("points", 0) or 0) for row in rows)
        shots = sum(int(row.get("shots", 0) or 0) for row in rows)

        plus_minus_values = [int(row.get("plusMinus", 0) or 0) for row in rows if row.get("plusMinus") is not None]
        plus_minus = sum(plus_minus_values) if plus_minus_values else None

        weighted_toi = 0
        toi_weight = 0
        for row in rows:
            row_games = int(row.get("gamesPlayed", 0) or 0)
            row_toi_seconds = _parse_toi_seconds(str(row.get("avgToi") or "") or None)
            if row_games > 0 and row_toi_seconds is not None:
                weighted_toi += row_toi_seconds * row_games
                toi_weight += row_games

        avg_toi = _format_toi_seconds(round(weighted_toi / toi_weight)) if toi_weight else None
        shooting_pct = round(goals / shots, 6) if shots > 0 else 0.0 if goals == 0 and shots == 0 else None

        return SkaterStats(
            season_id=season_id,
            games_played=games_played,
            goals=goals,
            assists=assists,
            points=points,
            shots=shots,
            shooting_pct=shooting_pct,
            plus_minus=plus_minus,
            avg_toi=avg_toi,
        )

    def _build_skater_stats(
        self,
        landing: dict,
        season_type: Literal["regular_season", "playoffs"],
    ) -> SkaterStats:
        season_id = self._current_season_id(landing)
        game_type_id = 2 if season_type == "regular_season" else 3
        rows = self._current_season_rows(landing, season_id, game_type_id)
        if rows:
            return self._aggregate_skater_stats_from_rows(season_id, rows)

        if season_type == "regular_season":
            season_stats = landing.get("featuredStats", {}).get("regularSeason", {}).get("subSeason", {})
            return SkaterStats(
                season_id=season_id,
                games_played=season_stats.get("gamesPlayed"),
                goals=season_stats.get("goals"),
                assists=season_stats.get("assists"),
                points=season_stats.get("points"),
                shots=season_stats.get("shots"),
                shooting_pct=season_stats.get("shootingPctg"),
                plus_minus=season_stats.get("plusMinus"),
                avg_toi=None,
            )

        if season_id is None:
            return SkaterStats()

        return SkaterStats(
            season_id=season_id,
            games_played=0,
            goals=0,
            assists=0,
            points=0,
            shots=0,
            shooting_pct=0.0,
            plus_minus=0,
            avg_toi=None,
        )

    def _to_basic_stats(self, stats: SkaterStats | None) -> BasicStats | None:
        if stats is None:
            return None
        return BasicStats(
            season_id=stats.season_id,
            games_played=stats.games_played,
            goals=stats.goals,
            assists=stats.assists,
            points=stats.points,
            shots=stats.shots,
            shooting_pct=stats.shooting_pct,
            plus_minus=stats.plus_minus,
            avg_toi=stats.avg_toi,
        )

    def _aggregate_goalie_stats_from_rows(self, season_id: int, rows: list[dict[str, Any]]) -> GoalieStats:
        games_played = sum(int(row.get("gamesPlayed", 0) or 0) for row in rows)
        wins = sum(int(row.get("wins", 0) or 0) for row in rows)
        losses = sum(int(row.get("losses", 0) or 0) for row in rows)
        ot_losses = sum(int(row.get("otLosses", 0) or 0) for row in rows)
        shutouts = sum(int(row.get("shutouts", 0) or 0) for row in rows)
        shots_against = sum(int(row.get("shotsAgainst", 0) or 0) for row in rows)
        goals_against = sum(int(row.get("goalsAgainst", 0) or 0) for row in rows)

        total_toi_seconds = 0
        for row in rows:
            total_toi_seconds += _parse_toi_seconds(str(row.get("timeOnIce") or "") or None) or 0

        save_pct = None
        if shots_against > 0:
            save_pct = round((shots_against - goals_against) / shots_against, 6)

        goals_against_avg = None
        if total_toi_seconds > 0:
            goals_against_avg = round((goals_against * 3600) / total_toi_seconds, 6)

        return GoalieStats(
            season_id=season_id,
            games_played=games_played,
            wins=wins,
            losses=losses,
            ot_losses=ot_losses,
            save_pct=save_pct,
            goals_against_avg=goals_against_avg,
            shutouts=shutouts,
            shots_against=shots_against if shots_against > 0 else None,
            goals_against=goals_against if goals_against > 0 else 0 if games_played > 0 else None,
            time_on_ice=_format_toi_seconds(total_toi_seconds) if total_toi_seconds > 0 else None,
        )

    def _build_goalie_stats(
        self,
        landing: dict,
        season_type: Literal["regular_season", "playoffs"],
    ) -> GoalieStats:
        season_id = self._current_season_id(landing)
        game_type_id = 2 if season_type == "regular_season" else 3
        rows = self._current_season_rows(landing, season_id, game_type_id)
        if rows:
            return self._aggregate_goalie_stats_from_rows(season_id, rows)

        featured_key = "regularSeason" if season_type == "regular_season" else "playoffs"
        season_stats = landing.get("featuredStats", {}).get(featured_key, {}).get("subSeason", {})
        if season_stats:
            return GoalieStats(
                season_id=season_id,
                games_played=season_stats.get("gamesPlayed"),
                wins=season_stats.get("wins"),
                losses=season_stats.get("losses"),
                ot_losses=season_stats.get("otLosses"),
                save_pct=season_stats.get("savePctg"),
                goals_against_avg=season_stats.get("goalsAgainstAvg"),
                shutouts=season_stats.get("shutouts"),
                shots_against=None,
                goals_against=None,
                time_on_ice=None,
            )

        if season_id is None:
            return GoalieStats()

        return GoalieStats(
            season_id=season_id,
            games_played=0,
            wins=0,
            losses=0,
            ot_losses=0,
            save_pct=0.0,
            goals_against_avg=0.0,
            shutouts=0,
            shots_against=0,
            goals_against=0,
            time_on_ice=None,
        )

    def _select_skater_stats_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_stats: SkaterStats,
        playoff_stats: SkaterStats,
    ) -> SkaterStats:
        if season_type == "playoffs":
            return playoff_stats
        return regular_season_stats

    def _select_goalie_stats_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_stats: GoalieStats,
        playoff_stats: GoalieStats,
    ) -> GoalieStats:
        if season_type == "playoffs":
            return playoff_stats
        return regular_season_stats

    def _select_skater_analytics_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_analytics: SkaterAnalytics | None,
        playoff_analytics: SkaterAnalytics | None,
    ) -> SkaterAnalytics | None:
        if season_type == "regular_season":
            return regular_season_analytics
        if season_type == "playoffs":
            return playoff_analytics
        return None

    def _select_goalie_analytics_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_analytics: GoalieAnalytics | None,
        playoff_analytics: GoalieAnalytics | None,
    ) -> GoalieAnalytics | None:
        if season_type == "regular_season":
            return regular_season_analytics
        if season_type == "playoffs":
            return playoff_analytics
        return None

    def _build_recent_form(self, landing: dict) -> RecentForm:
        last_games = landing.get("last5Games", [])
        return RecentForm(
            games=len(last_games),
            goals=sum(int(game.get("goals", 0) or 0) for game in last_games),
            assists=sum(int(game.get("assists", 0) or 0) for game in last_games),
            points=sum(int(game.get("points", 0) or 0) for game in last_games),
        )

    def _build_goalie_recent_form(self, landing: dict) -> GoalieRecentForm:
        last_games = [game for game in landing.get("last5Games", []) if isinstance(game, dict)]
        wins = 0
        losses = 0
        ot_losses = 0
        shots_against = 0
        goals_against = 0
        total_toi_seconds = 0

        for game in last_games:
            decision = str(game.get("decision") or "").upper()
            if decision == "W":
                wins += 1
            elif decision == "L":
                losses += 1
            elif decision == "OTL":
                ot_losses += 1

            shots_against += int(game.get("shotsAgainst", 0) or 0)
            goals_against += int(game.get("goalsAgainst", 0) or 0)
            total_toi_seconds += _parse_toi_seconds(str(game.get("toi") or "") or None) or 0

        save_pct = None
        if shots_against > 0:
            save_pct = round((shots_against - goals_against) / shots_against, 6)

        goals_against_avg = None
        if total_toi_seconds > 0:
            goals_against_avg = round((goals_against * 3600) / total_toi_seconds, 6)

        return GoalieRecentForm(
            games=len(last_games),
            wins=wins,
            losses=losses,
            ot_losses=ot_losses,
            save_pct=save_pct,
            goals_against_avg=goals_against_avg,
            shots_against=shots_against,
            goals_against=goals_against,
            time_on_ice=_format_toi_seconds(total_toi_seconds) if total_toi_seconds > 0 else None,
        )

    def _build_active_contract_view(self, normalized: NormalizedPlayer) -> ActiveContractView:
        contract = normalized.contract.active_contract
        current_season_label = normalized.contract.current_season_label
        if contract is None:
            return ActiveContractView(current_season_label=current_season_label)

        active_season = next(
            (season for season in contract.seasons if season.season == current_season_label),
            None,
        )
        if active_season is None:
            return ActiveContractView(
                current_season_label=current_season_label,
                contract_type=contract.contract_type,
                expiry_status=contract.expiry_status,
            )

        active_index = contract.seasons.index(active_season)
        years_remaining = len(contract.seasons) - active_index
        signing_bonus_heavy = (active_season.signing_bonuses or 0) > (active_season.base_salary or 0)
        return ActiveContractView(
            current_season_label=current_season_label,
            contract_type=contract.contract_type,
            expiry_status=contract.expiry_status,
            current_clause=active_season.clause,
            current_cap_hit=active_season.cap_hit,
            current_aav=active_season.aav,
            years_remaining=years_remaining,
            has_clause=bool(active_season.clause),
            signing_bonus_heavy=signing_bonus_heavy,
            active_season=active_season,
        )

    def _matches_seed_filters(self, player: LeagueRosterPlayer, filters: PlayerSearchFilters) -> bool:
        if filters.player:
            query = _normalize_text(filters.player.replace("-", " "))
            if query not in player.normalized_name:
                return False

        if filters.team:
            team_query = _normalize_text(filters.team)
            if team_query not in _normalize_text(player.team_name) and team_query != player.team_abbrev.casefold():
                return False

        if filters.position and player.position.upper() != filters.position.upper():
            return False

        if filters.shoots_catches and player.shoots_catches != filters.shoots_catches:
            return False

        age = _calculate_age(player.birth_date)
        if filters.age_min is not None and (age is None or age < filters.age_min):
            return False
        if filters.age_max is not None and (age is None or age > filters.age_max):
            return False

        return True

    def _matches_detailed_filters(self, player: ToolPlayerData, filters: PlayerSearchFilters) -> bool:
        age = _calculate_age(player.profile.birth_date)
        if filters.age_min is not None and (age is None or age < filters.age_min):
            return False
        if filters.age_max is not None and (age is None or age > filters.age_max):
            return False

        if filters.aav_min is not None and (player.active_contract.current_aav is None or player.active_contract.current_aav < filters.aav_min):
            return False
        if filters.aav_max is not None and (player.active_contract.current_aav is None or player.active_contract.current_aav > filters.aav_max):
            return False
        if filters.years_remaining_min is not None and (
            player.active_contract.years_remaining is None or player.active_contract.years_remaining < filters.years_remaining_min
        ):
            return False
        if filters.years_remaining_max is not None and (
            player.active_contract.years_remaining is None or player.active_contract.years_remaining > filters.years_remaining_max
        ):
            return False
        if filters.expiry_status and player.active_contract.expiry_status != filters.expiry_status:
            return False
        if filters.clause_required and not player.active_contract.has_clause:
            return False

        uses_goalie_metrics = any(
            value is not None
            for value in (filters.wins_min, filters.save_pct_min, filters.gaa_max, filters.shutouts_min)
        ) or filters.sort_by in {"wins_desc", "save_pct_desc", "gaa_asc", "shutouts_desc"}
        uses_skater_metrics = any(
            value is not None
            for value in (filters.goals_min, filters.assists_min, filters.points_min, filters.shots_min)
        )

        if player.player_type == "goalie":
            if uses_skater_metrics:
                return False
            goalie_stats = player.goalie_stats
            if filters.games_played_min is not None and (
                goalie_stats is None
                or goalie_stats.games_played is None
                or goalie_stats.games_played < filters.games_played_min
            ):
                return False
            if filters.wins_min is not None and (
                goalie_stats is None or goalie_stats.wins is None or goalie_stats.wins < filters.wins_min
            ):
                return False
            if filters.save_pct_min is not None and (
                goalie_stats is None
                or goalie_stats.save_pct is None
                or goalie_stats.save_pct < filters.save_pct_min
            ):
                return False
            if filters.gaa_max is not None and (
                goalie_stats is None
                or goalie_stats.goals_against_avg is None
                or goalie_stats.goals_against_avg > filters.gaa_max
            ):
                return False
            if filters.shutouts_min is not None and (
                goalie_stats is None
                or goalie_stats.shutouts is None
                or goalie_stats.shutouts < filters.shutouts_min
            ):
                return False
            return True

        if uses_goalie_metrics:
            return False
        if filters.games_played_min is not None and (
            player.stats.games_played is None or player.stats.games_played < filters.games_played_min
        ):
            return False
        if filters.goals_min is not None and (player.stats.goals is None or player.stats.goals < filters.goals_min):
            return False
        if filters.assists_min is not None and (
            player.stats.assists is None or player.stats.assists < filters.assists_min
        ):
            return False
        if filters.points_min is not None and (
            player.stats.points is None or player.stats.points < filters.points_min
        ):
            return False
        if filters.shots_min is not None and (player.stats.shots is None or player.stats.shots < filters.shots_min):
            return False

        return True

    def _sort_players(self, players: list[ToolPlayerData], sort_by: str) -> list[ToolPlayerData]:
        def age_value(player: ToolPlayerData) -> int:
            return _calculate_age(player.profile.birth_date) or 10**9

        def aav_value(player: ToolPlayerData) -> int:
            return player.active_contract.current_aav if player.active_contract.current_aav is not None else 10**12

        def term_value(player: ToolPlayerData) -> int:
            return (
                player.active_contract.years_remaining
                if player.active_contract.years_remaining is not None
                else 10**9
            )

        def skater_points_value(player: ToolPlayerData) -> int:
            return player.stats.points or 0

        def skater_goals_value(player: ToolPlayerData) -> int:
            return player.stats.goals or 0

        def goalie_wins_value(player: ToolPlayerData) -> int:
            return player.goalie_stats.wins if player.goalie_stats and player.goalie_stats.wins is not None else -1

        def goalie_save_pct_value(player: ToolPlayerData) -> float:
            return (
                player.goalie_stats.save_pct
                if player.goalie_stats and player.goalie_stats.save_pct is not None
                else -1.0
            )

        def goalie_gaa_value(player: ToolPlayerData) -> float:
            return (
                player.goalie_stats.goals_against_avg
                if player.goalie_stats and player.goalie_stats.goals_against_avg is not None
                else 10**9
            )

        def goalie_shutouts_value(player: ToolPlayerData) -> int:
            return (
                player.goalie_stats.shutouts
                if player.goalie_stats and player.goalie_stats.shutouts is not None
                else -1
            )

        if sort_by == "goals_desc":
            return sorted(players, key=lambda player: (-skater_goals_value(player), -skater_points_value(player)))
        if sort_by == "wins_desc":
            goalies = [player for player in players if player.player_type == "goalie"]
            return sorted(goalies, key=lambda player: (-goalie_wins_value(player), -goalie_save_pct_value(player)))
        if sort_by == "save_pct_desc":
            goalies = [player for player in players if player.player_type == "goalie"]
            return sorted(goalies, key=lambda player: (-goalie_save_pct_value(player), -goalie_wins_value(player)))
        if sort_by == "gaa_asc":
            goalies = [player for player in players if player.player_type == "goalie"]
            return sorted(goalies, key=lambda player: (goalie_gaa_value(player), -goalie_wins_value(player)))
        if sort_by == "shutouts_desc":
            goalies = [player for player in players if player.player_type == "goalie"]
            return sorted(goalies, key=lambda player: (-goalie_shutouts_value(player), -goalie_wins_value(player)))
        if sort_by == "age_asc":
            return sorted(players, key=lambda player: (age_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        if sort_by == "age_desc":
            return sorted(players, key=lambda player: (-age_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        if sort_by == "aav_asc":
            return sorted(players, key=lambda player: (aav_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        if sort_by == "aav_desc":
            return sorted(players, key=lambda player: (-aav_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        if sort_by == "term_asc":
            return sorted(players, key=lambda player: (term_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        if sort_by == "term_desc":
            return sorted(players, key=lambda player: (-term_value(player), -skater_points_value(player), -goalie_wins_value(player)))
        return sorted(players, key=lambda player: (-skater_points_value(player), -skater_goals_value(player), -goalie_wins_value(player)))

    def _build_comparison_facts(
        self,
        player_a: ToolPlayerData,
        player_b: ToolPlayerData,
    ) -> list[ComparisonFact]:
        shared_facts = [
            self._comparison_fact("team", player_a.profile.team_abbrev, player_b.profile.team_abbrev),
            self._comparison_fact("position", player_a.profile.position, player_b.profile.position),
            self._comparison_fact("shoots_catches", player_a.profile.shoots_catches, player_b.profile.shoots_catches),
            self._comparison_fact("age", _calculate_age(player_a.profile.birth_date), _calculate_age(player_b.profile.birth_date)),
        ]

        if player_a.player_type == "goalie" and player_b.player_type == "goalie":
            player_a_goalie = player_a.goalie_stats or GoalieStats()
            player_b_goalie = player_b.goalie_stats or GoalieStats()
            player_a_goalie_analytics = player_a.goalie_analytics or GoalieAnalytics()
            player_b_goalie_analytics = player_b.goalie_analytics or GoalieAnalytics()
            stat_facts = [
                self._comparison_fact("games_played", player_a_goalie.games_played, player_b_goalie.games_played),
                self._comparison_fact("wins", player_a_goalie.wins, player_b_goalie.wins, higher_is_better=True),
                self._comparison_fact("losses", player_a_goalie.losses, player_b_goalie.losses, lower_is_better=True),
                self._comparison_fact("ot_losses", player_a_goalie.ot_losses, player_b_goalie.ot_losses, lower_is_better=True),
                self._comparison_fact("save_pct", player_a_goalie.save_pct, player_b_goalie.save_pct, higher_is_better=True),
                self._comparison_fact(
                    "goals_against_avg",
                    player_a_goalie.goals_against_avg,
                    player_b_goalie.goals_against_avg,
                    lower_is_better=True,
                ),
                self._comparison_fact("shutouts", player_a_goalie.shutouts, player_b_goalie.shutouts, higher_is_better=True),
                self._comparison_fact("shots_against", player_a_goalie.shots_against, player_b_goalie.shots_against),
                self._comparison_fact("goals_against", player_a_goalie.goals_against, player_b_goalie.goals_against, lower_is_better=True),
                self._comparison_fact("time_on_ice", player_a_goalie.time_on_ice, player_b_goalie.time_on_ice),
                self._comparison_fact(
                    "goals_saved_above_expected",
                    player_a_goalie_analytics.goals_saved_above_expected,
                    player_b_goalie_analytics.goals_saved_above_expected,
                    higher_is_better=True,
                ),
                self._comparison_fact(
                    "goals_saved_above_expected_per_60",
                    player_a_goalie_analytics.goals_saved_above_expected_per_60,
                    player_b_goalie_analytics.goals_saved_above_expected_per_60,
                    higher_is_better=True,
                ),
            ]
        else:
            player_a_skater_analytics = player_a.skater_analytics or SkaterAnalytics()
            player_b_skater_analytics = player_b.skater_analytics or SkaterAnalytics()
            stat_facts = [
                self._comparison_fact("games_played", player_a.stats.games_played, player_b.stats.games_played),
                self._comparison_fact("goals", player_a.stats.goals, player_b.stats.goals, higher_is_better=True),
                self._comparison_fact("assists", player_a.stats.assists, player_b.stats.assists, higher_is_better=True),
                self._comparison_fact("points", player_a.stats.points, player_b.stats.points, higher_is_better=True),
                self._comparison_fact(
                    "goals_per_game",
                    _safe_rate(player_a.stats.goals, player_a.stats.games_played),
                    _safe_rate(player_b.stats.goals, player_b.stats.games_played),
                    higher_is_better=True,
                ),
                self._comparison_fact(
                    "assists_per_game",
                    _safe_rate(player_a.stats.assists, player_a.stats.games_played),
                    _safe_rate(player_b.stats.assists, player_b.stats.games_played),
                    higher_is_better=True,
                ),
                self._comparison_fact(
                    "points_per_game",
                    _safe_rate(player_a.stats.points, player_a.stats.games_played),
                    _safe_rate(player_b.stats.points, player_b.stats.games_played),
                    higher_is_better=True,
                ),
                self._comparison_fact("shots", player_a.stats.shots, player_b.stats.shots, higher_is_better=True),
                self._comparison_fact("shooting_pct", player_a.stats.shooting_pct, player_b.stats.shooting_pct, higher_is_better=True),
                self._comparison_fact("avg_toi", player_a.stats.avg_toi, player_b.stats.avg_toi),
                self._comparison_fact(
                    "on_ice_expected_goals_pct",
                    player_a_skater_analytics.on_ice_expected_goals_pct,
                    player_b_skater_analytics.on_ice_expected_goals_pct,
                    higher_is_better=True,
                ),
                self._comparison_fact(
                    "relative_expected_goals_pct",
                    player_a_skater_analytics.relative_expected_goals_pct,
                    player_b_skater_analytics.relative_expected_goals_pct,
                    higher_is_better=True,
                ),
                self._comparison_fact(
                    "on_ice_corsi_pct",
                    player_a_skater_analytics.on_ice_corsi_pct,
                    player_b_skater_analytics.on_ice_corsi_pct,
                    higher_is_better=True,
                ),
            ]

        return shared_facts + stat_facts + [
            self._comparison_fact("current_aav", player_a.active_contract.current_aav, player_b.active_contract.current_aav, lower_is_better=True),
            self._comparison_fact("current_cap_hit", player_a.active_contract.current_cap_hit, player_b.active_contract.current_cap_hit, lower_is_better=True),
            self._comparison_fact("years_remaining", player_a.active_contract.years_remaining, player_b.active_contract.years_remaining, lower_is_better=True),
            self._comparison_fact("expiry_status", player_a.active_contract.expiry_status, player_b.active_contract.expiry_status),
            self._comparison_fact(
                "has_clause",
                player_a.active_contract.has_clause,
                player_b.active_contract.has_clause,
                lower_is_better=True,
            ),
        ]

    def _comparison_fact(
        self,
        category: str,
        player_a_value: str | int | float | bool | None,
        player_b_value: str | int | float | bool | None,
        *,
        higher_is_better: bool = False,
        lower_is_better: bool = False,
    ) -> ComparisonFact:
        winner = "none"
        if player_a_value is not None and player_b_value is not None and player_a_value != player_b_value:
            if higher_is_better:
                winner = "player_a" if player_a_value > player_b_value else "player_b"
            elif lower_is_better:
                winner = "player_a" if player_a_value < player_b_value else "player_b"
        elif player_a_value == player_b_value and player_a_value is not None:
            winner = "tie"

        lower_flag = True if lower_is_better else False if higher_is_better else None
        return ComparisonFact(
            category=category,
            player_a_value=player_a_value,
            player_b_value=player_b_value,
            winner=winner,
            lower_is_better=lower_flag,
        )

    def _shared_limitations(self) -> list[str]:
        return [
            "These tools search only the current active NHL roster universe built from standings and team rosters.",
            "Outputs are grounded only in NHL API data, CapWages contract data, and local MoneyPuck player analytics when available.",
            "Broader advanced analytics and team-context reasoning are not part of the current build.",
        ]

    def _shared_team_limitations(
        self,
        season_type: Literal["regular_season", "playoffs"],
    ) -> list[str]:
        limitations = [
            "Team outputs are grounded only in NHL API team data and local MoneyPuck team analytics when available.",
            "Manual team-context guidance is not part of the current build.",
        ]
        if season_type == "playoffs":
            limitations.append(
                "Playoff team outputs omit standings-only fields that are not meaningful or supported in that context."
            )
        return limitations
