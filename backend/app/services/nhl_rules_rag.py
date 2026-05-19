from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from ..config import Settings
from ..errors import MissingConfigurationError


@dataclass(frozen=True)
class NHLRulesRetrievedChunk:
    chunk_id: str
    document: str
    title: str
    page_start: int
    page_end: int
    source_path: str
    score: float | None
    text: str
    text_preview: str


@dataclass(frozen=True)
class NHLRulesRetrievalResult:
    question: str
    top_k: int
    chunks: list[NHLRulesRetrievedChunk]


class NHLRulesRAGService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self._collection: Any | None = None
        self._available = False
        self._unavailable_reason: str | None = None
        self._record_count = 0
        self._initialize_collection()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    @property
    def record_count(self) -> int:
        return self._record_count

    def _initialize_collection(self) -> None:
        if not self._settings.nhl_rules_rag_enabled:
            self._mark_unavailable("NHL Rules RAG is disabled.")
            return

        if not self._settings.nhl_rules_chroma_path.exists():
            self._mark_unavailable(
                f"NHL Rules Chroma index not found at {self._settings.nhl_rules_chroma_path}."
            )
            return

        try:
            import chromadb
        except ModuleNotFoundError:
            self._mark_unavailable("ChromaDB is not installed.")
            return

        try:
            chroma_client = chromadb.PersistentClient(path=str(self._settings.nhl_rules_chroma_path))
            self._collection = chroma_client.get_collection(self._settings.nhl_rules_chroma_collection)
            self._record_count = int(self._collection.count())
        except Exception as error:
            self._mark_unavailable(f"NHL Rules Chroma collection is unavailable: {error}")
            return

        if self._record_count <= 0:
            self._mark_unavailable("NHL Rules Chroma collection is empty.")
            return

        self._available = True
        self._unavailable_reason = None

    def _mark_unavailable(self, reason: str) -> None:
        self._available = False
        self._unavailable_reason = reason
        self._collection = None
        self._record_count = 0

    async def retrieve(self, question: str, top_k: int | None = None) -> NHLRulesRetrievalResult:
        if not self._available or self._collection is None:
            raise MissingConfigurationError(
                self._unavailable_reason
                or "NHL Rules Chroma index is not available. Build the rules index before retrieval."
            )

        if self._client is None:
            raise MissingConfigurationError(
                "OPENAI_API_KEY is required to embed NHL Rules retrieval questions."
            )

        limit = top_k if top_k is not None else self._settings.nhl_rules_top_k
        limit = max(1, min(limit, self._record_count))
        query_embedding = await self._embed_query(question)
        response = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        chunks = self._parse_query_response(response)
        return NHLRulesRetrievalResult(question=question, top_k=limit, chunks=chunks)

    async def _embed_query(self, question: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._settings.openai_embedding_model,
            input=question,
        )
        return response.data[0].embedding

    def _parse_query_response(self, response: dict[str, Any]) -> list[NHLRulesRetrievedChunk]:
        ids = response.get("ids", [[]])[0]
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]

        chunks: list[NHLRulesRetrievedChunk] = []
        for index, chunk_id in enumerate(ids):
            text = documents[index] if index < len(documents) and documents[index] else ""
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            distance = distances[index] if index < len(distances) else None
            score = None if distance is None else 1 - float(distance)
            chunks.append(
                NHLRulesRetrievedChunk(
                    chunk_id=str(metadata.get("chunk_id") or chunk_id),
                    document=str(metadata.get("document") or "rulebook"),
                    title=str(metadata.get("title") or "NHL Rulebook"),
                    page_start=int(metadata.get("page_start") or 0),
                    page_end=int(metadata.get("page_end") or 0),
                    source_path=str(metadata.get("source_path") or ""),
                    score=score,
                    text=text,
                    text_preview=self._preview_text(text),
                )
            )

        return chunks

    def _preview_text(self, text: str, limit: int = 260) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}..."
