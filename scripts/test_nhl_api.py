from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://api-web.nhle.com/v1"
DEFAULT_PATH = "standings/now"


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    query_items = [arg.split("=", 1) for arg in sys.argv[2:] if "=" in arg]
    query = urllib.parse.urlencode(query_items)
    url = f"{API_BASE}/{path}"

    if query:
        url = f"{url}?{query}"

    print(f"Requesting: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.nhl.com/",
            "Origin": "https://www.nhl.com",
        },
        method="GET",
    )

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
