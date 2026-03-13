#!/usr/bin/env python3
"""update_events.py

Fetches a rolling events/news feed from GDELT and writes it to data/events.json.

Phase 4 (automation) improvement:
- Auto-tags events to your map nodes so the UI can show "Related events" per node.

Required env var:
- GDELT_QUERY: a GDELT Document API query string

Optional env var:
- GDELT_TIMESPAN: e.g. 6h, 1d, 3d, 14d (default: 14d)
- MAX_EVENTS: max events to write (default: 120)

Notes:
- Tagging is heuristic (string match on node name / aliases). Keep it conservative by curating node.aliases.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MAP_DATA_PATH = DATA_DIR / "map_data.json"
OUT_PATH = DATA_DIR / "events.json"

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

QUERY = os.getenv("GDELT_QUERY", "").strip()
TIMESPAN = os.getenv("GDELT_TIMESPAN", "14d").strip() or "14d"
MAX_EVENTS = int(os.getenv("MAX_EVENTS", "120"))


def _utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _gdelt_seendate_to_iso(seendate: Optional[str]) -> Optional[str]:
    """Convert GDELT seendate formats into ISO 8601.

    GDELT commonly returns seendate as YYYYMMDDHHMMSS.
    """
    if not seendate:
        return None
    s = str(seendate).strip()
    if re.fullmatch(r"\d{14}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}Z"
    # If it's already ISO-ish, keep it.
    return s


def _load_node_patterns() -> List[Tuple[str, re.Pattern]]:
    """Build regex patterns for tagging articles to nodes.

    Uses node.name + node.aliases + node.geoName (if provided).

    Tip: For ambiguous names, add more specific aliases.
    """
    try:
        data = json.loads(MAP_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    patterns: List[Tuple[str, re.Pattern]] = []

    for n in data.get("nodes", []):
        node_id = n.get("id")
        name = (n.get("name") or "").strip()
        if not node_id or not name:
            continue

        # Collect terms
        terms: List[str] = [name]
        for a in (n.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                terms.append(a.strip())
        geo = n.get("geoName")
        if isinstance(geo, str) and geo.strip() and geo.strip() not in terms:
            terms.append(geo.strip())

        # Filter & de-dupe
        # - allow 2-char org acronyms (EU, UN)
        # - otherwise require >= 3 chars to reduce noise
        min_len = 2 if (n.get("type") == "org") else 3
        seen = set()
        cleaned: List[str] = []
        for t in terms:
            t = t.strip()
            if len(t) < min_len:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(t)

        for t in cleaned:
            # Use "not a word char" boundaries so terms like "U.S." can still match.
            pat = re.compile(r"(?i)(?<![\w])" + re.escape(t) + r"(?![\w])")
            patterns.append((node_id, pat))

    return patterns


NODE_PATTERNS = _load_node_patterns()


def _tags_for_text(text: str) -> List[str]:
    if not text:
        return []
    out: List[str] = []
    seen = set()
    for node_id, pat in NODE_PATTERNS:
        if node_id in seen:
            continue
        if pat.search(text):
            seen.add(node_id)
            out.append(node_id)
        if len(out) >= 12:
            break
    return out


def fetch_gdelt(query: str, timespan: str) -> Dict[str, Any]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "timespan": timespan,
        "sort": "HybridRel",
        "format": "json",
        "maxrecords": str(MAX_EVENTS),
    }
    r = requests.get(GDELT_DOC_API, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    if not QUERY:
        print("GDELT_QUERY not set; skipping events update.")
        return 0

    payload = fetch_gdelt(QUERY, TIMESPAN)
    articles = payload.get("articles") or []

    events: List[Dict[str, Any]] = []

    for i, a in enumerate(articles[:MAX_EVENTS]):
        title = (a.get("title") or "").strip()
        url = (a.get("url") or "").strip()
        if not title or not url:
            continue

        published_at = _gdelt_seendate_to_iso(a.get("seendate"))

        # Tag using title + url (you can expand to description if you add it)
        tags = _tags_for_text(f"{title} {url}")

        events.append(
            {
                "id": f"gdelt_{i}",
                "headline": title,
                "url": url,
                "published_at": published_at,
                "source": (a.get("domain") or a.get("sourceCountry") or "GDELT"),
                "tags": tags,
            }
        )

    out = {
        "metadata": {
            "generated_at_utc": _utc_now_iso(),
            "provider": "GDELT_DOC_API",
            "query": QUERY,
            "timespan": TIMESPAN,
            "max_events": MAX_EVENTS,
            "tagging": {
                "method": "string_match",
                "uses": ["node.name", "node.aliases", "node.geoName"],
                "notes": "Heuristic tagging. Curate aliases for precision."
            },
        },
        "events": events,
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(events)} events to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
