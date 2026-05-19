from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_nhl_rules_rag import (
    DEFAULT_EVAL_PATH,
    DEFAULT_KEYWORD_THRESHOLD,
    DEFAULT_RESULTS_PATH,
    DEFAULT_TOP_K,
    console_summary,
    run_response_eval,
    run_retrieval_eval,
    write_results,
)


def run_retrieval(eval_path: str, top_k: int, keyword_threshold: float):
    payload = asyncio.run(
        run_retrieval_eval(
            eval_path=Path(eval_path),
            top_k=int(top_k),
            keyword_threshold=float(keyword_threshold),
        )
    )
    output_path = DEFAULT_RESULTS_PATH.with_name("rulebook_retrieval_latest.json")
    write_results(output_path, payload)
    return f"{console_summary(payload)}\nResults: {output_path}", payload


def run_response(eval_path: str, top_k: int, keyword_threshold: float):
    payload = asyncio.run(
        run_response_eval(
            eval_path=Path(eval_path),
            top_k=int(top_k),
            keyword_threshold=float(keyword_threshold),
        )
    )
    output_path = DEFAULT_RESULTS_PATH.with_name("rulebook_response_latest.json")
    write_results(output_path, payload)
    return f"{console_summary(payload)}\nResults: {output_path}", payload


def build_app() -> gr.Blocks:
    with gr.Blocks(title="NHL Rules RAG Eval") as demo:
        gr.Markdown("# NHL Rules RAG Eval\nRulebook-only testing UI for retrieval and response quality.")
        with gr.Row():
            eval_path = gr.Textbox(
                label="Eval JSONL Path",
                value=str(DEFAULT_EVAL_PATH),
                scale=4,
            )
            top_k = gr.Number(label="Top K", value=DEFAULT_TOP_K, precision=0, scale=1)
            keyword_threshold = gr.Number(
                label="Keyword Threshold",
                value=DEFAULT_KEYWORD_THRESHOLD,
                precision=2,
                scale=1,
            )

        with gr.Row():
            test_retrieval = gr.Button("Test Retrieval", variant="primary")
            test_response = gr.Button("Test Response", variant="secondary")

        summary = gr.Textbox(label="Summary", lines=8)
        details = gr.JSON(label="Detailed Results")

        test_retrieval.click(
            fn=run_retrieval,
            inputs=[eval_path, top_k, keyword_threshold],
            outputs=[summary, details],
        )
        test_response.click(
            fn=run_response,
            inputs=[eval_path, top_k, keyword_threshold],
            outputs=[summary, details],
        )

    return demo


if __name__ == "__main__":
    build_app().launch()
