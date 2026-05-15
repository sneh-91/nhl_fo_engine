from __future__ import annotations

import unicodedata
from datetime import date

from ..errors import IdentityResolutionError
from ..models import (
    ContractRecord,
    ContractSeason,
    ContractSnapshot,
    MergeNote,
    NormalizedPlayer,
    PlayerIdentity,
    PlayerProfile,
    SourceCoverage,
)


def _normalize_name(value: str) -> str:
    collapsed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(character if character.isalnum() or character.isspace() else " " for character in collapsed)
    return " ".join(stripped.split())


def _default_text(value: dict | None) -> str | None:
    if not isinstance(value, dict):
        return None
    default_value = value.get("default")
    return default_value.strip() if isinstance(default_value, str) and default_value.strip() else None


def _full_name_from_nhl_landing(landing: dict) -> str:
    first_name = _default_text(landing.get("firstName")) or ""
    last_name = _default_text(landing.get("lastName")) or ""
    return " ".join(part for part in (first_name, last_name) if part).strip()


def _derive_capwages_slug(player_slug: str | None) -> str | None:
    if not player_slug:
        return None

    pieces = player_slug.split("-")
    if pieces and pieces[-1].isdigit():
        candidate = "-".join(pieces[:-1]).strip()
        return candidate or None

    return player_slug.strip() or None


def _canonical_position_from_capwages(position: str | None) -> str | None:
    if not position:
        return None

    normalized = position.strip().upper()
    if normalized in {"LD", "RD", "D"}:
        return "D"
    if normalized in {"LW", "RW", "W"}:
        return "W"
    if normalized in {"C", "G"}:
        return normalized
    return normalized


def _build_contract_record(contract: dict) -> ContractRecord:
    seasons = [
        ContractSeason(
            season=str(season.get("season", "")),
            clause=season.get("clause"),
            cap_hit=season.get("capHit"),
            aav=season.get("aav"),
            performance_bonuses=season.get("performanceBonuses"),
            signing_bonuses=season.get("signingBonuses"),
            base_salary=season.get("baseSalary"),
            total_salary=season.get("totalSalary"),
            minors_salary=season.get("minorsSalary"),
        )
        for season in contract.get("seasons", [])
        if isinstance(season, dict)
    ]
    return ContractRecord(
        contract_type=contract.get("contractType"),
        contract_length=contract.get("contractLength"),
        contract_value=contract.get("contractValue"),
        expiry_status=contract.get("expiryStatus"),
        signing_team=contract.get("signingTeam"),
        signing_date=contract.get("signingDate"),
        signed_by=contract.get("signedBy"),
        seasons=seasons,
    )


class PlayerNormalizer:
    def __init__(self, *, today: date | None = None) -> None:
        self._today = today or date.today()

    def current_cap_season_label(self) -> str:
        start_year = self._today.year if self._today.month >= 7 else self._today.year - 1
        return f"{start_year}-{str(start_year + 1)[-2:]}"

    def match_capwages_detail(self, nhl_landing: dict, capwages_detail: dict) -> SourceCoverage:
        coverage = SourceCoverage(
            nhl_available=bool(nhl_landing),
            capwages_available=bool(capwages_detail.get("data")),
        )

        if not nhl_landing:
            coverage.notes.append(
                MergeNote(code="missing_nhl", detail="NHL landing payload was not provided.")
            )
            return coverage

        cap_data = capwages_detail.get("data")
        if not isinstance(cap_data, dict):
            coverage.notes.append(
                MergeNote(code="missing_capwages", detail="CapWages detail payload was not provided.")
            )
            return coverage

        nhl_id = str(nhl_landing.get("playerId") or "").strip()
        capwages_nhl_id = str(cap_data.get("nhlId") or "").strip()
        nhl_slug = _derive_capwages_slug(nhl_landing.get("playerSlug"))
        capwages_slug = cap_data.get("slug")
        nhl_name = _full_name_from_nhl_landing(nhl_landing)
        capwages_name = str(cap_data.get("name") or "").strip()

        if nhl_id and capwages_nhl_id and nhl_id == capwages_nhl_id:
            coverage.capwages_match_strategy = "nhl_id"
            return coverage

        if nhl_slug and capwages_slug and nhl_slug == capwages_slug:
            coverage.capwages_match_strategy = "slug"
            coverage.notes.append(
                MergeNote(
                    code="match_without_explicit_id",
                    detail="CapWages detail matched by slug because explicit shared nhlId was unavailable or different.",
                )
            )
            return coverage

        if nhl_name and capwages_name and _normalize_name(nhl_name) == _normalize_name(capwages_name):
            coverage.capwages_match_strategy = "name"
            coverage.notes.append(
                MergeNote(
                    code="match_without_explicit_id",
                    detail="CapWages detail matched by normalized full name.",
                )
            )
            return coverage

        raise IdentityResolutionError(
            "CapWages detail did not match the NHL landing payload by nhlId, slug, or normalized name."
        )

    def match_capwages_directory_entry(self, nhl_landing: dict, entry: dict) -> str:
        nhl_id = str(nhl_landing.get("playerId") or "").strip()
        capwages_nhl_id = str(entry.get("nhlId") or "").strip()
        if nhl_id and capwages_nhl_id and nhl_id == capwages_nhl_id:
            return "nhl_id"

        nhl_slug = _derive_capwages_slug(nhl_landing.get("playerSlug"))
        entry_slug = str(entry.get("slug") or "").strip()
        if nhl_slug and entry_slug and nhl_slug == entry_slug:
            return "slug"

        nhl_name = _full_name_from_nhl_landing(nhl_landing)
        entry_name = str(entry.get("name") or "").strip()
        if nhl_name and entry_name and _normalize_name(nhl_name) == _normalize_name(entry_name):
            return "name"

        return "none"

    def resolve_capwages_directory_match(self, nhl_landing: dict, capwages_players_payload: dict) -> dict | None:
        entries = capwages_players_payload.get("data")
        if not isinstance(entries, list):
            raise IdentityResolutionError("CapWages players payload did not contain a list in data.")

        ranked_matches: dict[str, list[dict]] = {"nhl_id": [], "slug": [], "name": []}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            strategy = self.match_capwages_directory_entry(nhl_landing, entry)
            if strategy in ranked_matches:
                ranked_matches[strategy].append(entry)

        for strategy in ("nhl_id", "slug", "name"):
            matches = ranked_matches[strategy]
            if len(matches) == 1:
                return {
                    "strategy": strategy,
                    "entry": matches[0],
                }
            if len(matches) > 1:
                raise IdentityResolutionError(
                    f"CapWages directory produced multiple matches using strategy '{strategy}'."
                )

        return None

    def normalize_player(self, nhl_landing: dict, capwages_detail: dict | None = None) -> NormalizedPlayer:
        nhl_name = _full_name_from_nhl_landing(nhl_landing)
        nhl_slug = str(nhl_landing.get("playerSlug") or "").strip() or None
        derived_capwages_slug = _derive_capwages_slug(nhl_slug)
        cap_data = capwages_detail.get("data") if isinstance(capwages_detail, dict) else None
        cap_team = str(cap_data.get("team") or "").strip() if isinstance(cap_data, dict) else ""
        cap_position = str(cap_data.get("position") or "").strip() if isinstance(cap_data, dict) else ""
        cap_hand = str(cap_data.get("physicalAttributes", {}).get("hand") or "").strip() if isinstance(cap_data, dict) else ""
        cap_birth_date = str(cap_data.get("personalInfo", {}).get("birthDate") or "").strip() if isinstance(cap_data, dict) else ""
        cap_nationality = str(cap_data.get("personalInfo", {}).get("nationality") or "").strip() if isinstance(cap_data, dict) else ""
        cap_height_cm = cap_data.get("physicalAttributes", {}).get("height", {}).get("metric") if isinstance(cap_data, dict) else None
        cap_weight_kg = cap_data.get("physicalAttributes", {}).get("weight", {}).get("metric") if isinstance(cap_data, dict) else None
        cap_jersey_number = cap_data.get("jerseyNumber") if isinstance(cap_data, dict) else None
        coverage = (
            self.match_capwages_detail(nhl_landing, capwages_detail)
            if isinstance(cap_data, dict)
            else SourceCoverage(
                nhl_available=bool(nhl_landing),
                capwages_available=False,
                notes=[MergeNote(code="missing_capwages", detail="No CapWages detail was provided for this player.")],
            )
        )

        cap_name = str(cap_data.get("name") or "").strip() if isinstance(cap_data, dict) else ""
        full_name = cap_name or nhl_name
        normalized_name = _normalize_name(full_name)

        profile = PlayerProfile(
            is_active=nhl_landing.get("isActive"),
            team_name=cap_team or _default_text(nhl_landing.get("fullTeamName")),
            team_abbrev=str(nhl_landing.get("currentTeamAbbrev") or "") or None,
            team_id=nhl_landing.get("currentTeamId"),
            position=str(nhl_landing.get("position") or _canonical_position_from_capwages(cap_position) or "") or None,
            capwages_position_detail=cap_position or None,
            shoots_catches=str(nhl_landing.get("shootsCatches") or "") or None,
            hand=cap_hand or None,
            jersey_number=cap_jersey_number or nhl_landing.get("sweaterNumber"),
            birth_date=cap_birth_date or (str(nhl_landing.get("birthDate") or "") or None),
            birth_city=_default_text(nhl_landing.get("birthCity")),
            birth_state_province=_default_text(nhl_landing.get("birthStateProvince")),
            birth_country=str(nhl_landing.get("birthCountry") or "") or None,
            nationality=cap_nationality or (str(nhl_landing.get("birthCountry") or "") or None),
            height_inches=nhl_landing.get("heightInInches"),
            height_centimeters=nhl_landing.get("heightInCentimeters") or cap_height_cm,
            weight_pounds=nhl_landing.get("weightInPounds"),
            weight_kilograms=nhl_landing.get("weightInKilograms") or cap_weight_kg,
            headshot_url=str(nhl_landing.get("headshot") or "") or None,
            hero_image_url=str(nhl_landing.get("heroImage") or "") or None,
        )

        if isinstance(cap_data, dict):
            personal_birth_date = str(cap_data.get("personalInfo", {}).get("birthDate") or "").strip()
            if personal_birth_date and profile.birth_date and personal_birth_date != profile.birth_date:
                coverage.notes.append(
                    MergeNote(
                        code="birth_date_conflict",
                        detail="NHL and CapWages birth dates differed; canonical birth_date prefers NHL.",
                    )
                )

            cap_team = str(cap_data.get("team") or "").strip()
            if cap_team and profile.team_name and cap_team != profile.team_name:
                coverage.notes.append(
                    MergeNote(
                        code="team_name_conflict",
                        detail="NHL and CapWages team names differed; canonical team_name prefers CapWages when present.",
                    )
                )

        contract_snapshot = self._normalize_contract_snapshot(cap_data, coverage)
        canonical_capwages_slug = (
            str(cap_data.get("slug") or "").strip() or derived_capwages_slug
            if isinstance(cap_data, dict)
            else derived_capwages_slug
        )

        return NormalizedPlayer(
            identity=PlayerIdentity(
                nhl_id=nhl_landing.get("playerId"),
                capwages_slug=canonical_capwages_slug,
                nhl_player_slug=nhl_slug,
                full_name=full_name,
                normalized_name=normalized_name,
            ),
            profile=profile,
            contract=contract_snapshot,
            source_coverage=coverage,
        )

    def _normalize_contract_snapshot(
        self,
        cap_data: dict | None,
        coverage: SourceCoverage,
    ) -> ContractSnapshot:
        current_season = self.current_cap_season_label()
        if not isinstance(cap_data, dict):
            return ContractSnapshot(current_season_label=current_season)

        history = [
            _build_contract_record(contract)
            for contract in cap_data.get("contracts", [])
            if isinstance(contract, dict)
        ]

        active_contract = None
        for contract in history:
            if any(season.season == current_season for season in contract.seasons):
                active_contract = contract
                break

        if active_contract is None and history:
            coverage.notes.append(
                MergeNote(
                    code="no_active_contract",
                    detail="CapWages contract history was found, but no contract covered the current cap season.",
                )
            )
        coverage.active_contract_found = active_contract is not None

        return ContractSnapshot(
            current_season_label=current_season,
            active_contract=active_contract,
            contract_history=history,
        )
