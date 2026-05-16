from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from ..config import Settings
from ..models import GoalieAnalytics, MergeNote, MoneyPuckCoverage, SkaterAnalytics


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


@dataclass
class MoneyPuckSnapshot:
    coverage: MoneyPuckCoverage
    skaters: dict[int, SkaterAnalytics] = field(default_factory=dict)
    goalies: dict[int, GoalieAnalytics] = field(default_factory=dict)


class MoneyPuckService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._cached_snapshot: MoneyPuckSnapshot | None = None
        self._cached_at: float = 0.0

    def get_skater_analytics(self, player_id: int) -> SkaterAnalytics | None:
        return self._get_snapshot().skaters.get(player_id)

    def get_goalie_analytics(self, player_id: int) -> GoalieAnalytics | None:
        return self._get_snapshot().goalies.get(player_id)

    def get_coverage(self) -> MoneyPuckCoverage:
        return self._get_snapshot().coverage.model_copy(deep=True)

    def refresh(self) -> MoneyPuckSnapshot:
        with self._lock:
            snapshot = self._load_snapshot()
            self._cached_snapshot = snapshot
            self._cached_at = time.time()
            return snapshot

    def _get_snapshot(self) -> MoneyPuckSnapshot:
        with self._lock:
            if (
                self._cached_snapshot is None
                or (time.time() - self._cached_at) >= self._settings.moneypuck_cache_ttl_seconds
            ):
                self._cached_snapshot = self._load_snapshot()
                self._cached_at = time.time()
            return self._cached_snapshot

    def _load_snapshot(self) -> MoneyPuckSnapshot:
        coverage = MoneyPuckCoverage(
            available=False,
            season_id=2025,
            situation="all",
        )
        if not self._settings.moneypuck_enabled:
            coverage.notes.append(
                MergeNote(
                    code="moneypuck_disabled",
                    detail="MoneyPuck analytics are disabled in settings.",
                )
            )
            return MoneyPuckSnapshot(coverage=coverage)

        skaters, skater_notes = self._load_skaters(self._settings.moneypuck_2025_regular_skaters_path)
        goalies, goalie_notes = self._load_goalies(self._settings.moneypuck_2025_regular_goalies_path)
        coverage.available = bool(skaters or goalies)
        coverage.notes.extend(skater_notes)
        coverage.notes.extend(goalie_notes)
        return MoneyPuckSnapshot(
            coverage=coverage,
            skaters=skaters,
            goalies=goalies,
        )

    def _load_skaters(self, path: Path) -> tuple[dict[int, SkaterAnalytics], list[MergeNote]]:
        notes: list[MergeNote] = []
        if not path.exists():
            notes.append(
                MergeNote(
                    code="moneypuck_skaters_missing",
                    detail=f"MoneyPuck skater file was not found at {path}.",
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
                    detail=f"MoneyPuck skater file could not be parsed: {error}",
                )
            )
            return {}, notes

        if not analytics_by_player:
            notes.append(
                MergeNote(
                    code="moneypuck_skaters_empty",
                    detail="MoneyPuck skater file loaded but no 'all' situation rows were found.",
                )
            )
        return analytics_by_player, notes

    def _load_goalies(self, path: Path) -> tuple[dict[int, GoalieAnalytics], list[MergeNote]]:
        notes: list[MergeNote] = []
        if not path.exists():
            notes.append(
                MergeNote(
                    code="moneypuck_goalies_missing",
                    detail=f"MoneyPuck goalie file was not found at {path}.",
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
                    detail=f"MoneyPuck goalie file could not be parsed: {error}",
                )
            )
            return {}, notes

        if not analytics_by_player:
            notes.append(
                MergeNote(
                    code="moneypuck_goalies_empty",
                    detail="MoneyPuck goalie file loaded but no 'all' situation rows were found.",
                )
            )
        return analytics_by_player, notes
