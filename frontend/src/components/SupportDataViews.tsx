import type {
  ComparisonResult,
  DisplayItem,
  DisplayLeaderboardItem,
  DisplayPlayerItem,
  DisplayTeamItem,
  GoalieLeaderboardResult,
  LeaderboardEntry,
  PlayerContractToolResult,
  PlayerProfileToolResult,
  PlayerSummaryResult,
  SearchResult,
  SkaterLeaderboardResult,
  TeamSummaryResult,
  ToolInvocation,
  ToolPlayerData,
  ToolTeamData,
} from "../types/api";
import { comparisonCategories, sampleQuestions } from "../constants/appConstants";
import {
  calculateAge,
  formatCategoryLabel,
  formatComparisonMetric,
  formatCurrency,
  formatDecimal,
  formatGoalieLine,
  formatPct,
  formatSavePct,
  formatScoringLine,
  formatSignedDecimal,
  formatStatValue,
  moneyPuckLabel,
  moneypuckNotes,
  playerSubtitle,
  statsContextLabel,
  supportNotes,
  teamSupportNotes,
} from "../utils/formatters";
import { teamLogoSrc, teamLogoSrcByAbbrev, teamSeasonLabel, teamStatsRows } from "../utils/teamDisplay";

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
          <p>Rel. xG%: {formatSignedDecimal((analytics.relative_expected_goals_pct ?? 0) * 100, 1)}%</p>
          <p>Corsi%: {formatPct(analytics.on_ice_corsi_pct)}</p>
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

export function QueryExamples(props: { onSelect: (question: string) => void }) {
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
        <div className="player-card-brand">
          <img
            className="team-logo"
            src={teamLogoSrcByAbbrev(player.profile.team_abbrev)}
            alt={`${player.profile.team_name ?? player.profile.team_abbrev ?? "NHL"} logo`}
          />
          <div>
            <p className="section-kicker">Player</p>
            <h4>{player.identity.full_name}</h4>
            <p className="player-subtitle">{playerSubtitle(player)}</p>
          </div>
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
          <span className={player.moneypuck_coverage.available ? "badge badge-on" : "badge"}>
            MoneyPuck
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

function TeamCard(props: { team: ToolTeamData }) {
  const { team } = props;
  const notes = [...teamSupportNotes(team.source_coverage), ...moneypuckNotes(team.moneypuck_coverage)];

  return (
    <article className="team-card">
      <div className="team-card-header">
        <div className="team-card-brand">
          <img
            className="team-logo"
            src={teamLogoSrc(team.identity)}
            alt={`${team.identity.team_name ?? team.identity.team_abbrev} logo`}
          />
          <div>
            <p className="section-kicker">Team</p>
            <h4>{team.identity.team_name ?? team.identity.team_abbrev}</h4>
            <p className="player-subtitle">
              {team.identity.team_abbrev} - {team.stats.season_type === "playoffs" ? "Playoffs" : "Regular season"}
            </p>
          </div>
        </div>
        <div className="source-badges">
          <span className={team.source_coverage.nhl_available ? "badge badge-on" : "badge"}>
            NHL
          </span>
          <span className={team.moneypuck_coverage.available ? "badge badge-on" : "badge"}>
            MoneyPuck
          </span>
        </div>
      </div>

      <div className="micro-panel team-summary-panel">
        <p className="micro-label">{teamSeasonLabel(team.stats.season_type)}</p>
        <div className="team-stats-grid">
          {teamStatsRows(team.stats).map((row) => (
            <div key={row.label} className="team-stat-cell">
              <span className="team-stat-label">{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </div>
      </div>

      {notes.length > 0 ? (
        <ul className="note-list">
          {notes.map((note) => (
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

function TeamDetailsView(props: { result: TeamSummaryResult }) {
  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>Team details</h3>
        </div>
      </div>
      <TeamCard team={props.result.team} />
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

function findDisplayPlayer(
  item: DisplayPlayerItem,
  toolInvocations: ToolInvocation[],
): ToolPlayerData | null {
  const normalizedName = item.full_name.toLowerCase();

  function matches(player: ToolPlayerData): boolean {
    return item.nhl_id !== null
      ? player.identity.nhl_id === item.nhl_id
      : player.identity.full_name.toLowerCase() === normalizedName;
  }

  for (const toolInvocation of toolInvocations) {
    if (!toolInvocation.output.ok || !toolInvocation.output.result) {
      continue;
    }

    const result = toolInvocation.output.result;
    if ("players" in result && Array.isArray(result.players)) {
      const player = result.players.find(matches);
      if (player) {
        return player;
      }
    }

    if ("player_a" in result && "player_b" in result) {
      if (matches(result.player_a)) {
        return result.player_a;
      }
      if (matches(result.player_b)) {
        return result.player_b;
      }
    }

    if ("player" in result && matches(result.player)) {
      return result.player;
    }

    if ("identity" in result && "profile" in result && "stats" in result && "recent_form" in result) {
      const player = toProfileToolPlayer(result);
      if (matches(player)) {
        return player;
      }
    }
  }

  return null;
}

function findDisplayTeam(
  item: DisplayTeamItem,
  toolInvocations: ToolInvocation[],
): ToolTeamData | null {
  const teamAbbrev = item.team_abbrev.toUpperCase();

  for (const toolInvocation of toolInvocations) {
    if (!toolInvocation.output.ok || !toolInvocation.output.result) {
      continue;
    }

    const result = toolInvocation.output.result;
    if ("team" in result && result.team.identity.team_abbrev.toUpperCase() === teamAbbrev) {
      return result.team;
    }
  }

  return null;
}

function findLeaderboardResult(
  item: DisplayLeaderboardItem,
  toolInvocations: ToolInvocation[],
): SkaterLeaderboardResult | GoalieLeaderboardResult | null {
  const toolInvocation = toolInvocations[item.tool_invocation_index];
  if (
    !toolInvocation
    || !toolInvocation.output.ok
    || !toolInvocation.output.result
    || !(
      toolInvocation.tool_name === "get_skater_leaderboard"
      || toolInvocation.tool_name === "get_goalie_leaderboard"
    )
    || !("leaders" in toolInvocation.output.result)
  ) {
    return null;
  }

  const result = toolInvocation.output.result as SkaterLeaderboardResult | GoalieLeaderboardResult;
  if (item.player_ids.length === 0) {
    return result;
  }

  const playerIds = new Set(item.player_ids);
  return {
    ...result,
    leaders: result.leaders.filter((leader) => playerIds.has(leader.nhl_id)),
  };
}

function findLeaderboardEntryForPlayer(
  item: DisplayPlayerItem,
  toolInvocations: ToolInvocation[],
): LeaderboardEntry | null {
  const normalizedName = item.full_name.toLowerCase();

  for (const toolInvocation of toolInvocations) {
    if (
      !toolInvocation.output.ok
      || !toolInvocation.output.result
      || !("leaders" in toolInvocation.output.result)
    ) {
      continue;
    }

    const entry = toolInvocation.output.result.leaders.find((leader) => (
      item.nhl_id !== null
        ? leader.nhl_id === item.nhl_id
        : leader.full_name.toLowerCase() === normalizedName
    ));
    if (entry) {
      return entry;
    }
  }

  return null;
}

function CuratedPlayerView(props: { item: DisplayPlayerItem; toolInvocations: ToolInvocation[] }) {
  const player = findDisplayPlayer(props.item, props.toolInvocations);
  const leaderboardEntry = player ? null : findLeaderboardEntryForPlayer(props.item, props.toolInvocations);

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>{props.item.title ?? props.item.full_name}</h3>
          {props.item.reason ? <p className="player-subtitle">{props.item.reason}</p> : null}
        </div>
      </div>

      {player ? (
        <PlayerCard player={player} />
      ) : leaderboardEntry ? (
        <div className="comparison-table-wrap">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Player</th>
                <th>Team</th>
                <th>Pos</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{leaderboardEntry.rank}</td>
                <td>{leaderboardEntry.full_name}</td>
                <td>{leaderboardEntry.team_abbrev ?? "N/A"}</td>
                <td>{leaderboardEntry.position ?? "N/A"}</td>
                <td>{formatStatValue(leaderboardEntry.value)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <p>{props.item.full_name}</p>
      )}
    </section>
  );
}

function CuratedTeamView(props: { item: DisplayTeamItem; toolInvocations: ToolInvocation[] }) {
  const team = findDisplayTeam(props.item, props.toolInvocations);

  if (!team) {
    return null;
  }

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>{props.item.title ?? team.identity.team_name ?? team.identity.team_abbrev}</h3>
          {props.item.reason ? <p className="player-subtitle">{props.item.reason}</p> : null}
        </div>
      </div>
      <TeamCard team={team} />
    </section>
  );
}

function CuratedLeaderboardView(props: { item: DisplayLeaderboardItem; toolInvocations: ToolInvocation[] }) {
  const result = findLeaderboardResult(props.item, props.toolInvocations);

  if (!result) {
    return null;
  }

  return (
    <section className="support-block">
      <div className="support-block-header">
        <div>
          <h3>{props.item.title}</h3>
          {props.item.reason ? <p className="player-subtitle">{props.item.reason}</p> : null}
        </div>
      </div>
      <LeaderboardView result={result} />
    </section>
  );
}

export function CuratedSupportView(props: { displayItems: DisplayItem[]; toolInvocations: ToolInvocation[] }) {
  if (props.displayItems.length === 0) {
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
        {props.displayItems.map((item, index) => {
          const key = `${item.kind}-${index}`;
          if (item.kind === "player") {
            return <CuratedPlayerView key={key} item={item} toolInvocations={props.toolInvocations} />;
          }
          if (item.kind === "team") {
            return <CuratedTeamView key={key} item={item} toolInvocations={props.toolInvocations} />;
          }
          return <CuratedLeaderboardView key={key} item={item} toolInvocations={props.toolInvocations} />;
        })}
      </div>
    </section>
  );
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

export function ToolTrace(props: { toolInvocations: ToolInvocation[] }) {
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

          if (toolInvocation.tool_name === "get_team_summary_data") {
            return (
              <TeamDetailsView
                key={key}
                result={toolInvocation.output.result as TeamSummaryResult}
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
