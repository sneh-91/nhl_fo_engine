from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_BASE = "https://capwages.com/api/gateway/v1"
DEFAULT_ENDPOINT = "players"


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }

    api_key = os.environ.get("CAPWAGES_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "CAPWAGES_API_KEY is missing. Add it to .env using .env.example as a template."
        )

    headers["x-api-key"] = api_key

    return headers


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    load_env_file(project_root / ".env")

    endpoint = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENDPOINT
    identifier = sys.argv[2] if len(sys.argv) > 2 else ""
    path = f"{endpoint}/{identifier}" if identifier else endpoint
    url = f"{API_BASE}/{path}"

    print(f"Requesting: {url}")

    try:
        headers = build_headers()
    except RuntimeError as error:
        print(str(error))
        return 1

    request = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read().decode("utf-8")
    except urllib.error.URLError as error:
        print("Request failed.")
        print(error.reason)
        return 1

    print(f"Status: {status}")

    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
