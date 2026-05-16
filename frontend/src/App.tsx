import { useEffect, useState, useTransition, type FormEvent } from "react";
import { apiBaseUrl } from "./config";
import { HockeyOpsLogo } from "./components/HockeyOpsLogo";

type HealthResponse = {
  status: string;
};

type AskQuestionRequest = {
  question: string;
};

type MergeNote = {
  code: string;
  detail: string;
};

type SourceCoverage = {
  nhl_available: boolean;
  capwages_available: boolean;
  capwages_match_strategy: string;
  active_contract_found: boolean;
  notes: MergeNote[];
};

type PlayerIdentity = {
  nhl_id: number | null;
  full_name: string;
};

type PlayerProfile = {
  team_name: string | null;
  team_abbrev: string | null;
  position: string | null;
  capwages_position_detail: string | null;
  shoots_catches: string | null;
  birth_date: string | null;
};

type ContractSeason = {
  season: string;
  clause: string | null;
  cap_hit: number | null;
  aav: number | null;
};

type ActiveContract = {
  current_clause: string | null;
  current_cap_hit: number | null;
  current_aav: number | null;
  years_remaining: number | null;
  expiry_status: string | null;
  active_season: ContractSeason | null;
};

type PlayerType = "skater" | "goalie";

type StatsContext = "regular_season" | "playoffs" | "both";

type BasicStats = {
  season_id?: number | null;
  games_played: number | null;
  goals: number | null;
  assists: number | null;
  points: number | null;
  shots: number | null;
  plus_minus: number | null;
  avg_toi: string | null;
};

type RecentForm = {
  games: number;
  goals: number;
  assists: number;
  points: number;
};

type SkaterStats = BasicStats;

type SkaterAnalytics = {
  season_id?: number | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  on_ice_expected_goals_pct: number | null;
  relative_expected_goals_pct: number | null;
  on_ice_corsi_pct: number | null;
};

type GoalieStats = {
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

type GoalieAnalytics = {
  season_id?: number | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  goals_saved_above_expected: number | null;
  goals_saved_above_expected_per_60: number | null;
};

type MoneyPuckCoverage = {
  available: boolean;
  season_id?: number | null;
  situation: "all" | "5on5" | "5on4" | "4on5" | "other" | null;
  notes: MergeNote[];
};

type GoalieRecentForm = {
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

type ToolPlayerData = {
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

type ComparisonFact = {
  category: string;
  player_a_value: string | number | boolean | null;
  player_b_value: string | number | boolean | null;
};

type SearchResult = {
  total_matches: number;
  players: ToolPlayerData[];
};

type ComparisonResult = {
  player_a: ToolPlayerData;
  player_b: ToolPlayerData;
  comparisons: ComparisonFact[];
};

type LeaderboardEntry = {
  rank: number;
  nhl_id: number;
  full_name: string;
  team_abbrev: string | null;
  position: string | null;
  headshot_url: string | null;
  value: number;
};

type SkaterLeaderboardResult = {
  season_id: number;
  season_type: "regular_season" | "playoffs";
  category: string;
  category_label: string;
  leaders: LeaderboardEntry[];
};

type GoalieLeaderboardResult = {
  season_id: number;
  season_type: "regular_season" | "playoffs";
  category: string;
  category_label: string;
  leaders: LeaderboardEntry[];
};

type PlayerProfileToolResult = {
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

type PlayerContractToolResult = {
  identity: PlayerIdentity;
  active_contract: ActiveContract;
  source_coverage: SourceCoverage;
};

type PlayerSummaryResult = {
  player: ToolPlayerData;
};

type ToolInvocation = {
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
      | PlayerSummaryResult;
    error?: {
      type: string;
      message: string;
    };
  };
};

type AskQuestionResponse = {
  question: string;
  answer_text: string;
  limitations: string[];
  support_data: {
    tool_invocations: ToolInvocation[];
  };
};

const sampleQuestions = [
  "Compare Aaron Ekblad vs Brandon Carlo",
  "Find right-shot defensemen on Florida under 7 million AAV",
  "Show Mitch Marner details",
  "Who are left-shot defensemen on Toronto with at least 20 points?",
];

const hiddenLimitationPills = new Set([
  "These tools search only the current active NHL roster universe built from standings and team rosters.",
  "Outputs are grounded only in NHL API data, CapWages contract data, and local MoneyPuck player analytics when available.",
  "Broader advanced analytics and team-context reasoning are not part of the current build.",
]);

const comparisonCategories = new Set([
  "games_played",
  "goals",
  "assists",
  "points",
  "goals_per_game",
  "assists_per_game",
  "points_per_game",
  "shots",
  "shooting_pct",
  "current_aav",
  "current_cap_hit",
  "years_remaining",
  "wins",
  "losses",
  "ot_losses",
  "save_pct",
  "goals_against_avg",
  "shutouts",
  "shots_against",
  "goals_against",
  "on_ice_expected_goals_pct",
  "relative_expected_goals_pct",
  "on_ice_corsi_pct",
  "goals_saved_above_expected",
  "goals_saved_above_expected_per_60",
]);

function formatCurrency(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "N/A";
  }

  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }

  return `$${value.toLocaleString()}`;
}

function formatStatValue(value: string | number | boolean | null): string {
  if (value === null) {
    return "N/A";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      return value.toFixed(3);
    }

    return value.toLocaleString();
  }

  return value;
}

function formatCategoryLabel(category: string): string {
  const customLabels: Record<string, string> = {
    on_ice_expected_goals_pct: "On-Ice xG%",
    relative_expected_goals_pct: "Relative xG%",
    on_ice_corsi_pct: "On-Ice Corsi%",
    goals_saved_above_expected: "Goals Saved Above Expected",
    goals_saved_above_expected_per_60: "Goals Saved Above Expected / 60",
  };

  if (customLabels[category]) {
    return customLabels[category];
  }

  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function calculateAge(birthDate: string | null): string {
  if (!birthDate) {
    return "N/A";
  }

  const birth = new Date(birthDate);
  if (Number.isNaN(birth.getTime())) {
    return "N/A";
  }

  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  const dayDiff = today.getDate() - birth.getDate();
  if (monthDiff < 0 || (monthDiff === 0 && dayDiff < 0)) {
    age -= 1;
  }

  return `${age}`;
}

function playerSubtitle(player: ToolPlayerData): string {
  const team = player.profile.team_abbrev ?? player.profile.team_name ?? "FA";
  const position = player.profile.capwages_position_detail ?? player.profile.position ?? "N/A";
  const shot = player.profile.shoots_catches
    ? player.player_type === "goalie"
      ? `${player.profile.shoots_catches}-catches`
      : `${player.profile.shoots_catches}-shot`
    : player.player_type === "goalie"
      ? "catches N/A"
      : "shot N/A";
  return `${team} - ${position} - ${shot}`;
}

function supportNotes(sourceCoverage: SourceCoverage): string[] {
  return sourceCoverage.notes.map((note) => note.detail);
}

function moneypuckNotes(coverage: MoneyPuckCoverage): string[] {
  return coverage.notes.map((note) => note.detail);
}

function visibleLimitations(limitations: string[]): string[] {
  return limitations.filter((item) => !hiddenLimitationPills.has(item));
}

function statsContextLabel(statsContext: StatsContext): string {
  if (statsContext === "playoffs") {
    return "Playoff line";
  }

  if (statsContext === "both") {
    return "Stat lines";
  }

  return "Season line";
}

function formatScoringLine(stats: BasicStats | null | undefined): string {
  if (!stats) {
    return "N/A";
  }

  return `${formatStatValue(stats.goals)} G / ${formatStatValue(stats.assists)} A / ${formatStatValue(stats.points)} PTS`;
}

function formatDecimal(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return value.toFixed(digits);
}

function formatSavePct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  const formatted = value.toFixed(3);
  return value >= 0 && value < 1 ? formatted.replace(/^0/, "") : formatted;
}

function formatGoalieLine(stats: GoalieStats | null | undefined): string {
  if (!stats) {
    return "N/A";
  }

  return [
    `${formatStatValue(stats.games_played)} GP`,
    `${formatStatValue(stats.wins)} W`,
    `${formatSavePct(stats.save_pct)} SV%`,
    `${formatDecimal(stats.goals_against_avg, 2)} GAA`,
    `${formatStatValue(stats.shutouts)} SO`,
  ].join(" / ");
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedDecimal(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function formatComparisonMetric(category: string, value: string | number | boolean | null): string {
  if (
    category === "on_ice_expected_goals_pct"
    || category === "relative_expected_goals_pct"
    || category === "on_ice_corsi_pct"
  ) {
    return typeof value === "number"
      ? category === "relative_expected_goals_pct"
        ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`
        : `${(value * 100).toFixed(1)}%`
      : "N/A";
  }

  if (category === "goals_saved_above_expected") {
    return typeof value === "number" ? formatSignedDecimal(value, 2) : "N/A";
  }

  if (category === "goals_saved_above_expected_per_60") {
    return typeof value === "number" ? formatSignedDecimal(value, 3) : "N/A";
  }

  return formatStatValue(value);
}

function moneyPuckLabel(coverage: MoneyPuckCoverage): string {
  if (!coverage.available) {
    return "Underlying analytics unavailable";
  }

  return coverage.situation === "all" ? "Underlying analytics" : `Underlying analytics ${coverage.situation}`;
}

function MoneyPuckPanel(props: { player: ToolPlayerData }) {
  const { player } = props;

  if (player.player_type === "goalie") {
    const analytics = player.goalie_analytics;
    return (
      <div className="micro-panel">
        <p className="micro-label">{moneyPuckLabel(player.moneypuck_coverage)}</p>
        {player.moneypuck_coverage.available && analytics ? (
          <>
            <p>GSAx: {formatSignedDecimal(analytics.goals_saved_above_expected, 2)}</p>
            <p>GSAx/60: {formatSignedDecimal(analytics.goals_saved_above_expected_per_60, 3)}</p>
          </>
        ) : (
          <p>Underlying goalie analytics are not available for this player.</p>
        )}
      </div>
    );
  }

  const analytics = player.skater_analytics;
  return (
    <div className="micro-panel">
      <p className="micro-label">{moneyPuckLabel(player.moneypuck_coverage)}</p>
      {player.moneypuck_coverage.available && analytics ? (
        <>
          <p>On-Ice xG%: {formatPct(analytics.on_ice_expected_goals_pct)}</p>
          <p>Relative xG%: {formatSignedDecimal((analytics.relative_expected_goals_pct ?? 0) * 100, 1)}%</p>
          <p>On-Ice Corsi%: {formatPct(analytics.on_ice_corsi_pct)}</p>
        </>
      ) : (
        <p>Underlying skater analytics are not available for this player.</p>
      )}
    </div>
  );
}

function playerKeyFacts(player: ToolPlayerData): Array<{ label: string; value: string }> {
  if (player.player_type === "goalie") {
    if (player.stats_context === "both") {
      return [
        { label: "Age", value: calculateAge(player.profile.birth_date) },
        { label: "RS GP", value: formatStatValue(player.regular_season_goalie_stats?.games_played ?? null) },
        { label: "RS SV%", value: formatSavePct(player.regular_season_goalie_stats?.save_pct ?? null) },
        { label: "PO GP", value: formatStatValue(player.playoff_goalie_stats?.games_played ?? null) },
        { label: "PO SV%", value: formatSavePct(player.playoff_goalie_stats?.save_pct ?? null) },
        { label: "AAV", value: formatCurrency(player.active_contract.current_aav) },
      ];
    }

    const labelPrefix = player.stats_context === "playoffs" ? "PO " : "";
    return [
      { label: "Age", value: calculateAge(player.profile.birth_date) },
      { label: `${labelPrefix}GP`, value: formatStatValue(player.goalie_stats?.games_played ?? null) },
      { label: `${labelPrefix}W`, value: formatStatValue(player.goalie_stats?.wins ?? null) },
      { label: `${labelPrefix}SV%`, value: formatSavePct(player.goalie_stats?.save_pct ?? null) },
      { label: `${labelPrefix}GAA`, value: formatDecimal(player.goalie_stats?.goals_against_avg ?? null, 2) },
      { label: "AAV", value: formatCurrency(player.active_contract.current_aav) },
    ];
  }

  if (player.stats_context === "both") {
    return [
      { label: "Age", value: calculateAge(player.profile.birth_date) },
      { label: "RS GP", value: formatStatValue(player.regular_season_stats?.games_played ?? null) },
      { label: "RS PTS", value: formatStatValue(player.regular_season_stats?.points ?? null) },
      { label: "PO GP", value: formatStatValue(player.playoff_stats?.games_played ?? null) },
      { label: "PO PTS", value: formatStatValue(player.playoff_stats?.points ?? null) },
      { label: "AAV", value: formatCurrency(player.active_contract.current_aav) },
    ];
  }

  const labelPrefix = player.stats_context === "playoffs" ? "PO " : "";
  return [
    { label: "Age", value: calculateAge(player.profile.birth_date) },
    { label: `${labelPrefix}GP`, value: formatStatValue(player.stats.games_played) },
    { label: `${labelPrefix}PTS`, value: formatStatValue(player.stats.points) },
    { label: `${labelPrefix}TOI`, value: player.stats.avg_toi ?? "N/A" },
    { label: "AAV", value: formatCurrency(player.active_contract.current_aav) },
    { label: "Term", value: formatStatValue(player.active_contract.years_remaining) },
  ];
}

function QueryExamples(props: { onSelect: (question: string) => void }) {
  return (
    <div className="sample-grid">
      {sampleQuestions.map((question) => (
        <button
          key={question}
          className="sample-card"
          type="button"
          onClick={() => props.onSelect(question)}
        >
          {question}
        </button>
      ))}
    </div>
  );
}

function PlayerCard(props: { player: ToolPlayerData }) {
  const { player } = props;

  return (
    <article className="player-card">
      <div className="player-card-header">
        <div>
          <p className="section-kicker">Player</p>
          <h4>{player.identity.full_name}</h4>
          <p className="player-subtitle">{playerSubtitle(player)}</p>
        </div>
        <div className="source-badges">
          <span className={player.source_coverage.nhl_available ? "badge badge-on" : "badge"}>
            NHL
          </span>
          <span
            className={player.source_coverage.capwages_available ? "badge badge-on" : "badge"}
          >
            CapWages
          </span>
        </div>
      </div>

      <dl className="fact-grid">
        {playerKeyFacts(player).map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>

      <div className="micro-panels">
        <div className="micro-panel">
          <p className="micro-label">{statsContextLabel(player.stats_context)}</p>
          {player.player_type === "goalie" ? (
            player.stats_context === "both" ? (
              <>
                <p>Regular season: {formatGoalieLine(player.regular_season_goalie_stats)}</p>
                <p>Playoffs: {formatGoalieLine(player.playoff_goalie_stats)}</p>
              </>
            ) : (
              <p>{formatGoalieLine(player.goalie_stats)}</p>
            )
          ) : (
            player.stats_context === "both" ? (
              <>
                <p>Regular season: {formatScoringLine(player.regular_season_stats)}</p>
                <p>Playoffs: {formatScoringLine(player.playoff_stats)}</p>
              </>
            ) : (
              <p>{formatScoringLine(player.stats)}</p>
            )
          )}
        </div>
        <div className="micro-panel">
          <p className="micro-label">Contract</p>
          <p>
            {formatCurrency(player.active_contract.current_cap_hit)} cap hit -{" "}
            {player.active_contract.current_clause ?? "No clause listed"}
          </p>
        </div>
        <MoneyPuckPanel player={player} />
      </div>

      {[...supportNotes(player.source_coverage), ...moneypuckNotes(player.moneypuck_coverage)].length > 0 ? (
        <ul className="note-list">
          {[...supportNotes(player.source_coverage), ...moneypuckNotes(player.moneypuck_coverage)].map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function SearchResultsView(props: { result: SearchResult }) {
  const { result } = props;

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Search results</h3>
        </div>
        <p className="result-meta">
          {result.total_matches} match{result.total_matches === 1 ? "" : "es"}
        </p>
      </div>
      <div className="player-grid">
        {result.players.map((player) => (
          <PlayerCard
            key={`${player.identity.nhl_id ?? player.identity.full_name}`}
            player={player}
          />
        ))}
      </div>
    </section>
  );
}

function LeaderboardView(props: { result: SkaterLeaderboardResult | GoalieLeaderboardResult }) {
  const { result } = props;
  const seasonLabel = result.season_type === "playoffs" ? "Playoffs" : "Regular season";

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>{result.category_label} leaders</h3>
        </div>
        <p className="result-meta">{seasonLabel}</p>
      </div>

      <div className="comparison-table-wrap">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Player</th>
              <th>Team</th>
              <th>Pos</th>
              <th>{result.category_label}</th>
            </tr>
          </thead>
          <tbody>
            {result.leaders.map((leader) => (
              <tr key={`${leader.nhl_id}-${leader.rank}`}>
                <td>{leader.rank}</td>
                <td>{leader.full_name}</td>
                <td>{leader.team_abbrev ?? "N/A"}</td>
                <td>{leader.position ?? "N/A"}</td>
                <td>{formatStatValue(leader.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ComparisonView(props: { result: ComparisonResult }) {
  const { result } = props;
  const relevantFacts = result.comparisons.filter((fact) => comparisonCategories.has(fact.category));

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Comparison table</h3>
        </div>
      </div>

      <div className="comparison-table-wrap">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>{result.player_a.identity.full_name}</th>
              <th>{result.player_b.identity.full_name}</th>
            </tr>
          </thead>
          <tbody>
            {relevantFacts.map((fact) => (
              <tr key={fact.category}>
                <td>{formatCategoryLabel(fact.category)}</td>
                <td>
                  {fact.category.includes("aav") || fact.category.includes("cap_hit")
                    ? formatCurrency(
                        typeof fact.player_a_value === "number" ? fact.player_a_value : null,
                      )
                    : formatComparisonMetric(fact.category, fact.player_a_value)}
                </td>
                <td>
                  {fact.category.includes("aav") || fact.category.includes("cap_hit")
                    ? formatCurrency(
                        typeof fact.player_b_value === "number" ? fact.player_b_value : null,
                      )
                    : formatComparisonMetric(fact.category, fact.player_b_value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ProfileView(props: { result: PlayerProfileToolResult }) {
  const player: ToolPlayerData = {
    identity: props.result.identity,
    profile: props.result.profile,
    active_contract: {
      current_clause: null,
      current_cap_hit: null,
      current_aav: null,
      years_remaining: null,
      expiry_status: null,
      active_season: null,
    },
    player_type: props.result.player_type,
    stats_context: props.result.stats_context,
    stats: props.result.stats,
    regular_season_stats: props.result.regular_season_stats,
    playoff_stats: props.result.playoff_stats,
    skater_stats: props.result.skater_stats,
    goalie_stats: props.result.goalie_stats,
    regular_season_skater_stats: props.result.regular_season_skater_stats,
    playoff_skater_stats: props.result.playoff_skater_stats,
    regular_season_goalie_stats: props.result.regular_season_goalie_stats,
    playoff_goalie_stats: props.result.playoff_goalie_stats,
    recent_form: props.result.recent_form,
    goalie_recent_form: props.result.goalie_recent_form,
    skater_analytics: props.result.skater_analytics,
    goalie_analytics: props.result.goalie_analytics,
    moneypuck_coverage: props.result.moneypuck_coverage,
    source_coverage: props.result.source_coverage,
  };

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Player profile</h3>
        </div>
      </div>
      <PlayerCard player={player} />
    </section>
  );
}

function ContractView(props: { result: PlayerContractToolResult }) {
  const { result } = props;

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Contract snapshot</h3>
        </div>
      </div>

      <article className="contract-card">
        <h4>{result.identity.full_name}</h4>
        <dl className="fact-grid">
          <div>
            <dt>AAV</dt>
            <dd>{formatCurrency(result.active_contract.current_aav)}</dd>
          </div>
          <div>
            <dt>Cap hit</dt>
            <dd>{formatCurrency(result.active_contract.current_cap_hit)}</dd>
          </div>
          <div>
            <dt>Clause</dt>
            <dd>{result.active_contract.current_clause ?? "N/A"}</dd>
          </div>
          <div>
            <dt>Term</dt>
            <dd>{formatStatValue(result.active_contract.years_remaining)}</dd>
          </div>
        </dl>

        {supportNotes(result.source_coverage).length > 0 ? (
          <ul className="note-list">
            {supportNotes(result.source_coverage).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
      </article>
    </section>
  );
}

function PlayerDetailsView(props: { result: PlayerSummaryResult }) {
  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Player details</h3>
        </div>
      </div>
      <PlayerCard player={props.result.player} />
    </section>
  );
}

function toProfileToolPlayer(result: PlayerProfileToolResult): ToolPlayerData {
  return {
    identity: result.identity,
    profile: result.profile,
    active_contract: {
      current_clause: null,
      current_cap_hit: null,
      current_aav: null,
      years_remaining: null,
      expiry_status: null,
      active_season: null,
    },
    player_type: result.player_type,
    stats_context: result.stats_context,
    stats: result.stats,
    regular_season_stats: result.regular_season_stats,
    playoff_stats: result.playoff_stats,
    skater_stats: result.skater_stats,
    goalie_stats: result.goalie_stats,
    regular_season_skater_stats: result.regular_season_skater_stats,
    playoff_skater_stats: result.playoff_skater_stats,
    regular_season_goalie_stats: result.regular_season_goalie_stats,
    playoff_goalie_stats: result.playoff_goalie_stats,
    recent_form: result.recent_form,
    goalie_recent_form: result.goalie_recent_form,
    skater_analytics: result.skater_analytics,
    goalie_analytics: result.goalie_analytics,
    moneypuck_coverage: result.moneypuck_coverage,
    source_coverage: result.source_coverage,
  };
}

function collectSupportPlayers(toolInvocations: ToolInvocation[]): ToolPlayerData[] {
  const players = new Map<string, ToolPlayerData>();

  function addPlayer(player: ToolPlayerData) {
    const key = player.identity.nhl_id !== null
      ? `nhl:${player.identity.nhl_id}`
      : `name:${player.identity.full_name.toLowerCase()}`;
    if (!players.has(key)) {
      players.set(key, player);
    }
  }

  for (const toolInvocation of toolInvocations) {
    if (!toolInvocation.output.ok || !toolInvocation.output.result) {
      continue;
    }

    const result = toolInvocation.output.result;
    if ("players" in result && Array.isArray(result.players)) {
      for (const player of result.players) {
        addPlayer(player);
      }
      continue;
    }

    if ("player_a" in result && "player_b" in result) {
      addPlayer(result.player_a);
      addPlayer(result.player_b);
      continue;
    }

    if ("player" in result) {
      addPlayer(result.player);
      continue;
    }

    if ("identity" in result && "profile" in result && "stats" in result && "recent_form" in result) {
      addPlayer(toProfileToolPlayer(result));
    }
  }

  return [...players.values()];
}

function MultiPlayerCardsView(props: { players: ToolPlayerData[] }) {
  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Players</h3>
        </div>
        <p className="result-meta">
          {props.players.length} player{props.players.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="player-grid">
        {props.players.map((player) => (
          <PlayerCard
            key={`${player.identity.nhl_id ?? player.identity.full_name}`}
            player={player}
          />
        ))}
      </div>
    </section>
  );
}

function ToolTrace(props: { toolInvocations: ToolInvocation[] }) {
  const supportPlayers = collectSupportPlayers(props.toolInvocations);
  const comparisonInvocation = [...props.toolInvocations]
    .reverse()
    .find((toolInvocation) => toolInvocation.tool_name === "compare_players");
  const toolInvocations = supportPlayers.length > 2
    ? props.toolInvocations
    : comparisonInvocation
      ? [comparisonInvocation]
      : props.toolInvocations;

  if (toolInvocations.length === 0) {
    return null;
  }

  return (
    <section className="panel panel-soft">
      <div className="panel-header">
        <div>
          <h2>Supporting data</h2>
        </div>
      </div>

      <div className="trace-stack">
        {supportPlayers.length > 2 ? <MultiPlayerCardsView players={supportPlayers} /> : null}
        {toolInvocations.map((toolInvocation, index) => {
          const key = `${toolInvocation.tool_name}-${index}`;

          if (supportPlayers.length > 2) {
            return null;
          }

          if (!toolInvocation.output.ok || !toolInvocation.output.result) {
            return (
              <article key={key} className="support-block support-error">
                <div className="support-block-header">
                  <div>
                    <h3>{toolInvocation.tool_name}</h3>
                  </div>
                </div>
                <p>{toolInvocation.output.error?.message ?? "Unknown tool error."}</p>
              </article>
            );
          }

          if (toolInvocation.tool_name === "search_players") {
            return (
              <SearchResultsView
                key={key}
                result={toolInvocation.output.result as SearchResult}
              />
            );
          }

          if (
            toolInvocation.tool_name === "get_skater_leaderboard"
            || toolInvocation.tool_name === "get_goalie_leaderboard"
          ) {
            return (
              <LeaderboardView
                key={key}
                result={toolInvocation.output.result as SkaterLeaderboardResult | GoalieLeaderboardResult}
              />
            );
          }

          if (toolInvocation.tool_name === "compare_players") {
            return (
              <ComparisonView
                key={key}
                result={toolInvocation.output.result as ComparisonResult}
              />
            );
          }

          if (toolInvocation.tool_name === "get_player_profile") {
            return (
              <ProfileView
                key={key}
                result={toolInvocation.output.result as PlayerProfileToolResult}
              />
            );
          }

          if (toolInvocation.tool_name === "get_player_contract") {
            return (
              <ContractView
                key={key}
                result={toolInvocation.output.result as PlayerContractToolResult}
              />
            );
          }

          if (toolInvocation.tool_name === "get_player_summary_data") {
            return (
              <PlayerDetailsView
                key={key}
                result={toolInvocation.output.result as PlayerSummaryResult}
              />
            );
          }

          return (
            <article key={key} className="support-block">
              <div className="support-block-header">
                <div>
                  <h3>{toolInvocation.tool_name}</h3>
                </div>
              </div>
              <p>This tool returned data, but the UI does not have a dedicated renderer for it yet.</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function App() {
  const [, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [question, setQuestion] = useState(sampleQuestions[0]);
  const [result, setResult] = useState<AskQuestionResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [, startTransition] = useTransition();
  const shownLimitations = result ? visibleLimitations(result.limitations) : [];

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/health`);
        if (!response.ok) {
          throw new Error(`Healthcheck failed with ${response.status}.`);
        }

        const payload = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(payload);
          setHealthError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHealthError(error instanceof Error ? error.message : "Unknown healthcheck error.");
        }
      }
    }

    void loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setSubmitError("Enter a hockey ops question first.");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion } satisfies AskQuestionRequest),
      });

      const payload = (await response.json()) as AskQuestionResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `Request failed with ${response.status}.`,
        );
      }

      startTransition(() => {
        setResult(payload as AskQuestionResponse);
      });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Unknown request error.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function applySampleQuestion(nextQuestion: string) {
    setQuestion(nextQuestion);
    setSubmitError(null);
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-brand">
            <HockeyOpsLogo className="hero-logo" />
            <p className="hero-tag">Front-office answers grounded in NHL and CapWages data.</p>
          </div>
          <h1>Ask Hockey Questions.</h1>
          <p className="lede">Search, compare, and summarize players with contract context.</p>
        </div>
        <p className="hero-source-note">Data from NHL API and CapWages</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-kicker">Question</p>
            <h2>What do you want to know?</h2>
          </div>
        </div>

        <form className="query-form" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="question">
            Hockey ops question
          </label>
          <textarea
            id="question"
            className="query-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Compare two defensemen, ask for a player summary, or search for a contract profile."
            rows={4}
          />
          <div className="query-actions">
            <button
              className={`primary-button${isSubmitting ? " is-loading" : ""}`}
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="button-loading">
                  <span className="button-spinner" aria-hidden="true" />
                  <span>Loading</span>
                </span>
              ) : (
                "Ask HockeyOps"
              )}
            </button>
          </div>
        </form>

        <QueryExamples onSelect={applySampleQuestion} />

        {submitError ? <p className="error-banner">{submitError}</p> : null}
        {healthError ? <p className="error-banner">{healthError}</p> : null}
      </section>

      {result ? (
        <>
          <section className="panel answer-panel">
            <div className="panel-header">
              <div>
                <p className="section-kicker">Answer</p>
              </div>
            </div>

            <div className="answer-copy">{result.answer_text}</div>

            {shownLimitations.length > 0 ? (
              <div className="limitations-row">
                {shownLimitations.map((limitation) => (
                  <span key={limitation} className="limitation-pill">
                    {limitation}
                  </span>
                ))}
              </div>
            ) : null}
          </section>

          <ToolTrace toolInvocations={result.support_data.tool_invocations} />
        </>
      ) : null}
    </main>
  );
}
