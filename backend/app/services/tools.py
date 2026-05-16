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
    MergeNote,
    NormalizedPlayer,
    PlayerComparisonResult,
    PlayerContractToolResult,
    PlayerProfileToolResult,
    PlayerSearchFilters,
    PlayerSearchResult,
    PlayerSummaryDataResult,
    PlayerToolQuery,
    RecentForm,
    SourceCoverage,
    ToolPlayerData,
)
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


class PlayerToolService:
    def __init__(
        self,
        settings: Settings,
        nhl_client: NHLClient,
        capwages_client: CapWagesClient,
        normalizer: PlayerNormalizer,
    ) -> None:
        self._settings = settings
        self._nhl_client = nhl_client
        self._capwages_client = capwages_client
        self._normalizer = normalizer
        self._semaphore = asyncio.Semaphore(settings.max_parallel_source_requests)
        self._roster_cache = TTLCache()
        self._landing_cache = TTLCache()
        self._tool_player_cache = TTLCache()

    async def get_player_profile(self, query: PlayerToolQuery) -> PlayerProfileToolResult:
        landing = await self._get_landing_for_query(query)
        tool_player = self._build_tool_player_data(landing, None, query.season_type)
        return PlayerProfileToolResult(
            identity=tool_player.identity,
            profile=tool_player.profile,
            stats_context=tool_player.stats_context,
            stats=tool_player.stats,
            regular_season_stats=tool_player.regular_season_stats,
            playoff_stats=tool_player.playoff_stats,
            recent_form=tool_player.recent_form,
            source_coverage=SourceCoverage(nhl_available=True),
            limitations=[
                "This tool returns NHL profile and basic stat data only.",
                "Contract and CapWages fields are not included unless you call a contract or summary tool.",
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
        return PlayerComparisonResult(
            player_a=player_a,
            player_b=player_b,
            comparisons=self._build_comparison_facts(player_a, player_b),
            limitations=self._shared_limitations(),
        )

    async def _with_limit(self, coroutine):
        async with self._semaphore:
            return await coroutine

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

        regular_season_stats = self._build_basic_stats(landing, "regular_season")
        playoff_stats = self._build_basic_stats(landing, "playoffs")
        selected_stats = self._select_stats_for_context(
            season_type,
            regular_season_stats,
            playoff_stats,
        )

        return ToolPlayerData(
            identity=normalized.identity,
            profile=normalized.profile,
            contract=normalized.contract,
            active_contract=self._build_active_contract_view(normalized),
            stats_context=season_type,
            stats=selected_stats,
            regular_season_stats=regular_season_stats,
            playoff_stats=playoff_stats,
            recent_form=self._build_recent_form(landing),
            source_coverage=normalized.source_coverage,
        )

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

    def _aggregate_basic_stats_from_rows(self, season_id: int, rows: list[dict[str, Any]]) -> BasicStats:
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

        return BasicStats(
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

    def _build_basic_stats(
        self,
        landing: dict,
        season_type: Literal["regular_season", "playoffs"],
    ) -> BasicStats:
        season_id = self._current_season_id(landing)
        game_type_id = 2 if season_type == "regular_season" else 3
        rows = self._current_season_rows(landing, season_id, game_type_id)
        if rows:
            return self._aggregate_basic_stats_from_rows(season_id, rows)

        if season_type == "regular_season":
            season_stats = landing.get("featuredStats", {}).get("regularSeason", {}).get("subSeason", {})
            return BasicStats(
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
            return BasicStats()

        return BasicStats(
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

    def _select_stats_for_context(
        self,
        season_type: Literal["regular_season", "playoffs", "both"],
        regular_season_stats: BasicStats,
        playoff_stats: BasicStats,
    ) -> BasicStats:
        if season_type == "playoffs":
            return playoff_stats
        return regular_season_stats

    def _build_recent_form(self, landing: dict) -> RecentForm:
        last_games = landing.get("last5Games", [])
        return RecentForm(
            games=len(last_games),
            goals=sum(int(game.get("goals", 0) or 0) for game in last_games),
            assists=sum(int(game.get("assists", 0) or 0) for game in last_games),
            points=sum(int(game.get("points", 0) or 0) for game in last_games),
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

        if sort_by == "goals_desc":
            return sorted(players, key=lambda player: (-(player.stats.goals or 0), -(player.stats.points or 0)))
        if sort_by == "age_asc":
            return sorted(players, key=lambda player: (age_value(player), -(player.stats.points or 0)))
        if sort_by == "age_desc":
            return sorted(players, key=lambda player: (-age_value(player), -(player.stats.points or 0)))
        if sort_by == "aav_asc":
            return sorted(players, key=lambda player: (aav_value(player), -(player.stats.points or 0)))
        if sort_by == "aav_desc":
            return sorted(players, key=lambda player: (-aav_value(player), -(player.stats.points or 0)))
        if sort_by == "term_asc":
            return sorted(players, key=lambda player: (term_value(player), -(player.stats.points or 0)))
        if sort_by == "term_desc":
            return sorted(players, key=lambda player: (-term_value(player), -(player.stats.points or 0)))
        return sorted(players, key=lambda player: (-(player.stats.points or 0), -(player.stats.goals or 0)))

    def _build_comparison_facts(
        self,
        player_a: ToolPlayerData,
        player_b: ToolPlayerData,
    ) -> list[ComparisonFact]:
        return [
            self._comparison_fact("team", player_a.profile.team_abbrev, player_b.profile.team_abbrev),
            self._comparison_fact("position", player_a.profile.position, player_b.profile.position),
            self._comparison_fact("shoots_catches", player_a.profile.shoots_catches, player_b.profile.shoots_catches),
            self._comparison_fact("age", _calculate_age(player_a.profile.birth_date), _calculate_age(player_b.profile.birth_date)),
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
            "Outputs are grounded only in NHL API data and CapWages contract data.",
            "Advanced analytics and manual team-context reasoning are not part of v0.5.",
        ]
