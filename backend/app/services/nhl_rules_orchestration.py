from __future__ import annotations

import json

from openai import AsyncOpenAI

from ..config import Settings
from ..errors import MissingConfigurationError
from ..models import OrchestratedAnswerResult, ToolInvocationRecord
from .nhl_rules_rag import NHLRulesRAGService, NHLRulesRetrievalResult


RULEBOOK_SYSTEM_PROMPT = """
You are HockeyOps AI's NHL Rulebook assistant.

Answer only from the retrieved NHL Rulebook context supplied in the request.

Hard rules:
- The current rules corpus is the NHL Rulebook only.
- Do not answer CBA, salary cap, contract, free agency, waiver, arbitration, or labor-agreement questions from memory.
- If the question is outside Rulebook scope or the retrieved context is insufficient, say that plainly.
- Do not invent rule numbers, page references, exceptions, procedures, or disciplinary standards.
- Use the retrieved context as the source of truth.
- Include concise source references using the source labels provided with the context.
- Keep the answer direct and practical.
- Do not mention internal retrieval, embeddings, Chroma, chunks, or tool names.
""".strip()


class NHLRulesOrchestrator:
    def __init__(self, settings: Settings, rag_service: NHLRulesRAGService) -> None:
        self._settings = settings
        self._rag_service = rag_service
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def answer_question(self, question: str) -> OrchestratedAnswerResult:
        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is missing. Add it to the root .env before using NHL Rules answers."
            )

        retrieval = await self._rag_service.retrieve(question)
        tool_invocation = self._retrieval_tool_invocation(retrieval)
        answer_text, response_id = await self._create_answer(question, retrieval)

        return OrchestratedAnswerResult(
            model=self._settings.openai_answer_model,
            answer_text=self._clean_answer_text(answer_text),
            display_items=[],
            tool_invocations=[tool_invocation],
            limitations=[],
            response_id=response_id,
        )

    async def _create_answer(
        self,
        question: str,
        retrieval: NHLRulesRetrievalResult,
    ) -> tuple[str, str | None]:
        payload = {
            "question": question,
            "rulebook_context": [
                {
                    "source": self._source_label(chunk.document, chunk.page_start, chunk.page_end),
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                }
                for chunk in retrieval.chunks
            ],
        }
        response = await self._client.responses.create(
            model=self._settings.openai_answer_model,
            instructions=RULEBOOK_SYSTEM_PROMPT,
            input=[{"role": "user", "content": json.dumps(payload)}],
            max_output_tokens=self._settings.openai_max_output_tokens,
        )
        return response.output_text, getattr(response, "id", None)

    def _retrieval_tool_invocation(self, retrieval: NHLRulesRetrievalResult) -> ToolInvocationRecord:
        return ToolInvocationRecord(
            tool_name="retrieve_nhl_rules_context",
            arguments={
                "question": retrieval.question,
                "top_k": retrieval.top_k,
            },
            output={
                "ok": True,
                "result": {
                    "chunks": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "document": chunk.document,
                            "title": chunk.title,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "source_path": chunk.source_path,
                            "score": chunk.score,
                            "text_preview": chunk.text_preview,
                        }
                        for chunk in retrieval.chunks
                    ],
                },
            },
        )

    def _source_label(self, document: str, page_start: int, page_end: int) -> str:
        title = "NHL Rulebook" if document == "rulebook" else document
        if page_start and page_end and page_start != page_end:
            return f"{title}, pages {page_start}-{page_end}"
        if page_start:
            return f"{title}, page {page_start}"
        return title

    def _clean_answer_text(self, raw_text: str) -> str:
        cleaned = raw_text.replace("**", "").replace("__", "").replace("`", "")
        cleaned = cleaned.replace("\r\n", "\n")
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        return cleaned.strip()
