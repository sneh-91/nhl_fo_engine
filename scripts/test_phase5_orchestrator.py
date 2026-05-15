from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.clients.capwages import CapWagesClient
from backend.app.clients.nhl import NHLClient
from backend.app.config import get_settings
from backend.app.services.normalization import PlayerNormalizer
from backend.app.services.orchestration import HockeyOpsOrchestrator
from backend.app.services.tools import PlayerToolService


async def main() -> int:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print("Usage: python scripts/test_phase5_orchestrator.py <question>")
        return 1

    settings = get_settings()
    nhl_client = NHLClient(settings)
    capwages_client = CapWagesClient(settings)
    normalizer = PlayerNormalizer()
    tool_service = PlayerToolService(settings, nhl_client, capwages_client, normalizer)
    orchestrator = HockeyOpsOrchestrator(settings, tool_service)

    try:
        result = await orchestrator.answer_question(question)
    finally:
        await nhl_client.aclose()
        await capwages_client.aclose()

    print("Model:", result.model)
    print("Response ID:", result.response_id)
    print("\nAnswer:\n")
    print(result.answer_text)
    print("\nTools used:")
    for invocation in result.tool_invocations:
        print(f"- {invocation.tool_name}: {invocation.arguments}")
    if result.limitations:
        print("\nLimitations:")
        for limitation in result.limitations:
            print(f"- {limitation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
