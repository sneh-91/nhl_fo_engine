import type { TeamIdentity, TeamStats } from "../types/api";
import { teamLogoByAbbrev } from "../constants/teamLogos";
import { formatDecimal, formatPct, formatStatValue } from "./formatters";

export function teamLogoSrcByAbbrev(teamAbbrev: string | null | undefined): string {
  return teamAbbrev ? teamLogoByAbbrev[teamAbbrev.toUpperCase()] ?? "/teams/nhl-logo.svg" : "/teams/nhl-logo.svg";
}

export function teamLogoSrc(team: TeamIdentity): string {
  return teamLogoSrcByAbbrev(team.team_abbrev);
}

export function teamStatsRows(stats: TeamStats): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string | null }> = [
    { label: "Games", value: formatStatValue(stats.games_played) },
    { label: "W", value: formatStatValue(stats.wins) },
    { label: "L", value: formatStatValue(stats.losses) },
    { label: "OTL", value: stats.ot_losses !== null ? formatStatValue(stats.ot_losses) : null },
    { label: "PTS", value: stats.points !== null ? formatStatValue(stats.points) : null },
    { label: "P%", value: stats.points_pct !== null ? formatPct(stats.points_pct) : null },
    { label: "GF", value: formatStatValue(stats.goals_for) },
    { label: "GA", value: formatStatValue(stats.goals_against) },
    { label: "PP%", value: stats.power_play_pct !== null ? formatPct(stats.power_play_pct) : null },
    { label: "PK%", value: stats.penalty_kill_pct !== null ? formatPct(stats.penalty_kill_pct) : null },
    { label: "GF%", value: stats.goals_for_pct !== null ? formatPct(stats.goals_for_pct) : null },
    { label: "xGF%", value: stats.expected_goals_for_pct !== null ? formatPct(stats.expected_goals_for_pct) : null },
    { label: "Corsi%", value: stats.corsi_pct !== null ? formatPct(stats.corsi_pct) : null },
    { label: "PDO", value: stats.pdo !== null ? formatDecimal(stats.pdo, 3) : null },
  ];

  return rows
    .filter((row): row is { label: string; value: string } => row.value !== null)
    .map((row) => ({ label: row.label, value: row.value }));
}

export function teamSeasonLabel(seasonType: "regular_season" | "playoffs" | null): string {
  return seasonType === "playoffs" ? "Playoff team line" : "Season team line";
}
