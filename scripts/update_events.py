"""Update /data/events.json from a news/events source.

Safe starter:
- does NOT modify baseline graph
- requires env vars to run

Set GitHub repo secrets:
- GDELT_QUERY (required)
- GDELT_TIMESPAN (optional, default 15m)

Example query:
  (iran OR israel) AND (strike OR attack)

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

OUT_PATH = os.path.join("data", "events.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    q = os.getenv("GDELT_QUERY")
    timespan = os.getenv("GDELT_TIMESPAN", "15m")

    if not q:
        print("No GDELT_QUERY set; leaving events.json unchanged.")
        return

    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": q,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 50,
        "timespan": timespan,
        "sort": "HybridRel",
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    articles = payload.get("articles", [])
    events = []
    for a in articles:
        events.append(
            {
                "id": a.get("url"),
                "published_at": a.get("seendate"),
                "headline": a.get("title"),
                "url": a.get("url"),
                "source": a.get("sourceCountry") or a.get("sourceCollection"),
                "confidence": 0.4,
                "tags": [],
            }
        )

    out = {
        "metadata": {
            "generated_at_utc": utc_now(),
            "source": "gdelt-doc-2.0",
            "timespan": timespan,
            "query": q,
        },
        "events": events,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(events)} events to {OUT_PATH}")


if __name__ == "__main__":
    main()
