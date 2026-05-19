from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings
from backend.app.services.nhl_rules_orchestration import NHLRulesOrchestrator
from backend.app.services.nhl_rules_rag import NHLRulesRAGService, NHLRulesRetrievedChunk


DEFAULT_EVAL_PATH = PROJECT_ROOT / "data" / "nhl" / "evals" / "rulebook_eval.jsonl"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "data" / "nhl" / "evals" / "results" / "rulebook_eval_latest.json"
DEFAULT_TOP_K = 6
DEFAULT_KEYWORD_THRESHOLD = 0.60


JUDGE_PROMPT = """
You are an evaluation judge for a Rulebook-only NHL Rules RAG system.

Compare only the generated answer to the expected answer. The expected answer is the sole reference. Do not use outside knowledge, retrieved context, or other sources.

Score each category from 1 to 5:
- accuracy: How factually correct is it compared to the reference answer? Only give 5/5 scores for perfect answers.
- completeness: How thoroughly does it address all aspects of the question, covering all the information from the reference answer?
- relevance: How well does it directly answer the specific question asked, giving no additional information?

Return only JSON with this exact shape:
{"accuracy": 1-5, "completeness": 1-5, "relevance": 1-5, "rationale": "<short explanation>"}
""".strip()


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_answer: str
    keywords: list[str]


@dataclass(frozen=True)
class RetrievalMetrics:
    mrr: float
    keyword_coverage: float
    matched_keywords: list[str]
    missing_keywords: list[str]
    first_relevant_rank: int | None


def normalize_text(value: str) -> str:
    cleaned = "".join(character.casefold() if character.isalnum() else " " for character in value)
    return " ".join(cleaned.split())


def keyword_found(keyword: str, text: str) -> bool:
    return normalize_text(keyword) in normalize_text(text)


def load_eval_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        question = str(payload.get("question", "")).strip()
        expected_answer = str(payload.get("expected_answer", "")).strip()
        keywords = payload.get("keywords")
        if not question or not expected_answer or not isinstance(keywords, list) or not keywords:
            raise ValueError(f"Invalid eval item on line {line_number}.")
        cleaned_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
        if not cleaned_keywords:
            raise ValueError(f"Invalid keywords on line {line_number}.")
        cases.append(EvalCase(question=question, expected_answer=expected_answer, keywords=cleaned_keywords))
    if not cases:
        raise ValueError(f"No eval cases found in {path}.")
    return cases


def compute_retrieval_metrics(
    *,
    chunks: list[NHLRulesRetrievedChunk],
    keywords: list[str],
    threshold: float,
) -> RetrievalMetrics:
    combined_text = "\n".join(chunk.text for chunk in chunks)
    matched_keywords = [keyword for keyword in keywords if keyword_found(keyword, combined_text)]
    missing_keywords = [keyword for keyword in keywords if keyword not in matched_keywords]
    keyword_coverage = len(matched_keywords) / len(keywords)

    first_relevant_rank: int | None = None
    for rank, chunk in enumerate(chunks, start=1):
        hits = sum(1 for keyword in keywords if keyword_found(keyword, chunk.text))
        if hits / len(keywords) >= threshold:
            first_relevant_rank = rank
            break

    mrr = 0.0 if first_relevant_rank is None else 1 / first_relevant_rank
    return RetrievalMetrics(
        mrr=mrr,
        keyword_coverage=keyword_coverage,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        first_relevant_rank=first_relevant_rank,
    )


def retrieved_chunk_payload(chunks: list[NHLRulesRetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "document": chunk.document,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "score": chunk.score,
            "text_preview": chunk.text_preview,
        }
        for chunk in chunks
    ]


async def run_retrieval_eval(
    *,
    eval_path: Path = DEFAULT_EVAL_PATH,
    top_k: int = DEFAULT_TOP_K,
    keyword_threshold: float = DEFAULT_KEYWORD_THRESHOLD,
) -> dict[str, Any]:
    settings = get_settings()
    rag_service = NHLRulesRAGService(settings)
    cases = load_eval_cases(eval_path)
    items: list[dict[str, Any]] = []

    for case in cases:
        retrieval = await rag_service.retrieve(case.question, top_k=top_k)
        metrics = compute_retrieval_metrics(
            chunks=retrieval.chunks,
            keywords=case.keywords,
            threshold=keyword_threshold,
        )
        items.append(
            {
                "question": case.question,
                "expected_answer": case.expected_answer,
                "keywords": case.keywords,
                "retrieval": {
                    "mrr": metrics.mrr,
                    "keyword_coverage": metrics.keyword_coverage,
                    "matched_keywords": metrics.matched_keywords,
                    "missing_keywords": metrics.missing_keywords,
                    "first_relevant_rank": metrics.first_relevant_rank,
                    "chunks": retrieved_chunk_payload(retrieval.chunks),
                },
            }
        )

    return build_result_payload(
        eval_path=eval_path,
        top_k=top_k,
        keyword_threshold=keyword_threshold,
        items=items,
        include_judge=False,
    )


async def run_response_eval(
    *,
    eval_path: Path = DEFAULT_EVAL_PATH,
    top_k: int = DEFAULT_TOP_K,
    keyword_threshold: float = DEFAULT_KEYWORD_THRESHOLD,
) -> dict[str, Any]:
    settings = get_settings()
    rag_service = NHLRulesRAGService(settings)
    orchestrator = NHLRulesOrchestrator(settings, rag_service)
    judge_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
    if judge_client is None:
        raise RuntimeError("OPENAI_API_KEY is required to run response judging.")

    cases = load_eval_cases(eval_path)
    items: list[dict[str, Any]] = []

    for case in cases:
        answer = await orchestrator.answer_question(case.question)
        retrieval_record = answer.tool_invocations[0].output["result"]["chunks"]
        retrieval_chunks = [
            NHLRulesRetrievedChunk(
                chunk_id=str(chunk["chunk_id"]),
                document=str(chunk["document"]),
                title=str(chunk["title"]),
                page_start=int(chunk["page_start"]),
                page_end=int(chunk["page_end"]),
                source_path=str(chunk["source_path"]),
                score=chunk["score"],
                text="",
                text_preview=str(chunk["text_preview"]),
            )
            for chunk in retrieval_record
        ]
        # Run a retrieval call as well so metrics can use full chunk text.
        retrieval = await rag_service.retrieve(case.question, top_k=top_k)
        metrics = compute_retrieval_metrics(
            chunks=retrieval.chunks,
            keywords=case.keywords,
            threshold=keyword_threshold,
        )
        judge = await judge_answer(
            client=judge_client,
            model=settings.openai_judge_model,
            expected_answer=case.expected_answer,
            generated_answer=answer.answer_text,
        )
        items.append(
            {
                "question": case.question,
                "expected_answer": case.expected_answer,
                "keywords": case.keywords,
                "generated_answer": answer.answer_text,
                "retrieval": {
                    "mrr": metrics.mrr,
                    "keyword_coverage": metrics.keyword_coverage,
                    "matched_keywords": metrics.matched_keywords,
                    "missing_keywords": metrics.missing_keywords,
                    "first_relevant_rank": metrics.first_relevant_rank,
                    "chunks": retrieved_chunk_payload(retrieval_chunks),
                },
                "judge": judge,
            }
        )

    return build_result_payload(
        eval_path=eval_path,
        top_k=top_k,
        keyword_threshold=keyword_threshold,
        items=items,
        include_judge=True,
    )


async def judge_answer(
    *,
    client: AsyncOpenAI,
    model: str,
    expected_answer: str,
    generated_answer: str,
) -> dict[str, Any]:
    payload = {
        "expected_answer": expected_answer,
        "generated_answer": generated_answer,
    }
    response = await client.responses.create(
        model=model,
        instructions=JUDGE_PROMPT,
        input=[{"role": "user", "content": json.dumps(payload)}],
        max_output_tokens=2000,
    )
    parsed = parse_judge_json(response.output_text)
    for key in ("accuracy", "completeness", "relevance"):
        value = parsed.get(key)
        if not isinstance(value, int) or value < 1 or value > 5:
            raise ValueError(f"Judge returned invalid {key}: {value!r}")
    if not isinstance(parsed.get("rationale"), str):
        raise ValueError("Judge returned invalid rationale.")
    parsed["model"] = model
    return parsed


def parse_judge_json(raw_text: str) -> dict[str, Any]:
    if not raw_text.strip():
        raise ValueError("Judge returned empty output.")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def build_result_payload(
    *,
    eval_path: Path,
    top_k: int,
    keyword_threshold: float,
    items: list[dict[str, Any]],
    include_judge: bool,
) -> dict[str, Any]:
    retrieval_mrr = average(item["retrieval"]["mrr"] for item in items)
    keyword_coverage = average(item["retrieval"]["keyword_coverage"] for item in items)
    aggregate: dict[str, Any] = {
        "mrr": retrieval_mrr,
        "keyword_coverage": keyword_coverage,
        "question_count": len(items),
    }
    if include_judge:
        aggregate["judge"] = {
            "accuracy": average(item["judge"]["accuracy"] for item in items),
            "completeness": average(item["judge"]["completeness"] for item in items),
            "relevance": average(item["judge"]["relevance"] for item in items),
        }

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "eval_path": str(eval_path),
        "top_k": top_k,
        "keyword_threshold": keyword_threshold,
        "aggregate": aggregate,
        "items": items,
    }


def average(values: Any) -> float:
    items = list(values)
    return sum(float(value) for value in items) / len(items) if items else 0.0


def write_results(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def console_summary(payload: dict[str, Any]) -> str:
    aggregate = payload["aggregate"]
    lines = [
        f"Questions: {aggregate['question_count']}",
        f"MRR: {aggregate['mrr']:.3f}",
        f"Keyword Coverage: {aggregate['keyword_coverage']:.3f}",
    ]
    if "judge" in aggregate:
        judge = aggregate["judge"]
        lines.extend(
            [
                f"Accuracy: {judge['accuracy']:.2f}/5",
                f"Completeness: {judge['completeness']:.2f}/5",
                f"Relevance: {judge['relevance']:.2f}/5",
            ]
        )
    return "\n".join(lines)


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Rulebook-only NHL Rules RAG pipeline.")
    parser.add_argument("--eval-path", type=Path, default=DEFAULT_EVAL_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--keyword-threshold", type=float, default=DEFAULT_KEYWORD_THRESHOLD)
    parser.add_argument(
        "--mode",
        choices=["retrieval", "response"],
        default="retrieval",
        help="Run retrieval-only metrics or full answer generation plus judge.",
    )
    args = parser.parse_args()

    if args.mode == "response":
        payload = await run_response_eval(
            eval_path=args.eval_path,
            top_k=args.top_k,
            keyword_threshold=args.keyword_threshold,
        )
    else:
        payload = await run_retrieval_eval(
            eval_path=args.eval_path,
            top_k=args.top_k,
            keyword_threshold=args.keyword_threshold,
        )

    write_results(args.output_path, payload)
    print(console_summary(payload))
    print(f"Results: {args.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
