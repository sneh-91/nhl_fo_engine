from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MergeNote(BaseModel):
    code: str
    detail: str


class SourceCoverage(BaseModel):
    nhl_available: bool = False
    capwages_available: bool = False
    capwages_match_strategy: Literal["nhl_id", "slug", "name", "manual", "none"] = "none"
    active_contract_found: bool = False
    notes: list[MergeNote] = Field(default_factory=list)


class PlayerIdentity(BaseModel):
    nhl_id: int | None = None
    capwages_slug: str | None = None
    nhl_player_slug: str | None = None
    full_name: str
    normalized_name: str


class PlayerProfile(BaseModel):
    is_active: bool | None = None
    team_name: str | None = None
    team_abbrev: str | None = None
    team_id: int | None = None
    position: str | None = None
    capwages_position_detail: str | None = None
    shoots_catches: str | None = None
    hand: str | None = None
    jersey_number: int | None = None
    birth_date: str | None = None
    birth_city: str | None = None
    birth_state_province: str | None = None
    birth_country: str | None = None
    nationality: str | None = None
    height_inches: int | None = None
    height_centimeters: int | None = None
    weight_pounds: int | None = None
    weight_kilograms: int | None = None
    headshot_url: str | None = None
    hero_image_url: str | None = None


class ContractSeason(BaseModel):
    season: str
    clause: str | None = None
    cap_hit: int | None = None
    aav: int | None = None
    performance_bonuses: int | None = None
    signing_bonuses: int | None = None
    base_salary: int | None = None
    total_salary: int | None = None
    minors_salary: int | None = None


class ContractRecord(BaseModel):
    contract_type: str | None = None
    contract_length: str | None = None
    contract_value: int | None = None
    expiry_status: str | None = None
    signing_team: str | None = None
    signing_date: str | None = None
    signed_by: str | None = None
    seasons: list[ContractSeason] = Field(default_factory=list)


class ContractSnapshot(BaseModel):
    current_season_label: str
    active_contract: ContractRecord | None = None
    contract_history: list[ContractRecord] = Field(default_factory=list)


class NormalizedPlayer(BaseModel):
    identity: PlayerIdentity
    profile: PlayerProfile
    contract: ContractSnapshot
    source_coverage: SourceCoverage


class BasicStats(BaseModel):
    season_id: int | None = None
    games_played: int | None = None
    goals: int | None = None
    assists: int | None = None
    points: int | None = None
    shots: int | None = None
    shooting_pct: float | None = None
    plus_minus: int | None = None
    avg_toi: str | None = None


class SkaterStats(BaseModel):
    season_id: int | None = None
    games_played: int | None = None
    goals: int | None = None
    assists: int | None = None
    points: int | None = None
    shots: int | None = None
    shooting_pct: float | None = None
    plus_minus: int | None = None
    avg_toi: str | None = None


class GoalieStats(BaseModel):
    season_id: int | None = None
    games_played: int | None = None
    wins: int | None = None
    losses: int | None = None
    ot_losses: int | None = None
    save_pct: float | None = None
    goals_against_avg: float | None = None
    shutouts: int | None = None
    shots_against: int | None = None
    goals_against: int | None = None
    time_on_ice: str | None = None


class RecentForm(BaseModel):
    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0


class GoalieRecentForm(BaseModel):
    games: int = 0
    wins: int = 0
    losses: int = 0
    ot_losses: int = 0
    save_pct: float | None = None
    goals_against_avg: float | None = None
    shots_against: int = 0
    goals_against: int = 0
    time_on_ice: str | None = None


class ActiveContractView(BaseModel):
    current_season_label: str
    contract_type: str | None = None
    expiry_status: str | None = None
    current_clause: str | None = None
    current_cap_hit: int | None = None
    current_aav: int | None = None
    years_remaining: int | None = None
    has_clause: bool = False
    signing_bonus_heavy: bool = False
    active_season: ContractSeason | None = None


class ToolPlayerData(BaseModel):
    identity: PlayerIdentity
    profile: PlayerProfile
    contract: ContractSnapshot
    active_contract: ActiveContractView
    player_type: Literal["skater", "goalie"] = "skater"
    stats_context: Literal["regular_season", "playoffs", "both"] = "regular_season"
    stats: BasicStats = Field(default_factory=BasicStats)
    regular_season_stats: BasicStats | None = None
    playoff_stats: BasicStats | None = None
    skater_stats: SkaterStats | None = None
    goalie_stats: GoalieStats | None = None
    regular_season_skater_stats: SkaterStats | None = None
    playoff_skater_stats: SkaterStats | None = None
    regular_season_goalie_stats: GoalieStats | None = None
    playoff_goalie_stats: GoalieStats | None = None
    recent_form: RecentForm = Field(default_factory=RecentForm)
    goalie_recent_form: GoalieRecentForm | None = None
    source_coverage: SourceCoverage


class PlayerToolQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player: str | None = None
    nhl_id: int | None = None
    season_type: Literal["regular_season", "playoffs", "both"] = "regular_season"

    @model_validator(mode="after")
    def validate_identifier(self) -> "PlayerToolQuery":
        if self.player is None and self.nhl_id is None:
            raise ValueError("Either player or nhl_id must be provided.")
        return self


class PlayerSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player: str | None = None
    season_type: Literal["regular_season", "playoffs"] = "regular_season"
    position: str | None = None
    shoots_catches: Literal["L", "R"] | None = None
    team: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    aav_min: int | None = None
    aav_max: int | None = None
    years_remaining_min: int | None = None
    years_remaining_max: int | None = None
    expiry_status: str | None = None
    clause_required: bool = False
    games_played_min: int | None = None
    goals_min: int | None = None
    assists_min: int | None = None
    points_min: int | None = None
    shots_min: int | None = None
    wins_min: int | None = None
    save_pct_min: float | None = None
    gaa_max: float | None = None
    shutouts_min: int | None = None
    sort_by: Literal[
        "points_desc",
        "goals_desc",
        "wins_desc",
        "save_pct_desc",
        "gaa_asc",
        "shutouts_desc",
        "age_asc",
        "age_desc",
        "aav_asc",
        "aav_desc",
        "term_asc",
        "term_desc",
    ] = "points_desc"
    limit: int = Field(default=10, ge=1, le=50)


class PlayerProfileToolResult(BaseModel):
    identity: PlayerIdentity
    profile: PlayerProfile
    player_type: Literal["skater", "goalie"] = "skater"
    stats_context: Literal["regular_season", "playoffs", "both"] = "regular_season"
    stats: BasicStats = Field(default_factory=BasicStats)
    regular_season_stats: BasicStats | None = None
    playoff_stats: BasicStats | None = None
    recent_form: RecentForm = Field(default_factory=RecentForm)
    skater_stats: SkaterStats | None = None
    goalie_stats: GoalieStats | None = None
    regular_season_skater_stats: SkaterStats | None = None
    playoff_skater_stats: SkaterStats | None = None
    regular_season_goalie_stats: GoalieStats | None = None
    playoff_goalie_stats: GoalieStats | None = None
    goalie_recent_form: GoalieRecentForm | None = None
    source_coverage: SourceCoverage
    limitations: list[str] = Field(default_factory=list)


class PlayerContractToolResult(BaseModel):
    identity: PlayerIdentity
    contract: ContractSnapshot
    active_contract: ActiveContractView
    source_coverage: SourceCoverage
    limitations: list[str] = Field(default_factory=list)


class PlayerSummaryDataResult(BaseModel):
    player: ToolPlayerData
    limitations: list[str] = Field(default_factory=list)


class PlayerSearchResult(BaseModel):
    filters: PlayerSearchFilters
    total_matches: int
    players: list[ToolPlayerData] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SkaterLeaderboardEntry(BaseModel):
    rank: int
    nhl_id: int
    full_name: str
    team_abbrev: str | None = None
    position: str | None = None
    headshot_url: str | None = None
    value: float | int


class SkaterLeaderboardResult(BaseModel):
    season_id: int
    season_type: Literal["regular_season", "playoffs"]
    category: Literal[
        "points",
        "goals",
        "assists",
        "plus_minus",
        "power_play_goals",
        "short_handed_goals",
        "penalty_minutes",
        "faceoff_pct",
        "time_on_ice",
    ]
    category_label: str
    leaders: list[SkaterLeaderboardEntry] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class GoalieLeaderboardEntry(BaseModel):
    rank: int
    nhl_id: int
    full_name: str
    team_abbrev: str | None = None
    position: str | None = None
    headshot_url: str | None = None
    value: float | int


class GoalieLeaderboardResult(BaseModel):
    season_id: int
    season_type: Literal["regular_season", "playoffs"]
    category: Literal[
        "wins",
        "shutouts",
        "save_pct",
        "goals_against_avg",
    ]
    category_label: str
    leaders: list[GoalieLeaderboardEntry] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ComparisonFact(BaseModel):
    category: str
    player_a_value: str | int | float | bool | None = None
    player_b_value: str | int | float | bool | None = None
    winner: Literal["player_a", "player_b", "tie", "none"] = "none"
    lower_is_better: bool | None = None


class PlayerComparisonResult(BaseModel):
    player_a: ToolPlayerData
    player_b: ToolPlayerData
    comparisons: list[ComparisonFact] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PlayerComparisonQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_a: str | None = None
    player_a_nhl_id: int | None = None
    player_b: str | None = None
    player_b_nhl_id: int | None = None
    season_type: Literal["regular_season", "playoffs"] = "regular_season"

    @model_validator(mode="after")
    def validate_players(self) -> "PlayerComparisonQuery":
        if self.player_a is None and self.player_a_nhl_id is None:
            raise ValueError("Either player_a or player_a_nhl_id must be provided.")
        if self.player_b is None and self.player_b_nhl_id is None:
            raise ValueError("Either player_b or player_b_nhl_id must be provided.")
        return self


class SkaterLeaderboardQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_type: Literal["regular_season", "playoffs"] = "regular_season"
    category: Literal[
        "points",
        "goals",
        "assists",
        "plus_minus",
        "power_play_goals",
        "short_handed_goals",
        "penalty_minutes",
        "faceoff_pct",
        "time_on_ice",
    ]
    limit: int = Field(default=10, ge=1, le=50)


class GoalieLeaderboardQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_type: Literal["regular_season", "playoffs"] = "regular_season"
    category: Literal[
        "wins",
        "shutouts",
        "save_pct",
        "goals_against_avg",
    ]
    limit: int = Field(default=10, ge=1, le=50)


class ToolInvocationRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


class OrchestratedAnswerResult(BaseModel):
    model: str
    answer_text: str
    tool_invocations: list[ToolInvocationRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    response_id: str | None = None


class AskQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_question(self) -> "AskQuestionRequest":
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("Question must not be empty.")
        return self


class AskQuestionSupportData(BaseModel):
    tool_invocations: list[ToolInvocationRecord] = Field(default_factory=list)


class AskQuestionResponse(BaseModel):
    question: str
    answer_text: str
    limitations: list[str] = Field(default_factory=list)
    support_data: AskQuestionSupportData
    model: str
    response_id: str | None = None


class ApiErrorResponse(BaseModel):
    detail: str


class OrchestratorDiagnosticsResponse(BaseModel):
    app_version: str
    openai_answer_model: str
    openai_classifier_model: str
    openai_configured: bool
    openai_max_tool_rounds: int
    openai_max_output_tokens: int
