from __future__ import annotations

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
    OrchestratedAnswerResult,
    PlayerComparisonQuery,
    PlayerSearchFilters,
    PlayerToolQuery,
    ToolInvocationRecord,
)
from .tools import PlayerToolService


SYSTEM_PROMPT = """
You are HockeyOps AI v0.5.

You are a hockey-first assistant. Answer NHL and hockey-operations questions directly.

Use backend tools whenever factual player, roster, stat, or contract information is needed.

Hard rules:
- Do not invent stats, contract terms, clauses, team context, or player facts.
- Stay inside the current v0.5 product focus: NHL and hockey topics only.
- Do not claim advanced analytics, MoneyPuck insights, or strategic team-fit conclusions.
- If the question is subjective or evaluative, you may give a clearly labeled hockey opinion or judgment.
- For subjective questions, use tool-returned facts when helpful, but do not refuse only because there is no single objectively verifiable answer.
- For broad subjective questions without a stated criterion, answer with your best hockey judgment first, then optionally mention a few factual ways to narrow it.
- If answer to question depends on facts the tools cannot provide, say what is missing plainly instead of pretending certainty.
- Use the tool outputs as the source of truth.
- If the user is comparing two players or asking who had the better season, use compare_players rather than separate summary calls.
- For season-stat questions, set the tool argument season_type explicitly.
- Use season_type=regular_season by default.
- Use season_type=playoffs only when the user explicitly needs playoff or postseason stats.
- Use season_type=both only when the user explicitly asks for both regular-season and playoff stats in the same answer.

Output style:
- Keep the answer concise and direct.
- Write in plain natural text, like a smart friend texting an analysis.
- Do not use markdown, bold, headers, or code formatting.
- Avoid nested bullets. Prefer short paragraphs or compact plain-text lines.
- Include explicit limitations when source coverage is incomplete or the question exceeds scope.
- If comparing or ranking players, base all takeaways only on tool-returned data.
- If answering with opinion, say it is your view and separate opinion from hard facts.
- When citing a player's season production, include games played (GP) alongside the scoring line when available.
- If player games played differ meaningfully, discuss both total production and rate production.
- Do not treat a tiny total-point edge as decisive without acknowledging the games-played context.
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


class HockeyOpsOrchestrator:
    def __init__(self, settings: Settings, tool_service: PlayerToolService) -> None:
        self._settings = settings
        self._tool_service = tool_service
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
                tool_output = await self._execute_tool_call(tool_call.name, tool_call.arguments)
                tool_invocations.append(
                    ToolInvocationRecord(
                        tool_name=tool_call.name,
                        arguments=json.loads(tool_call.arguments),
                        output=tool_output,
                    )
                )
                limitations.extend(self._collect_limitations(tool_output))
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(tool_output),
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
                "name": "search_players",
                "description": (
                    "Search the current active NHL roster universe using factual NHL and CapWages filters. "
                    "Stat filters and ranking use the requested season_type. "
                    "Use this for discovery questions, candidate lists, age/team/position/contract buckets, "
                    "or when the user asks for players matching a profile."
                ),
                "strict": True,
                "parameters": self._search_players_schema(),
            },
            {
                "type": "function",
                "name": "get_player_profile",
                "description": (
                    "Fetch one player's NHL profile, identity, season stats, and recent form. "
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
                    "Fetch one merged player object combining NHL profile/stats with CapWages contract data. "
                    "Set season_type explicitly when the user needs playoff/postseason stats or both regular-season and playoff lines."
                ),
                "strict": True,
                "parameters": self._player_query_schema(),
            },
            {
                "type": "function",
                "name": "compare_players",
                "description": (
                    "Compare two current NHL roster players side by side using factual NHL and CapWages data. "
                    "Set season_type to playoffs when the comparison should use playoff stats instead of regular-season stats."
                ),
                "strict": True,
                "parameters": self._player_comparison_schema(),
            },
        ]

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
                "sort_by": {
                    "type": "string",
                    "enum": [
                        "points_desc",
                        "goals_desc",
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
                "sort_by",
                "limit",
            ],
        }

    async def _execute_tool_call(self, name: str, raw_arguments: str) -> dict[str, Any]:
        arguments = json.loads(raw_arguments)
        try:
            if name == "search_players":
                result = await self._tool_service.search_players(PlayerSearchFilters.model_validate(arguments))
                return {"ok": True, "result": result.model_dump(mode="json")}

            if name == "get_player_profile":
                result = await self._tool_service.get_player_profile(PlayerToolQuery.model_validate(arguments))
                return {"ok": True, "result": result.model_dump(mode="json")}

            if name == "get_player_contract":
                result = await self._tool_service.get_player_contract(PlayerToolQuery.model_validate(arguments))
                return {"ok": True, "result": result.model_dump(mode="json")}

            if name == "get_player_summary_data":
                result = await self._tool_service.get_player_summary_data(PlayerToolQuery.model_validate(arguments))
                return {"ok": True, "result": result.model_dump(mode="json")}

            if name == "compare_players":
                query = PlayerComparisonQuery.model_validate(arguments)
                result = await self._tool_service.compare_players(
                    PlayerToolQuery(player=query.player_a, nhl_id=query.player_a_nhl_id),
                    PlayerToolQuery(player=query.player_b, nhl_id=query.player_b_nhl_id),
                    query.season_type,
                )
                return {"ok": True, "result": result.model_dump(mode="json")}

            return {
                "ok": False,
                "error": {
                    "type": "unknown_tool",
                    "message": f"Tool '{name}' is not registered.",
                },
            }
        except (
            PlayerNotFoundError,
            AmbiguousPlayerError,
            IdentityResolutionError,
            UpstreamRequestError,
            MissingConfigurationError,
            ValueError,
        ) as error:
            return {
                "ok": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }

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
            collected.extend(self._collect_source_notes(player))

        for field_name in ("players", "player_a", "player_b"):
            value = result.get(field_name)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        collected.extend(self._collect_source_notes(item))
            elif isinstance(value, dict):
                collected.extend(self._collect_source_notes(value))

        return self._dedupe_limitations(collected)

    def _collect_source_notes(self, payload: dict[str, Any]) -> list[str]:
        collected: list[str] = []
        source_coverage = payload.get("source_coverage")
        if not isinstance(source_coverage, dict):
            return collected

        notes = source_coverage.get("notes")
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
