from __future__ import annotations

import json
from threading import Lock

from pydantic import ValidationError

from ..config import Settings
from ..models import TeamContextEntry, TeamContextSnapshot


class TeamContextService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._cached_snapshot: TeamContextSnapshot | None = None

    def get_context(self, team_abbrev: str) -> TeamContextEntry | None:
        snapshot = self._get_snapshot()
        context = snapshot.teams.get(team_abbrev.strip().upper())
        if context is None:
            return None
        return context.model_copy(deep=True)

    def refresh(self) -> TeamContextSnapshot:
        with self._lock:
            snapshot = self._load_snapshot()
            self._cached_snapshot = snapshot
            return snapshot.model_copy(deep=True)

    def _get_snapshot(self) -> TeamContextSnapshot:
        with self._lock:
            if self._cached_snapshot is None:
                self._cached_snapshot = self._load_snapshot()
            return self._cached_snapshot

    def _load_snapshot(self) -> TeamContextSnapshot:
        path = self._settings.team_context_2025_26_path
        if not path.exists():
            return TeamContextSnapshot(
                season_id=20252026,
                last_updated="",
                teams={},
            )

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            snapshot = TeamContextSnapshot.model_validate(payload)
        except json.JSONDecodeError as error:
            raise ValueError(f"Team context file at {path} is not valid JSON: {error}") from error
        except OSError as error:
            raise ValueError(f"Team context file at {path} could not be read: {error}") from error
        except ValidationError as error:
            raise ValueError(f"Team context file at {path} failed validation: {error}") from error

        return self._with_entry_metadata(snapshot)

    def _with_entry_metadata(self, snapshot: TeamContextSnapshot) -> TeamContextSnapshot:
        teams = {
            team_abbrev.strip().upper(): entry.model_copy(
                update={"last_updated": snapshot.last_updated},
                deep=True,
            )
            for team_abbrev, entry in snapshot.teams.items()
        }
        return snapshot.model_copy(update={"teams": teams}, deep=True)
