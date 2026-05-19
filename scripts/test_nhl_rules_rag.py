from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app


DEFAULT_QUESTION = "When is icing waived off?"


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION

    with TestClient(app) as client:
        response = client.post(
            "/api/ask",
            json={
                "question": question,
                "question_mode": "nhl_rules",
            },
        )

    print(f"Status: {response.status_code}")
    if not response.is_success:
        print(response.text)
        return 1

    payload = response.json()
    answer_text = payload.get("answer_text", "").strip()
    tool_invocations = payload.get("support_data", {}).get("tool_invocations", [])
    retrieval_invocation = next(
        (
            invocation
            for invocation in tool_invocations
            if invocation.get("tool_name") == "retrieve_nhl_rules_context"
        ),
        None,
    )
    chunks = []
    if retrieval_invocation:
        chunks = retrieval_invocation.get("output", {}).get("result", {}).get("chunks", [])

    if not answer_text:
        print("FAIL: response answer_text is empty.")
        return 1
    if not chunks:
        print("FAIL: response does not include retrieved NHL Rules chunks.")
        return 1

    print(f"Question: {payload.get('question')}")
    print(f"Answer chars: {len(answer_text)}")
    print(f"Retrieved chunks: {len(chunks)}")
    print(f"Top chunk: {chunks[0].get('chunk_id')} pages {chunks[0].get('page_start')}-{chunks[0].get('page_end')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
