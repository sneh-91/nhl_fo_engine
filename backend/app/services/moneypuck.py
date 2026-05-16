from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Literal

from ..config import Settings
from ..models import GoalieAnalytics, MergeNote, MoneyPuckCoverage, SkaterAnalytics, TeamAnalytics


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(float(stripped))
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _season_label(season_type: Literal["regular_season", "playoffs"]) -> str:
    return "regular-season" if season_type == "regular_season" else "playoff"


@dataclass
class MoneyPuckSnapshot:
    player_coverage: MoneyPuckCoverage
    team_coverage: MoneyPuckCoverage
    skaters: dict[int, SkaterAnalytics] = field(default_factory=dict)
    goalies: dict[int, GoalieAnalytics] = field(default_factory=dict)
    teams: dict[str, TeamAnalytics] = field(default_factory=dict)


class MoneyPuckService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._cached_snapshots: dict[str, MoneyPuckSnapshot] = {}
        self._cached_at: dict[str, float] = {}

    def get_skater_analytics(
        self,
        player_id: int,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> SkaterAnalytics | None:
        return self._get_snapshot(season_type).skaters.get(player_id)

    def get_goalie_analytics(
        self,
        player_id: int,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> GoalieAnalytics | None:
        return self._get_snapshot(season_type).goalies.get(player_id)

    def get_coverage(
        self,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> MoneyPuckCoverage:
        return self._get_snapshot(season_type).player_coverage.model_copy(deep=True)

    def get_team_analytics(
        self,
        team_abbrev: str,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> TeamAnalytics | None:
        return self._get_snapshot(season_type).teams.get(team_abbrev.strip().upper())

    def get_team_coverage(
        self,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> MoneyPuckCoverage:
        return self._get_snapshot(season_type).team_coverage.model_copy(deep=True)

    def refresh(
        self,
        season_type: Literal["regular_season", "playoffs"] = "regular_season",
    ) -> MoneyPuckSnapshot:
        with self._lock:
            snapshot = self._load_snapshot(season_type)
            self._cached_snapshots[season_type] = snapshot
            self._cached_at[season_type] = time.time()
            return snapshot

    def _get_snapshot(self, season_type: Literal["regular_season", "playoffs"]) -> MoneyPuckSnapshot:
        with self._lock:
            cached_snapshot = self._cached_snapshots.get(season_type)
            cached_at = self._cached_at.get(season_type, 0.0)
            if (
                cached_snapshot is None
                or (time.time() - cached_at) >= self._settings.moneypuck_cache_ttl_seconds
            ):
                cached_snapshot = self._load_snapshot(season_type)
                self._cached_snapshots[season_type] = cached_snapshot
                self._cached_at[season_type] = time.time()
            return cached_snapshot

    def _load_snapshot(self, season_type: Literal["regular_season", "playoffs"]) -> MoneyPuckSnapshot:
        player_coverage = MoneyPuckCoverage(
            available=False,
            season_id=2025,
            season_type=season_type,
            situation="all",
        )
        team_coverage = MoneyPuckCoverage(
            available=False,
            season_id=2025,
            season_type=season_type,
            situation="all",
        )
        if not self._settings.moneypuck_enabled:
            disabled_note = MergeNote(
                code="moneypuck_disabled",
                detail="MoneyPuck analytics are disabled in settings.",
            )
            player_coverage.notes.append(disabled_note)
            team_coverage.notes.append(disabled_note.model_copy(deep=True))
            return MoneyPuckSnapshot(
                player_coverage=player_coverage,
                team_coverage=team_coverage,
            )

        skater_path, goalie_path, team_path = self._paths_for_season_type(season_type)
        skaters, skater_notes = self._load_skaters(skater_path, season_type)
        goalies, goalie_notes = self._load_goalies(goalie_path, season_type)
        teams, team_notes = self._load_teams(team_path, season_type)
        player_coverage.available = bool(skaters or goalies)
        player_coverage.notes.extend(skater_notes)
        player_coverage.notes.extend(goalie_notes)
        team_coverage.available = bool(teams)
        team_coverage.notes.extend(team_notes)
        return MoneyPuckSnapshot(
            player_coverage=player_coverage,
            team_coverage=team_coverage,
            skaters=skaters,
            goalies=goalies,
            teams=teams,
        )

    def _paths_for_season_type(
        self,
        season_type: Literal["regular_season", "playoffs"],
    ) -> tuple[Path, Path, Path]:
        if season_type == "playoffs":
            return (
                self._settings.moneypuck_2025_playoff_skaters_path,
                self._settings.moneypuck_2025_playoff_goalies_path,
                self._settings.moneypuck_2025_playoff_teams_path,
            )
        return (
            self._settings.moneypuck_2025_regular_skaters_path,
            self._settings.moneypuck_2025_regular_goalies_path,
            self._settings.moneypuck_2025_regular_teams_path,
        )

    def _load_skaters(
        self,
        path: Path,
        season_type: Literal["regular_season", "playoffs"],
    ) -> tuple[dict[int, SkaterAnalytics], list[MergeNote]]:
        notes: list[MergeNote] = []
        if not path.exists():
            notes.append(
                MergeNote(
                    code="moneypuck_skaters_missing",
                    detail=f"MoneyPuck {_season_label(season_type)} skater file was not found at {path}.",
                )
            )
            return {}, notes

        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                analytics_by_player: dict[int, SkaterAnalytics] = {}
                for row in reader:
                    if row.get("situation") != "all":
                        continue
                    player_id = _parse_int(row.get("playerId"))
                    if player_id is None:
                        continue

                    on_ice_xg_pct = _parse_float(row.get("onIce_xGoalsPercentage"))
                    off_ice_xg_pct = _parse_float(row.get("offIce_xGoalsPercentage"))
                    relative_xg_pct = None
                    if on_ice_xg_pct is not None and off_ice_xg_pct is not None:
                        relative_xg_pct = on_ice_xg_pct - off_ice_xg_pct

                    analytics_by_player[player_id] = SkaterAnalytics(
                        season_id=_parse_int(row.get("season")),
                        situation="all",
                        on_ice_expected_goals_pct=on_ice_xg_pct,
                        relative_expected_goals_pct=relative_xg_pct,
                        on_ice_corsi_pct=_parse_float(row.get("onIce_corsiPercentage")),
                    )
        except (OSError, csv.Error) as error:
            notes.append(
                MergeNote(
                    code="moneypuck_skaters_parse_error",
                    detail=f"MoneyPuck {_season_label(season_type)} skater file could not be parsed: {error}",
                )
            )
            return {}, notes

        if not analytics_by_player:
            notes.append(
                MergeNote(
                    code="moneypuck_skaters_empty",
                    detail=f"MoneyPuck {_season_label(season_type)} skater file loaded but no 'all' situation rows were found.",
                )
            )
        return analytics_by_player, notes

    def _load_goalies(
        self,
        path: Path,
        season_type: Literal["regular_season", "playoffs"],
    ) -> tuple[dict[int, GoalieAnalytics], list[MergeNote]]:
        notes: list[MergeNote] = []
        if not path.exists():
            notes.append(
                MergeNote(
                    code="moneypuck_goalies_missing",
                    detail=f"MoneyPuck {_season_label(season_type)} goalie file was not found at {path}.",
                )
            )
            return {}, notes

        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                analytics_by_player: dict[int, GoalieAnalytics] = {}
                for row in reader:
                    if row.get("situation") != "all":
                        continue
                    player_id = _parse_int(row.get("playerId"))
                    if player_id is None:
                        continue

                    expected_goals_against = _parse_float(row.get("xGoals"))
                    goals_against = _parse_float(row.get("goals"))
                    icetime_seconds = _parse_float(row.get("icetime"))

                    goals_saved_above_expected = None
                    if expected_goals_against is not None and goals_against is not None:
                        goals_saved_above_expected = expected_goals_against - goals_against

                    goals_saved_above_expected_per_60 = None
                    if (
                        goals_saved_above_expected is not None
                        and icetime_seconds is not None
                        and icetime_seconds > 0
                    ):
                        goals_saved_above_expected_per_60 = (
                            goals_saved_above_expected / icetime_seconds * 3600.0
                        )

                    analytics_by_player[player_id] = GoalieAnalytics(
                        season_id=_parse_int(row.get("season")),
                        situation="all",
                        goals_saved_above_expected=goals_saved_above_expected,
                        goals_saved_above_expected_per_60=goals_saved_above_expected_per_60,
                    )
        except (OSError, csv.Error) as error:
            notes.append(
                MergeNote(
                    code="moneypuck_goalies_parse_error",
                    detail=f"MoneyPuck {_season_label(season_type)} goalie file could not be parsed: {error}",
                )
            )
            return {}, notes

        if not analytics_by_player:
            notes.append(
                MergeNote(
                    code="moneypuck_goalies_empty",
                    detail=f"MoneyPuck {_season_label(season_type)} goalie file loaded but no 'all' situation rows were found.",
                )
            )
        return analytics_by_player, notes

    def _load_teams(
        self,
        path: Path,
        season_type: Literal["regular_season", "playoffs"],
    ) -> tuple[dict[str, TeamAnalytics], list[MergeNote]]:
        notes: list[MergeNote] = []
        if not path.exists():
            notes.append(
                MergeNote(
                    code="moneypuck_teams_missing",
                    detail=f"MoneyPuck {_season_label(season_type)} team file was not found at {path}.",
                )
            )
            return {}, notes

        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                analytics_by_team: dict[str, TeamAnalytics] = {}
                for row in reader:
                    if row.get("situation") != "all":
                        continue
                    if str(row.get("position") or "").strip() != "Team Level":
                        continue

                    team_abbrev = str(row.get("team") or "").strip().upper()
                    if not team_abbrev:
                        continue

                    goals_for = _parse_int(row.get("goalsFor"))
                    goals_against = _parse_int(row.get("goalsAgainst"))
                    shots_on_goal_for = _parse_float(row.get("shotsOnGoalFor"))
                    shots_on_goal_against = _parse_float(row.get("shotsOnGoalAgainst"))
                    saved_shots_on_goal_against = _parse_float(row.get("savedShotsOnGoalAgainst"))

                    goals_for_pct = None
                    if (
                        goals_for is not None
                        and goals_against is not None
                        and (goals_for + goals_against) > 0
                    ):
                        goals_for_pct = round(goals_for / (goals_for + goals_against), 6)

                    pdo = None
                    if (
                        goals_for is not None
                        and shots_on_goal_for is not None
                        and shots_on_goal_against is not None
                        and saved_shots_on_goal_against is not None
                        and shots_on_goal_for > 0
                        and shots_on_goal_against > 0
                    ):
                        shooting_pct = goals_for / shots_on_goal_for
                        save_pct = saved_shots_on_goal_against / shots_on_goal_against
                        pdo = round(shooting_pct + save_pct, 6)

                    analytics_by_team[team_abbrev] = TeamAnalytics(
                        season_id=_parse_int(row.get("season")),
                        season_type=season_type,
                        team_abbrev=team_abbrev,
                        situation="all",
                        games_played=_parse_int(row.get("games_played")),
                        goals_for=goals_for,
                        goals_against=goals_against,
                        goals_for_pct=goals_for_pct,
                        expected_goals_for_pct=_parse_float(row.get("xGoalsPercentage")),
                        corsi_pct=_parse_float(row.get("corsiPercentage")),
                        pdo=pdo,
                    )
        except (OSError, csv.Error) as error:
            notes.append(
                MergeNote(
                    code="moneypuck_teams_parse_error",
                    detail=f"MoneyPuck {_season_label(season_type)} team file could not be parsed: {error}",
                )
            )
            return {}, notes

        if not analytics_by_team:
            notes.append(
                MergeNote(
                    code="moneypuck_teams_empty",
                    detail=f"MoneyPuck {_season_label(season_type)} team file loaded but no team-level 'all' rows were found.",
                )
            )
        return analytics_by_team, notes
