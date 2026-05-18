export const sampleQuestions = [
  "Compare Sidney Crosby Vs Alex Ovechkin",
  "Find right-shot defensemen on Florida under 7 million AAV",
  "Who is better, Brandon Carlo or Bowen Byram? Pick one and defend your stance!",
  "Who are left-shot defensemen on Toronto with at least 20 points?",
  "Were the Toronto Maple Leafs good this year? What is their outlook?"
];

export const hiddenLimitationPills = new Set([
  "These tools search only the current active NHL roster universe built from standings and team rosters.",
  "Outputs are grounded only in NHL API data, CapWages contract data, and local MoneyPuck player analytics when available.",
  "Broader advanced analytics and team-context reasoning are not part of the current build.",
]);

export const comparisonCategories = new Set([
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
