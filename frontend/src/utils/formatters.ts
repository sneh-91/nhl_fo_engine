import type {
  BasicStats,
  GoalieStats,
  MoneyPuckCoverage,
  SourceCoverage,
  StatsContext,
  TeamSourceCoverage,
  ToolPlayerData,
} from "../types/api";
import { hiddenLimitationPills } from "../constants/appConstants";

export function formatCurrency(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "N/A";
  }

  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }

  return `$${value.toLocaleString()}`;
}

export function formatStatValue(value: string | number | boolean | null): string {
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

export function formatCategoryLabel(category: string): string {
  const customLabels: Record<string, string> = {
    on_ice_expected_goals_pct: "On-Ice xG%",
    relative_expected_goals_pct: "Rel.xG%",
    on_ice_corsi_pct: "Corsi%",
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

export function calculateAge(birthDate: string | null): string {
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

export function playerSubtitle(player: ToolPlayerData): string {
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

export function supportNotes(sourceCoverage: SourceCoverage): string[] {
  return sourceCoverage.notes.map((note) => note.detail);
}

export function teamSupportNotes(sourceCoverage: TeamSourceCoverage): string[] {
  return sourceCoverage.notes.map((note) => note.detail);
}

export function moneypuckNotes(coverage: MoneyPuckCoverage): string[] {
  return coverage.notes.map((note) => note.detail);
}

export function visibleLimitations(limitations: string[]): string[] {
  return limitations.filter((item) => !hiddenLimitationPills.has(item));
}

export function statsContextLabel(statsContext: StatsContext): string {
  if (statsContext === "playoffs") {
    return "Playoff line";
  }

  if (statsContext === "both") {
    return "Stat lines";
  }

  return "Season line";
}

export function formatScoringLine(stats: BasicStats | null | undefined): string {
  if (!stats) {
    return "N/A";
  }

  return `${formatStatValue(stats.goals)} G / ${formatStatValue(stats.assists)} A / ${formatStatValue(stats.points)} PTS`;
}

export function formatDecimal(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return value.toFixed(digits);
}

export function formatSavePct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  const formatted = value.toFixed(3);
  return value >= 0 && value < 1 ? formatted.replace(/^0/, "") : formatted;
}

export function formatGoalieLine(stats: GoalieStats | null | undefined): string {
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

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return `${(value * 100).toFixed(1)}%`;
}

export function formatSignedDecimal(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }

  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function formatComparisonMetric(category: string, value: string | number | boolean | null): string {
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

export function moneyPuckLabel(coverage: MoneyPuckCoverage): string {
  if (!coverage.available) {
    return "Underlying analytics unavailable";
  }

  const context =
    coverage.season_type === "playoffs"
      ? "playoffs"
      : coverage.season_type === "regular_season"
        ? "regular season"
        : null;

  if (coverage.situation === "all") {
    return context ? `Underlying analytics (${context})` : "Underlying analytics";
  }

  return context
    ? `Underlying analytics ${coverage.situation} (${context})`
    : `Underlying analytics ${coverage.situation}`;
}
