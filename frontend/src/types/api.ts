export type HealthResponse = {
  status: string;
};

export type AskQuestionRequest = {
  question: string;
  question_mode?: "player_team_info" | "nhl_rules";
};

export type MergeNote = {
  code: string;
  detail: string;
};

export type SourceCoverage = {
  nhl_available: boolean;
  capwages_available: boolean;
  capwages_match_strategy: string;
  active_contract_found: boolean;
  notes: MergeNote[];
};

export type TeamSourceCoverage = {
  nhl_available: boolean;
  notes: MergeNote[];
};

export type PlayerIdentity = {
  nhl_id: number | null;
  full_name: string;
};

export type PlayerProfile = {
  team_name: string | null;
  team_abbrev: string | null;
  position: string | null;
  capwages_position_detail: string | null;
  shoots_catches: string | null;
  birth_date: string | null;
};

export type ContractSeason = {
  season: string;
  clause: string | null;
  cap_hit: number | null;
  aav: number | null;
};

export type ActiveContract = {
  current_clause: string | null;
  current_cap_hit: number | null;
  current_aav: number | null;
  years_remaining: number | null;
  expiry_status: string | null;
  active_season: ContractSeason | null;
};

export type PlayerType = "skater" | "goalie";

export type StatsContext = "regular_season" | "playoffs" | "both";

export type BasicStats = {
  season_id?: number | null;
  games_played: number | null;
  goals: number | null;
  assists: number | null;
  points: number | null;
  shots: number | null;
  plus_minus: number | null;
  avg_toi: string | null;
};

export type RecentForm = {
  games: number;
  goals: number;
  assists: number;
  points: number;
};

export type SkaterStats = BasicStats;

export type SkaterAnalytics = {
  season_id?: number | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  on_ice_expected_goals_pct: number | null;
  relative_expected_goals_pct: number | null;
  on_ice_corsi_pct: number | null;
};

export type GoalieStats = {
  season_id?: number | null;
  games_played: number | null;
  wins: number | null;
  losses: number | null;
  ot_losses: number | null;
  save_pct: number | null;
  goals_against_avg: number | null;
  shutouts: number | null;
  shots_against: number | null;
  goals_against: number | null;
  time_on_ice: string | null;
};

export type GoalieAnalytics = {
  season_id?: number | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  goals_saved_above_expected: number | null;
  goals_saved_above_expected_per_60: number | null;
};

export type MoneyPuckCoverage = {
  available: boolean;
  season_id?: number | null;
  season_type?: "regular_season" | "playoffs" | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  notes: MergeNote[];
};

export type GoalieRecentForm = {
  games: number;
  wins: number;
  losses: number;
  ot_losses: number;
  save_pct: number | null;
  goals_against_avg: number | null;
  shots_against: number;
  goals_against: number;
  time_on_ice: string | null;
};

export type TeamIdentity = {
  team_abbrev: string;
  team_name: string | null;
  team_id: number | null;
  team_logo_url: string | null;
};

export type TeamStats = {
  season_id?: number | null;
  season_type: "regular_season" | "playoffs" | null;
  games_played: number | null;
  wins: number | null;
  losses: number | null;
  ot_losses: number | null;
  points: number | null;
  points_pct: number | null;
  goals_for: number | null;
  goals_against: number | null;
  power_play_pct: number | null;
  penalty_kill_pct: number | null;
  goals_for_pct: number | null;
  expected_goals_for_pct: number | null;
  corsi_pct: number | null;
  pdo: number | null;
};

export type TeamAnalytics = {
  season_id?: number | null;
  season_type: "regular_season" | "playoffs" | null;
  team_abbrev: string | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  games_played: number | null;
  goals_for: number | null;
  goals_against: number | null;
  power_play_pct: number | null;
  penalty_kill_pct: number | null;
  goals_for_pct: number | null;
  expected_goals_for_pct: number | null;
  corsi_pct: number | null;
  pdo: number | null;
};

export type ToolTeamData = {
  identity: TeamIdentity;
  stats: TeamStats;
  moneypuck_analytics: TeamAnalytics | null;
  source_coverage: TeamSourceCoverage;
  moneypuck_coverage: MoneyPuckCoverage;
};

export type ToolPlayerData = {
  identity: PlayerIdentity;
  profile: PlayerProfile;
  active_contract: ActiveContract;
  player_type: PlayerType;
  stats_context: StatsContext;
  stats: BasicStats;
  regular_season_stats?: BasicStats | null;
  playoff_stats?: BasicStats | null;
  skater_stats?: SkaterStats | null;
  goalie_stats?: GoalieStats | null;
  regular_season_skater_stats?: SkaterStats | null;
  playoff_skater_stats?: SkaterStats | null;
  regular_season_goalie_stats?: GoalieStats | null;
  playoff_goalie_stats?: GoalieStats | null;
  recent_form: RecentForm;
  goalie_recent_form?: GoalieRecentForm | null;
  skater_analytics?: SkaterAnalytics | null;
  goalie_analytics?: GoalieAnalytics | null;
  moneypuck_coverage: MoneyPuckCoverage;
  source_coverage: SourceCoverage;
};

export type ComparisonFact = {
  category: string;
  player_a_value: string | number | boolean | null;
  player_b_value: string | number | boolean | null;
};

export type SearchResult = {
  total_matches: number;
  players: ToolPlayerData[];
};

export type ComparisonResult = {
  player_a: ToolPlayerData;
  player_b: ToolPlayerData;
  comparisons: ComparisonFact[];
};

export type LeaderboardEntry = {
  rank: number;
  nhl_id: number;
  full_name: string;
  team_abbrev: string | null;
  position: string | null;
  headshot_url: string | null;
  value: number;
};

export type SkaterLeaderboardResult = {
  season_id: number;
  season_type: "regular_season" | "playoffs";
  category: string;
  category_label: string;
  leaders: LeaderboardEntry[];
};

export type GoalieLeaderboardResult = {
  season_id: number;
  season_type: "regular_season" | "playoffs";
  category: string;
  category_label: string;
  leaders: LeaderboardEntry[];
};

export type PlayerProfileToolResult = {
  identity: PlayerIdentity;
  profile: PlayerProfile;
  player_type: PlayerType;
  stats_context: StatsContext;
  stats: BasicStats;
  regular_season_stats?: BasicStats | null;
  playoff_stats?: BasicStats | null;
  recent_form: RecentForm;
  skater_stats?: SkaterStats | null;
  goalie_stats?: GoalieStats | null;
  regular_season_skater_stats?: SkaterStats | null;
  playoff_skater_stats?: SkaterStats | null;
  regular_season_goalie_stats?: GoalieStats | null;
  playoff_goalie_stats?: GoalieStats | null;
  goalie_recent_form?: GoalieRecentForm | null;
  skater_analytics?: SkaterAnalytics | null;
  goalie_analytics?: GoalieAnalytics | null;
  moneypuck_coverage: MoneyPuckCoverage;
  source_coverage: SourceCoverage;
};

export type PlayerContractToolResult = {
  identity: PlayerIdentity;
  active_contract: ActiveContract;
  source_coverage: SourceCoverage;
};

export type PlayerSummaryResult = {
  player: ToolPlayerData;
};

export type TeamSummaryResult = {
  team: ToolTeamData;
};

export type ToolInvocation = {
  tool_name: string;
  arguments: Record<string, unknown>;
  output: {
    ok: boolean;
    result?:
      | SkaterLeaderboardResult
      | GoalieLeaderboardResult
      | SearchResult
      | ComparisonResult
      | PlayerProfileToolResult
      | PlayerContractToolResult
      | PlayerSummaryResult
      | TeamSummaryResult;
    error?: {
      type: string;
      message: string;
    };
  };
};

export type DisplayPlayerItem = {
  kind: "player";
  nhl_id: number | null;
  full_name: string;
  title: string | null;
  reason: string | null;
};

export type DisplayTeamItem = {
  kind: "team";
  team_abbrev: string;
  title: string | null;
  reason: string | null;
};

export type DisplayLeaderboardItem = {
  kind: "leaderboard";
  title: string;
  tool_invocation_index: number;
  player_ids: number[];
  reason: string | null;
};

export type DisplayItem = DisplayPlayerItem | DisplayTeamItem | DisplayLeaderboardItem;

export type AskQuestionResponse = {
  question: string;
  answer_text: string;
  limitations: string[];
  support_data: {
    display_items: DisplayItem[];
    tool_invocations: ToolInvocation[];
  };
};
