from __future__ import annotations

import copy
import json
from typing import Any

from openai import AsyncOpenAI

from ..config import Settings
from ..errors import (
    AmbiguousPlayerError,
    IdentityResolutionError,
    MissingConfigurationError,
    PlayerNotFoundError,
    UnsupportedQuestionError,
    UpstreamRequestError,
)
from ..models import (
    DisplayLeaderboardItem,
    DisplayPlayerItem,
    DisplaySelectionResponse,
    DisplayTeamItem,
    ExecutedToolResult,
    GoalieLeaderboardQuery,
    OrchestratedAnswerResult,
    PlayerComparisonQuery,
    PlayerSearchFilters,
    SkaterLeaderboardQuery,
    TeamToolQuery,
    PlayerToolQuery,
    ToolInvocationRecord,
)
from .team_context import TeamContextService
from .tools import PlayerToolService


SYSTEM_PROMPT = """
You are HockeyOps AI v0.5.

You are a hockey-first assistant. Answer NHL and hockey-operations questions directly.

Use backend tools whenever factual player, roster, team, stat, or contract information is needed.

Hard rules:
- Do not invent stats, contract terms, clauses, team context, or player facts.
- Stay inside the current v0.5 product focus: NHL and hockey topics only.
- Do not claim unsupported advanced analytics or strategic team-fit conclusions.
- Current-season MoneyPuck player analytics are supported only through the tool-returned fields that are actually present.
- Do not invent MoneyPuck metrics beyond the supported player fields in the tool output.
- Team-level MoneyPuck stat fields are supported only through the tool-returned fields that are actually present.
- Do not claim manual team context, strategy posture, or team-fit context that is not in the tool output.
- Manual team context may be available inside get_team_summary_data as team_context.
- Use team_context for team posture, buyer/seller stance, contention status, strengths, needs, cap posture, prospect pipeline, core age, goalie outlook, and roster-building questions.
- Treat team_context as manually maintained current-season guidance, not as an official NHL or MoneyPuck fact source.
- If team_context is missing, say that team-strategy context is unavailable instead of inventing it.
- Do not mention tool names, internal field names, or source labels such as team_context, tool output, manual context, or support data in the final answer.
- If the question is subjective or evaluative, you may give a clearly labeled hockey opinion or judgment.
- For subjective questions, use tool-returned facts when helpful, but do not refuse only because there is no single objectively verifiable answer.
- For broad subjective questions without a stated criterion, answer with your best hockey judgment first, then optionally mention a few factual ways to narrow it.
- If answer to question depends on facts the tools cannot provide, say what is missing plainly instead of pretending certainty.
- Use the tool outputs as the source of truth.
- If the user is comparing two players or asking who had the better season, use compare_players rather than separate summary calls.
- For comparison questions, when current-season player analytics are available in the tool output, treat them as meaningful evidence rather than an afterthought.
- If the question is specifically about MoneyPuck or underlying analytics, prefer player profile or summary tools so you can use the returned analytics fields directly.
- For team stat questions, use get_team_summary_data rather than forcing a player tool.
- For season-stat questions, set the tool argument season_type explicitly.
- Use season_type=regular_season by default.
- Use season_type=playoffs only when the user explicitly needs playoff or postseason stats.
- Use season_type=both only when the user explicitly asks for both regular-season and playoff stats in the same answer.
- For league leaders or leaderboard questions, use the dedicated skater or goalie leaderboard tool that matches the stat category being asked.
- Goalie profile and summary questions are supported.
- Goalie search questions are supported through search_players with goalie-specific filters and sorts.
- Goalie-vs-goalie comparison is supported through compare_players.
- Mixed skater-vs-goalie statistical comparison is not supported.
- Team stat questions are supported for regular season and playoffs.
- For playoff team answers, do not invent standings-only fields like points percentage when they are not in the tool output.

Output style:
- Keep the answer concise and direct.
- Write in plain natural text, like a smart friend texting an analysis.
- Do not use markdown, bold, headers, or code formatting.
- Avoid nested bullets. Prefer short paragraphs or compact plain-text lines.
- Include explicit limitations when source coverage is incomplete or the question exceeds scope.
- If comparing or ranking players, base all takeaways only on tool-returned data.
- If answering with opinion, say it is your view and separate opinion from hard facts.
- When citing a player's season production, include games played (GP) alongside the scoring line when available.
- When current-season player analytics are available and relevant, cite them plainly and keep them separate from the NHL counting-stat line.
- Unless the user explicitly asks about MoneyPuck, refer to them as underlying analytics or chance-share / impact numbers rather than repeatedly calling them "MoneyPuck stats."
- If MoneyPuck analytics are missing for a player, say that plainly instead of inventing an analytics take.
- If team data is missing a field for the requested season context, say that plainly instead of inventing it.
- If player games played differ meaningfully, discuss both total production and rate production.
- Do not treat a tiny total-point edge as decisive without acknowledging the games-played context.
- For team answers, keep measured results, underlying metrics, and forward-looking evaluation conceptually separate, but do not refer to internal data labels.
""".strip()

SCOPE_CLASSIFIER_PROMPT = """
You are a strict scope classifier for HockeyOps AI.

Return only JSON with this exact shape:
{"in_scope": true|false, "message": "<short user-facing sentence>"}

Mark in_scope true only if the question is about NHL hockey operations topics that HockeyOps AI can reasonably handle with NHL API facts and CapWages contract data, such as:
- NHL players
- NHL teams or rosters
- NHL contracts, cap hits, AAV, clauses, term
- NHL player comparisons
- NHL player discovery/search questions
- generic hockey questions where the hockey meaning is obvious in context, including subjective prompts like "Who is the best player?" or follow-ups like "What about his contract?"

Mark in_scope false for:
- non-hockey questions
- hockey questions outside NHL scope
- general chat, coding help, math, weather, history, or other unrelated topics

Interpret ambiguous sports wording in a hockey-first way when a reasonable NHL reading exists.
Only mark false when the question is clearly unrelated to hockey or clearly about another sport/domain.

If false, the message should be brief and user-facing, for example:
"HockeyOps AI only handles NHL player, roster, and contract questions right now."

If true, the message should be:
"ok"
""".strip()


DISPLAY_SELECTOR_PROMPT = """
You select the support items that should be displayed in the UI for a HockeyOps AI answer.

Return only JSON with this exact shape:
{"display_items": [<display item objects>]}

Allowed display item shapes:
- {"kind": "player", "nhl_id": 123, "full_name": "Player Name", "title": "short label or null", "reason": "short reason or null"}
- {"kind": "team", "team_abbrev": "TOR", "title": "short label or null", "reason": "short reason or null"}
- {"kind": "leaderboard", "title": "short title", "tool_invocation_index": 0, "player_ids": [123, 456], "reason": "short reason or null"}

Rules:
- Choose only players, teams, or leaderboard tool outputs that are directly relevant to the final answer.
- Do not include exploratory or unused candidates.
- Do not include entities that are not present in the available references.
- Prefer 1-5 display items for normal answers.
- Use player items for specific named players.
- Use team items for team-summary answers.
- Use leaderboard items only when the final answer is about a leaderboard or ranking list.
- If nothing should be displayed, return {"display_items": []}.
- Do not include markdown or explanatory text outside the JSON object.
""".strip()

MAX_DISPLAY_ITEMS = 8


def _normalize_display_text(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character.isspace() else " "
        for character in value.casefold()
    )
    return " ".join(cleaned.split())


class HockeyOpsOrchestrator:
    def __init__(
        self,
        settings: Settings,
        tool_service: PlayerToolService,
        team_context_service: TeamContextService,
    ) -> None:
        self._settings = settings
        self._tool_service = tool_service
        self._team_context_service = team_context_service
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key)
            if settings.openai_api_key
            else None
        )

    async def answer_question(self, question: str) -> OrchestratedAnswerResult:
        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is missing. Add it to the root .env before using Phase 5 orchestration."
            )

        scope_decision = await self._classify_scope(question)
        if not scope_decision["in_scope"]:
            raise UnsupportedQuestionError(scope_decision["message"])

        input_items: list[Any] = [{"role": "user", "content": question}]
        tool_invocations: list[ToolInvocationRecord] = []
        limitations: list[str] = []
        response = await self._create_response(input_items)

        for _ in range(self._settings.openai_max_tool_rounds):
            function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not function_calls:
                return OrchestratedAnswerResult(
                    model=self._settings.openai_answer_model,
                    answer_text=self._clean_answer_text(response.output_text),
                    tool_invocations=tool_invocations,
                    limitations=self._dedupe_limitations(limitations),
                    response_id=getattr(response, "id", None),
                )

            input_items.extend(response.output)
            for tool_call in function_calls:
                executed_tool = await self._execute_tool_call(tool_call.name, tool_call.arguments)
                tool_invocations.append(
                    ToolInvocationRecord(
                        tool_name=tool_call.name,
                        arguments=json.loads(tool_call.arguments),
                        output=executed_tool.support_output,
                    )
                )
                limitations.extend(self._collect_limitations(executed_tool.support_output))
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(executed_tool.model_output),
                    }
                )

            response = await self._create_response(input_items)

        raise RuntimeError(
            f"Model exceeded the configured max tool rounds ({self._settings.openai_max_tool_rounds})."
        )

    async def _create_response(self, input_items: list[Any]):
        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is missing. Add it to the root .env before using Phase 5 orchestration."
            )

        request: dict[str, Any] = {
            "model": self._settings.openai_answer_model,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": self._tool_definitions(),
            "max_output_tokens": self._settings.openai_max_output_tokens,
        }
        if self._settings.openai_reasoning_effort:
            request["reasoning"] = {"effort": self._settings.openai_reasoning_effort}

        return await self._client.responses.create(**request)

    async def _select_display_items(
        self,
        *,
        question: str,
        answer_text: str,
        available_references: dict[str, Any],
    ) -> DisplaySelectionResponse:
        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is missing. Add it to the root .env before using display selection."
            )

        payload = {
            "question": question,
            "answer_text": answer_text,
            "available_references": available_references,
        }
        response = await self._client.responses.create(
            model=self._settings.openai_classifier_model,
            instructions=DISPLAY_SELECTOR_PROMPT,
            input=[{"role": "user", "content": json.dumps(payload)}],
            max_output_tokens=1000,
        )

        try:
            parsed = json.loads(response.output_text)
            return DisplaySelectionResponse.model_validate(parsed)
        except (json.JSONDecodeError, ValueError):
            return DisplaySelectionResponse()

    def _build_display_available_references(
        self,
        tool_invocations: list[ToolInvocationRecord],
    ) -> dict[str, Any]:
        reference_index = self._build_display_reference_index(tool_invocations)
        return {
            "players": [
                {
                    "nhl_id": player["nhl_id"],
                    "full_name": player["full_name"],
                    "source_tool_indexes": sorted(player["source_tool_indexes"]),
                }
                for player in reference_index["players_by_id"].values()
            ],
            "teams": [
                {
                    "team_abbrev": team_abbrev,
                    "source_tool_indexes": sorted(source_tool_indexes),
                }
                for team_abbrev, source_tool_indexes in reference_index["teams_by_abbrev"].items()
            ],
            "leaderboards": [
                {
                    "tool_invocation_index": tool_invocation_index,
                    "title": leaderboard["title"],
                    "player_ids": leaderboard["player_ids"],
                }
                for tool_invocation_index, leaderboard in reference_index["leaderboards_by_index"].items()
            ],
        }

    def _validate_display_selection(
        self,
        selection: DisplaySelectionResponse,
        tool_invocations: list[ToolInvocationRecord],
    ) -> DisplaySelectionResponse:
        reference_index = self._build_display_reference_index(tool_invocations)
        display_items = []

        for item in selection.display_items:
            if len(display_items) >= MAX_DISPLAY_ITEMS:
                break

            if isinstance(item, DisplayPlayerItem):
                validated_player = self._validate_display_player_item(item, reference_index)
                if validated_player is not None:
                    display_items.append(validated_player)
                continue

            if isinstance(item, DisplayTeamItem):
                validated_team = self._validate_display_team_item(item, reference_index)
                if validated_team is not None:
                    display_items.append(validated_team)
                continue

            if isinstance(item, DisplayLeaderboardItem):
                validated_leaderboard = self._validate_display_leaderboard_item(item, reference_index)
                if validated_leaderboard is not None:
                    display_items.append(validated_leaderboard)

        return DisplaySelectionResponse(display_items=display_items)

    def _validate_display_player_item(
        self,
        item: DisplayPlayerItem,
        reference_index: dict[str, Any],
    ) -> DisplayPlayerItem | None:
        player_reference = None
        if item.nhl_id is not None:
            player_reference = reference_index["players_by_id"].get(item.nhl_id)

        if player_reference is None:
            player_reference = reference_index["players_by_name"].get(
                _normalize_display_text(item.full_name)
            )

        if player_reference is None:
            return None

        return DisplayPlayerItem(
            kind="player",
            nhl_id=player_reference["nhl_id"],
            full_name=player_reference["full_name"],
            title=item.title,
            reason=item.reason,
        )

    def _validate_display_team_item(
        self,
        item: DisplayTeamItem,
        reference_index: dict[str, Any],
    ) -> DisplayTeamItem | None:
        team_abbrev = item.team_abbrev.strip().upper()
        if team_abbrev not in reference_index["teams_by_abbrev"]:
            return None

        return DisplayTeamItem(
            kind="team",
            team_abbrev=team_abbrev,
            title=item.title,
            reason=item.reason,
        )

    def _validate_display_leaderboard_item(
        self,
        item: DisplayLeaderboardItem,
        reference_index: dict[str, Any],
    ) -> DisplayLeaderboardItem | None:
        leaderboard = reference_index["leaderboards_by_index"].get(item.tool_invocation_index)
        if leaderboard is None:
            return None

        allowed_player_ids = set(leaderboard["player_ids"])
        player_ids = [
            player_id
            for player_id in item.player_ids
            if player_id in allowed_player_ids
        ]

        return DisplayLeaderboardItem(
            kind="leaderboard",
            title=item.title.strip() or leaderboard["title"],
            tool_invocation_index=item.tool_invocation_index,
            player_ids=player_ids,
            reason=item.reason,
        )

    def _build_display_reference_index(
        self,
        tool_invocations: list[ToolInvocationRecord],
    ) -> dict[str, Any]:
        reference_index: dict[str, Any] = {
            "players_by_id": {},
            "players_by_name": {},
            "teams_by_abbrev": {},
            "leaderboards_by_index": {},
        }

        for tool_invocation_index, tool_invocation in enumerate(tool_invocations):
            output = tool_invocation.output
            if not output.get("ok"):
                continue

            result = output.get("result")
            if not isinstance(result, dict):
                continue

            self._collect_display_references_from_result(
                reference_index,
                result,
                tool_invocation.tool_name,
                tool_invocation_index,
            )

        return reference_index

    def _collect_display_references_from_result(
        self,
        reference_index: dict[str, Any],
        result: dict[str, Any],
        tool_name: str,
        tool_invocation_index: int,
    ) -> None:
        players = result.get("players")
        if isinstance(players, list):
            for player in players:
                self._add_display_player_reference(reference_index, player, tool_invocation_index)

        for field_name in ("player", "player_a", "player_b"):
            player = result.get(field_name)
            if isinstance(player, dict):
                self._add_display_player_reference(reference_index, player, tool_invocation_index)

        if "identity" in result:
            self._add_display_player_reference(reference_index, result, tool_invocation_index)

        team = result.get("team")
        if isinstance(team, dict):
            self._add_display_team_reference(reference_index, team, tool_invocation_index)

        if tool_name in {"get_skater_leaderboard", "get_goalie_leaderboard"}:
            self._add_display_leaderboard_reference(reference_index, result, tool_invocation_index)

    def _add_display_player_reference(
        self,
        reference_index: dict[str, Any],
        payload: Any,
        tool_invocation_index: int,
    ) -> None:
        if not isinstance(payload, dict):
            return

        identity = payload.get("identity")
        if isinstance(identity, dict):
            nhl_id = identity.get("nhl_id")
            full_name = identity.get("full_name")
        else:
            nhl_id = payload.get("nhl_id")
            full_name = payload.get("full_name")

        if not isinstance(nhl_id, int) or not isinstance(full_name, str) or not full_name.strip():
            return

        player_reference = reference_index["players_by_id"].setdefault(
            nhl_id,
            {
                "nhl_id": nhl_id,
                "full_name": full_name.strip(),
                "source_tool_indexes": set(),
            },
        )
        player_reference["source_tool_indexes"].add(tool_invocation_index)
        reference_index["players_by_name"][_normalize_display_text(full_name)] = player_reference

    def _add_display_team_reference(
        self,
        reference_index: dict[str, Any],
        payload: dict[str, Any],
        tool_invocation_index: int,
    ) -> None:
        identity = payload.get("identity")
        if not isinstance(identity, dict):
            return

        team_abbrev = identity.get("team_abbrev")
        if not isinstance(team_abbrev, str) or not team_abbrev.strip():
            return

        reference_index["teams_by_abbrev"].setdefault(team_abbrev.strip().upper(), set()).add(
            tool_invocation_index
        )

    def _add_display_leaderboard_reference(
        self,
        reference_index: dict[str, Any],
        result: dict[str, Any],
        tool_invocation_index: int,
    ) -> None:
        leaders = result.get("leaders")
        if not isinstance(leaders, list):
            return

        player_ids = []
        for leader in leaders:
            if not isinstance(leader, dict):
                continue
            self._add_display_player_reference(reference_index, leader, tool_invocation_index)
            nhl_id = leader.get("nhl_id")
            if isinstance(nhl_id, int):
                player_ids.append(nhl_id)

        category_label = result.get("category_label")
        title = category_label if isinstance(category_label, str) and category_label.strip() else "Leaderboard"
        reference_index["leaderboards_by_index"][tool_invocation_index] = {
            "title": title,
            "player_ids": player_ids,
        }

    async def _classify_scope(self, question: str) -> dict[str, Any]:
        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is missing. Add it to the root .env before using Phase 5 orchestration."
            )

        response = await self._client.responses.create(
            model=self._settings.openai_classifier_model,
            instructions=SCOPE_CLASSIFIER_PROMPT,
            input=[{"role": "user", "content": question}],
            max_output_tokens=120,
        )

        parsed = self._parse_scope_response(response.output_text)
        if parsed is not None:
            if parsed["in_scope"]:
                return parsed
            if self._looks_hockey_related(question) or not self._looks_clearly_off_topic(question):
                return {"in_scope": True, "message": "ok"}
            return parsed

        if self._looks_clearly_off_topic(question):
            return {
                "in_scope": False,
                "message": "HockeyOps AI only handles NHL player, roster, and contract questions right now.",
            }

        return {"in_scope": True, "message": "ok"}

    def _parse_scope_response(self, raw_text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        in_scope = payload.get("in_scope")
        message = payload.get("message")
        if not isinstance(in_scope, bool) or not isinstance(message, str):
            return None

        return {"in_scope": in_scope, "message": message.strip() or "ok"}

    def _looks_hockey_related(self, question: str) -> bool:
        normalized = question.casefold()
        hockey_terms = (
            "nhl",
            "hockey",
            "player",
            "players",
            "roster",
            "lineup",
            "goalie",
            "goalies",
            "skater",
            "skaters",
            "defenseman",
            "defenceman",
            "forward",
            "forwards",
            "winger",
            "center",
            "centre",
            "contract",
            "cap hit",
            "aav",
            "trade",
            "waiver",
            "free agent",
            "draft",
            "prospect",
            "points",
            "goals",
            "assists",
            "stanley cup",
        )
        return any(term in normalized for term in hockey_terms)

    def _looks_clearly_off_topic(self, question: str) -> bool:
        normalized = question.casefold()
        obvious_off_topic_terms = (
            "weather",
            "recipe",
            "capital of",
            "python code",
            "javascript",
            "stock market",
            "bitcoin",
            "movie",
            "restaurant",
            "nba",
            "nfl",
            "mlb",
            "wnba",
            "soccer",
            "football",
            "basketball",
            "baseball",
            "tennis",
            "golf",
            "formula 1",
            "f1",
            "area of a circle",
            "circle formula",
            "integral",
            "derivative",
            "president of",
            "prime minister",
        )
        return any(term in normalized for term in obvious_off_topic_terms)

    def _clean_answer_text(self, raw_text: str) -> str:
        cleaned = raw_text.replace("**", "").replace("__", "").replace("`", "")
        cleaned = cleaned.replace("\r\n", "\n")
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        return cleaned.strip()

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "get_skater_leaderboard",
                "description": (
                    "Fetch a current-season NHL skater leaderboard for one supported category. "
                    "Use this for league-leader questions about points, goals, assists, plus-minus, "
                    "power-play goals, short-handed goals, penalty minutes, faceoff percentage, or time on ice."
                ),
                "strict": True,
                "parameters": self._skater_leaderboard_schema(),
            },
            {
                "type": "function",
                "name": "get_goalie_leaderboard",
                "description": (
                    "Fetch a current-season NHL goalie leaderboard for one supported category. "
                    "Use this for league-leader questions about wins, shutouts, save percentage, or goals-against average."
                ),
                "strict": True,
                "parameters": self._goalie_leaderboard_schema(),
            },
            {
                "type": "function",
                "name": "search_players",
                "description": (
                    "Search the current active NHL roster universe using factual NHL and CapWages filters. "
                    "Stat filters and ranking use the requested season_type. "
                    "Use this for discovery questions, candidate lists, age/team/position/contract buckets, "
                    "or when the user asks for players matching a skater or goalie profile."
                ),
                "strict": True,
                "parameters": self._search_players_schema(),
            },
            {
                "type": "function",
                "name": "get_player_profile",
                "description": (
                    "Fetch one player's NHL profile, identity, season stats, recent form, and current-season MoneyPuck player analytics when available. "
                    "Supports both skaters and goalies for single-player questions. "
                    "MoneyPuck analytics here follow the requested regular-season or playoff context for the local 2025-26 dataset when available. "
                    "Set season_type explicitly when the user needs playoff/postseason stats or both regular-season and playoff lines. "
                    "Use this for factual player-summary questions when contract detail is not the main focus."
                ),
                "strict": True,
                "parameters": self._player_query_schema(),
            },
            {
                "type": "function",
                "name": "get_player_contract",
                "description": (
                    "Fetch one player's CapWages-grounded contract detail, active contract view, and contract limitations."
                ),
                "strict": True,
                "parameters": self._player_query_schema(),
            },
            {
                "type": "function",
                "name": "get_player_summary_data",
                "description": (
                    "Fetch one merged player object combining NHL profile/stats, CapWages contract data, and current-season MoneyPuck player analytics when available. "
                    "Supports both skaters and goalies for single-player questions. "
                    "MoneyPuck analytics here follow the requested regular-season or playoff context for the local 2025-26 dataset when available. "
                    "Set season_type explicitly when the user needs playoff/postseason stats or both regular-season and playoff lines."
                ),
                "strict": True,
                "parameters": self._player_query_schema(),
            },
            {
                "type": "function",
                "name": "get_team_summary_data",
                "description": (
                    "Fetch one NHL team summary with season-context-aware team stats, local MoneyPuck team analytics, and team outlook/context guidance when available. "
                    "Use this for factual team-stat questions about wins, losses, points, goals for/against, special teams, and underlying team metrics. "
                    "Also use this for team-direction, buyer/seller, contention, roster strengths, roster needs, cap posture, prospect pipeline, core age, and goalie outlook questions. "
                    "For playoffs, rely only on the playoff fields actually returned by the tool."
                ),
                "strict": True,
                "parameters": self._team_query_schema(),
            },
            {
                "type": "function",
                "name": "compare_players",
                "description": (
                    "Compare two current NHL roster players side by side using factual NHL and CapWages data. "
                    "Includes current-season player analytics when available. "
                    "Supports skater-vs-skater and goalie-vs-goalie comparisons. "
                    "Set season_type to playoffs when the comparison should use playoff stats instead of regular-season stats."
                ),
                "strict": True,
                "parameters": self._player_comparison_schema(),
            },
        ]

    def _skater_leaderboard_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs"],
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "points",
                        "goals",
                        "assists",
                        "plus_minus",
                        "power_play_goals",
                        "short_handed_goals",
                        "penalty_minutes",
                        "faceoff_pct",
                        "time_on_ice",
                    ],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["season_type", "category", "limit"],
        }

    def _player_query_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "player": {"type": ["string", "null"]},
                "nhl_id": {"type": ["integer", "null"]},
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs", "both"],
                },
            },
            "required": ["player", "nhl_id", "season_type"],
        }

    def _goalie_leaderboard_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs"],
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "wins",
                        "shutouts",
                        "save_pct",
                        "goals_against_avg",
                    ],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["season_type", "category", "limit"],
        }

    def _team_query_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "team": {"type": "string"},
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs"],
                },
            },
            "required": ["team", "season_type"],
        }

    def _player_comparison_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "player_a": {"type": ["string", "null"]},
                "player_a_nhl_id": {"type": ["integer", "null"]},
                "player_b": {"type": ["string", "null"]},
                "player_b_nhl_id": {"type": ["integer", "null"]},
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs"],
                },
            },
            "required": [
                "player_a",
                "player_a_nhl_id",
                "player_b",
                "player_b_nhl_id",
                "season_type",
            ],
        }

    def _search_players_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "player": {"type": ["string", "null"]},
                "season_type": {
                    "type": "string",
                    "enum": ["regular_season", "playoffs"],
                },
                "position": {"type": ["string", "null"]},
                "shoots_catches": {"type": ["string", "null"], "enum": ["L", "R", None]},
                "team": {"type": ["string", "null"]},
                "age_min": {"type": ["integer", "null"]},
                "age_max": {"type": ["integer", "null"]},
                "aav_min": {"type": ["integer", "null"]},
                "aav_max": {"type": ["integer", "null"]},
                "years_remaining_min": {"type": ["integer", "null"]},
                "years_remaining_max": {"type": ["integer", "null"]},
                "expiry_status": {"type": ["string", "null"]},
                "clause_required": {"type": "boolean"},
                "games_played_min": {"type": ["integer", "null"]},
                "goals_min": {"type": ["integer", "null"]},
                "assists_min": {"type": ["integer", "null"]},
                "points_min": {"type": ["integer", "null"]},
                "shots_min": {"type": ["integer", "null"]},
                "wins_min": {"type": ["integer", "null"]},
                "save_pct_min": {"type": ["number", "null"]},
                "gaa_max": {"type": ["number", "null"]},
                "shutouts_min": {"type": ["integer", "null"]},
                "sort_by": {
                    "type": "string",
                    "enum": [
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
                    ],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": [
                "player",
                "season_type",
                "position",
                "shoots_catches",
                "team",
                "age_min",
                "age_max",
                "aav_min",
                "aav_max",
                "years_remaining_min",
                "years_remaining_max",
                "expiry_status",
                "clause_required",
                "games_played_min",
                "goals_min",
                "assists_min",
                "points_min",
                "shots_min",
                "wins_min",
                "save_pct_min",
                "gaa_max",
                "shutouts_min",
                "sort_by",
                "limit",
            ],
        }

    def _executed_tool_result(self, output: dict[str, Any]) -> ExecutedToolResult:
        return ExecutedToolResult(
            model_output=output,
            support_output=output,
        )

    async def _execute_tool_call(self, name: str, raw_arguments: str) -> ExecutedToolResult:
        arguments = json.loads(raw_arguments)
        try:
            if name == "get_skater_leaderboard":
                result = await self._tool_service.get_skater_leaderboard(
                    SkaterLeaderboardQuery.model_validate(arguments)
                )
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "get_goalie_leaderboard":
                result = await self._tool_service.get_goalie_leaderboard(
                    GoalieLeaderboardQuery.model_validate(arguments)
                )
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "search_players":
                result = await self._tool_service.search_players(PlayerSearchFilters.model_validate(arguments))
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "get_player_profile":
                result = await self._tool_service.get_player_profile(PlayerToolQuery.model_validate(arguments))
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "get_player_contract":
                result = await self._tool_service.get_player_contract(PlayerToolQuery.model_validate(arguments))
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "get_player_summary_data":
                result = await self._tool_service.get_player_summary_data(PlayerToolQuery.model_validate(arguments))
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            if name == "get_team_summary_data":
                result = await self._tool_service.get_team_summary_data(TeamToolQuery.model_validate(arguments))
                support_output = {"ok": True, "result": result.model_dump(mode="json")}
                return self._with_team_context_model_output(support_output)

            if name == "compare_players":
                query = PlayerComparisonQuery.model_validate(arguments)
                result = await self._tool_service.compare_players(
                    PlayerToolQuery(player=query.player_a, nhl_id=query.player_a_nhl_id),
                    PlayerToolQuery(player=query.player_b, nhl_id=query.player_b_nhl_id),
                    query.season_type,
                )
                return self._executed_tool_result({"ok": True, "result": result.model_dump(mode="json")})

            return self._executed_tool_result(
                {
                    "ok": False,
                    "error": {
                        "type": "unknown_tool",
                        "message": f"Tool '{name}' is not registered.",
                    },
                }
            )
        except (
            PlayerNotFoundError,
            AmbiguousPlayerError,
            IdentityResolutionError,
            UpstreamRequestError,
            MissingConfigurationError,
            ValueError,
        ) as error:
            return self._executed_tool_result(
                {
                    "ok": False,
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
            )

    def _with_team_context_model_output(self, support_output: dict[str, Any]) -> ExecutedToolResult:
        model_output = copy.deepcopy(support_output)
        team = model_output.get("result", {}).get("team")
        if not isinstance(team, dict):
            return ExecutedToolResult(
                model_output=model_output,
                support_output=support_output,
            )

        identity = team.get("identity")
        team_abbrev = identity.get("team_abbrev") if isinstance(identity, dict) else None
        if not isinstance(team_abbrev, str):
            team["team_context"] = None
            return ExecutedToolResult(
                model_output=model_output,
                support_output=support_output,
            )

        context = self._team_context_service.get_context(team_abbrev)
        team["team_context"] = context.model_dump(mode="json") if context is not None else None
        return ExecutedToolResult(
            model_output=model_output,
            support_output=support_output,
        )

    def _collect_limitations(self, tool_output: dict[str, Any]) -> list[str]:
        collected: list[str] = []
        result = tool_output.get("result")
        if not isinstance(result, dict):
            return collected

        direct_limitations = result.get("limitations")
        if isinstance(direct_limitations, list):
            collected.extend(str(item) for item in direct_limitations)

        player = result.get("player")
        if isinstance(player, dict):
            collected.extend(self._collect_player_notes(player))

        team = result.get("team")
        if isinstance(team, dict):
            collected.extend(self._collect_team_notes(team))

        for field_name in ("players", "player_a", "player_b"):
            value = result.get(field_name)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        collected.extend(self._collect_player_notes(item))
            elif isinstance(value, dict):
                collected.extend(self._collect_player_notes(value))

        return self._dedupe_limitations(collected)

    def _collect_player_notes(self, payload: dict[str, Any]) -> list[str]:
        collected: list[str] = []
        collected.extend(self._collect_notes_from_coverage(payload.get("source_coverage")))
        collected.extend(self._collect_notes_from_coverage(payload.get("moneypuck_coverage")))
        return collected

    def _collect_team_notes(self, payload: dict[str, Any]) -> list[str]:
        collected: list[str] = []
        collected.extend(self._collect_notes_from_coverage(payload.get("source_coverage")))
        collected.extend(self._collect_notes_from_coverage(payload.get("moneypuck_coverage")))
        return collected

    def _collect_notes_from_coverage(self, coverage: Any) -> list[str]:
        collected: list[str] = []
        if not isinstance(coverage, dict):
            return collected

        notes = coverage.get("notes")
        if not isinstance(notes, list):
            return collected

        for note in notes:
            if isinstance(note, dict) and isinstance(note.get("detail"), str):
                collected.append(note["detail"])
        return collected

    def _dedupe_limitations(self, limitations: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in limitations:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped
