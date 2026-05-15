from __future__ import annotations

import json
import sys

import httpx


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python scripts/test_phase6_api.py "<question>" [base_url]')
        return 1

    question = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"

    response = httpx.post(
        f"{base_url}/api/ask",
        json={"question": question},
        timeout=120.0,
    )

    print(f"Status: {response.status_code}")
    try:
        payload = response.json()
    except json.JSONDecodeError:
        print(response.text)
        return 1

    print(json.dumps(payload, indent=2))
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
