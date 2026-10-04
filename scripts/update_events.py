#!/usr/bin/env python3
"""update_events.py

Fetch conflict-related events from GDELT and write data/events.json (+ meta freshness).

Design goals:
- Runs reliably on schedule with minimal external dependencies (stdlib HTTP client).
- Supports two query streams (core + tripwire) with sensible defaults.
- Handles partial failures without leaking raw query strings.
- Produces explicit metadata so freshness/health are auditable.
"""

from __future__ import annotations

import datetime as _dt
import email.utils
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MAP_DATA_PATH = DATA_DIR / "map_data.json"
META_PATH = DATA_DIR / "meta.json"
OUT_PATH = DATA_DIR / "events.json"

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Environment overrides. If secrets are absent, defaults keep the pipeline alive.
DEFAULT_CORE_QUERY = '("war" OR "armed conflict" OR "ceasefire" OR "airstrike" OR "missile")'
DEFAULT_TRIPWIRE_QUERY = '("sanctions" OR "military aid" OR "troop deployment" OR "cross-border" OR "escalation")'

CORE_QUERY = os.getenv("GDELT_QUERY", "").strip() or DEFAULT_CORE_QUERY
TRIPWIRE_QUERY = os.getenv("GDELT_TRIPWIRE_QUERY", "").strip() or DEFAULT_TRIPWIRE_QUERY
TIMESPAN = os.getenv("GDELT_TIMESPAN", "6h").strip() or "6h"
MAX_EVENTS = int(os.getenv("MAX_EVENTS", "120"))
MAX_TAGS_PER_EVENT = int(os.getenv("MAX_TAGS_PER_EVENT", "12"))
PER_TAG_PER_DAY_LIMIT = int(os.getenv("PER_TAG_PER_DAY_LIMIT", "3"))
DRY_RUN = os.getenv("DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}

# Resilience knobs: GDELT rate-limits aggressively (HTTP 429). The old
# [1, 2, 4, 8]s backoff could not ride out a limit window, so nearly every
# hourly run died here.
GDELT_MAX_RETRIES = int(os.getenv("GDELT_MAX_RETRIES", "6"))
# Pause between the two query streams so we don't fire back-to-back requests.
STREAM_STAGGER_SECS = int(os.getenv("STREAM_STAGGER_SECS", "20"))
# Exponential backoff schedule (seconds); jitter is added per attempt.
_RETRY_BACKOFFS = [5, 15, 30, 60, 120]

# Fallback provider: conflict-news RSS feeds. Fully keyless (no API keys, no
# registration), so it works with zero setup. It only fires when GDELT yields
# zero usable articles, and its only job is to keep the feed alive with fresh
# items instead of going stale or blank.
FALLBACK_ENABLED = os.getenv("FALLBACK_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
FALLBACK_RSS_FEEDS = [
    u.strip()
    for u in os.getenv(
        "FALLBACK_RSS_FEEDS",
        "https://feeds.bbci.co.uk/news/world/rss.xml,"
        "https://www.aljazeera.com/xml/rss/all.xml,"
        "https://www.france24.com/en/rss",
    ).split(",")
    if u.strip()
]
FALLBACK_MAX_ITEMS_PER_FEED = int(os.getenv("FALLBACK_MAX_ITEMS_PER_FEED", "40"))
# Keep the fallback on-theme: only items matching conflict keywords are kept.
_FALLBACK_KEYWORDS = (
    "war", "conflict", "ceasefire", "airstrike", "air strike", "missile",
    "troop", "military", "sanction", "invasion", "offensive", "bombing",
    "shelling", "hostage", "escalat", "armed", "insurgent", "militant",
    "drone", "truce", "peace talk", "refugee", "evacuat", "casualt",
)
_FALLBACK_OUTLETS = {
    "feeds.bbci.co.uk": "BBC News",
    "www.aljazeera.com": "Al Jazeera",
    "www.france24.com": "France 24",
}


def _utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _day_bucket(iso: Optional[str]) -> str:
    if not iso:
        return "unknown"
    return str(iso).split("T", 1)[0]


def _gdelt_seendate_to_iso(seendate: Optional[str]) -> Optional[str]:
    if not seendate:
        return None
    s = str(seendate).strip()
    if re.fullmatch(r"\d{14}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}Z"
    return s


def _load_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _load_node_patterns() -> List[Tuple[str, re.Pattern]]:
    data = _load_json(MAP_DATA_PATH, {"nodes": []})

    patterns: List[Tuple[str, re.Pattern]] = []
    for n in data.get("nodes", []):
        node_id = n.get("id")
        name = (n.get("name") or "").strip()
        if not node_id or not name:
            continue

        terms: List[str] = [name]
        for a in (n.get("aliases") or []):
            if isinstance(a, str) and a.strip():
                terms.append(a.strip())

        geo = n.get("geoName")
        if isinstance(geo, str) and geo.strip():
            terms.append(geo.strip())

        min_len = 2 if (n.get("type") == "org") else 3
        dedup = []
        seen = set()
        for t in terms:
            t = t.strip()
            if len(t) < min_len:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(t)

        for t in dedup:
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
        if len(out) >= MAX_TAGS_PER_EVENT:
            break

    return out


def _backoff_with_jitter(attempt: int, retry_after: Optional[float] = None) -> float:
    base = _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)]
    if retry_after is not None:
        base = max(base, min(retry_after, 300.0))
    # +/-20% jitter so concurrent runners don't stampede in lockstep
    return base * (0.8 + 0.4 * random.random())


def _retry_after_seconds(headers: Any) -> Optional[float]:
    try:
        raw = headers.get("Retry-After") if headers else None
        if raw is None:
            return None
        return max(0.0, float(str(raw).strip()))
    except Exception:
        return None


def _query_gdelt(params: Dict[str, str], retries: Optional[int] = None) -> Dict[str, Any]:
    retries = retries if retries is not None else GDELT_MAX_RETRIES
    last_error: Optional[str] = None

    for attempt in range(retries):
        url = GDELT_DOC_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "WorldWarEventsBot/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                status = getattr(resp, "status", 200)
                body = resp.read().decode("utf-8", errors="replace")
                ctype = str(resp.headers.get("Content-Type", "")).lower()

                if status == 429:
                    last_error = f"rate_limited status=429 content_type={ctype}"
                    if attempt < retries - 1:
                        wait = _backoff_with_jitter(attempt, _retry_after_seconds(resp.headers))
                        print(f"GDELT 429 (attempt {attempt + 1}/{retries}); retrying in {wait:.0f}s")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(last_error)

                if 500 <= status < 600:
                    last_error = f"transient status={status} content_type={ctype}"
                    if attempt < retries - 1:
                        wait = _backoff_with_jitter(attempt)
                        print(f"GDELT {status} (attempt {attempt + 1}/{retries}); retrying in {wait:.0f}s")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(last_error)

                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    snippet = body[:240].replace("\n", " ")
                    raise RuntimeError(f"non-json response status={status} content_type={ctype} body={snippet}")

        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                last_error = "rate_limited status=429"
                if attempt < retries - 1:
                    wait = _backoff_with_jitter(attempt, _retry_after_seconds(exc.headers))
                    print(f"GDELT 429 (attempt {attempt + 1}/{retries}); retrying in {wait:.0f}s")
                    time.sleep(wait)
                    continue
                raise RuntimeError(last_error) from exc
            if 500 <= exc.code < 600:
                last_error = f"http_error status={exc.code}"
                if attempt < retries - 1:
                    wait = _backoff_with_jitter(attempt)
                    print(f"GDELT {exc.code} (attempt {attempt + 1}/{retries}); retrying in {wait:.0f}s")
                    time.sleep(wait)
                    continue
                raise RuntimeError(last_error) from exc
            raise RuntimeError(f"http_error status={exc.code}") from exc
        except urllib.error.URLError as exc:
            last_error = f"url_error reason={exc.reason}"
            if attempt < retries - 1:
                wait = _backoff_with_jitter(attempt)
                print(f"network error (attempt {attempt + 1}/{retries}); retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
            raise RuntimeError(last_error) from exc

    raise RuntimeError(last_error or "unknown query failure")


def fetch_stream(stream_name: str, query: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "timespan": TIMESPAN,
        "sort": "HybridRel",
        "maxrecords": str(MAX_EVENTS),
    }

    try:
        payload = _query_gdelt(params)
        articles = payload.get("articles") or []
        return articles, {"name": stream_name, "status": "ok", "fetched": len(articles)}
    except Exception as exc:
        return [], {"name": stream_name, "status": "error", "error": str(exc), "fetched": 0}


def _fallback_outlet_name(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        netloc = ""
    return _FALLBACK_OUTLETS.get(netloc, netloc or "RSS")


def _rss_pubdate_to_iso(pubdate: Optional[str]) -> Optional[str]:
    if not pubdate:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(str(pubdate).strip())
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _matches_fallback_keywords(title: str) -> bool:
    lowered = (title or "").lower()
    return any(kw in lowered for kw in _FALLBACK_KEYWORDS)


def _fetch_rss_feed(url: str, outlet: str) -> List[Dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "WorldWarEventsBot/1.0 (+rss-fallback)"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310
        raw = resp.read()
    root = ET.fromstring(raw)
    items: List[Dict[str, str]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "pubDate": (item.findtext("pubDate") or "").strip(),
                "outlet": outlet,
            }
        )
        if len(items) >= FALLBACK_MAX_ITEMS_PER_FEED:
            break
    return items


def fetch_fallback_articles() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pull conflict-themed items from RSS feeds.

    Returns article dicts shaped like GDELT articles (title/url/seendate/domain)
    so they flow through the same _build_events pipeline, plus a stream-style
    result dict for metadata.
    """
    articles: List[Dict[str, Any]] = []
    per_feed: List[Dict[str, Any]] = []

    for url in FALLBACK_RSS_FEEDS:
        outlet = _fallback_outlet_name(url)
        try:
            items = _fetch_rss_feed(url, outlet)
            kept = 0
            for it in items:
                if not _matches_fallback_keywords(it["title"]):
                    continue
                articles.append(
                    {
                        "title": it["title"],
                        "url": it["link"],
                        "seendate": _rss_pubdate_to_iso(it["pubDate"]),
                        "domain": outlet,
                    }
                )
                kept += 1
            per_feed.append(
                {"outlet": outlet, "status": "ok", "items": len(items), "kept": kept}
            )
        except Exception as exc:
            per_feed.append(
                {
                    "outlet": outlet,
                    "status": "error",
                    "error": str(exc)[:200],
                    "items": 0,
                    "kept": 0,
                }
            )

    articles = articles[:MAX_EVENTS]
    any_ok = any(f["status"] == "ok" for f in per_feed)
    if articles:
        status = "ok"
    elif any_ok:
        status = "empty"
    else:
        status = "error"
    return articles, {
        "name": "rss_fallback",
        "status": status,
        "fetched": len(articles),
        "feeds": per_feed,
    }


def _event_key(title: str, url: str) -> str:
    norm = f"{title.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _write_meta_events_timestamp(ts: str) -> None:
    meta = _load_json(META_PATH, {})
    meta["events_last_updated"] = ts
    if not DRY_RUN:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_previous_events() -> Dict[str, Any]:
    return _load_json(OUT_PATH, {"metadata": {}, "events": []})


def _build_events(articles: List[Dict[str, Any]], id_prefix: str = "gdelt") -> List[Dict[str, Any]]:
    seen = set()
    per_tag_day: Dict[str, int] = {}
    events: List[Dict[str, Any]] = []

    for a in articles:
        title = (a.get("title") or "").strip()
        url = (a.get("url") or "").strip()
        if not title or not url:
            continue

        key = _event_key(title, url)
        if key in seen:
            continue
        seen.add(key)

        published_at = _gdelt_seendate_to_iso(a.get("seendate"))
        day = _day_bucket(published_at)
        tags = _tags_for_text(f"{title} {url}")

        if tags:
            filtered_tags: List[str] = []
            for tag in tags:
                k = f"{tag}|{day}"
                c = per_tag_day.get(k, 0)
                if c >= PER_TAG_PER_DAY_LIMIT:
                    continue
                per_tag_day[k] = c + 1
                filtered_tags.append(tag)
            tags = filtered_tags

        events.append(
            {
                "id": f"{id_prefix}_{key}",
                "headline": title,
                "url": url,
                "published_at": published_at,
                "source": (a.get("domain") or a.get("sourceCountry") or "GDELT"),
                "tags": tags,
            }
        )

        if len(events) >= MAX_EVENTS:
            break

    return events


def main() -> int:
    now = _utc_now_iso()
    previous = _load_previous_events()

    streams = [("core", CORE_QUERY), ("tripwire", TRIPWIRE_QUERY)]
    all_articles: List[Dict[str, Any]] = []
    stream_results: List[Dict[str, Any]] = []

    for i, (stream_name, query) in enumerate(streams):
        if i > 0 and STREAM_STAGGER_SECS > 0:
            print(f"Staggering {STREAM_STAGGER_SECS}s before '{stream_name}' stream...")
            time.sleep(STREAM_STAGGER_SECS)
        if not query:
            stream_results.append({"name": stream_name, "status": "skipped", "fetched": 0})
            continue
        articles, result = fetch_stream(stream_name, query)
        stream_results.append(result)
        all_articles.extend(articles)

    failed_streams = [r for r in stream_results if r.get("status") == "error"]
    for r in failed_streams:
        print(f"- {r.get('name')}: {r.get('error')}")

    events = _build_events(all_articles)
    used_fallback = False

    if not events and FALLBACK_ENABLED:
        # GDELT gave us nothing usable: try the keyless RSS fallback so the
        # feed still gets fresh items instead of going stale or blank.
        print("GDELT yielded 0 usable articles; trying RSS fallback provider...")
        fb_articles, fb_result = fetch_fallback_articles()
        stream_results.append(fb_result)
        if fb_articles:
            events = _build_events(fb_articles, id_prefix="rss")
            used_fallback = bool(events)
            print(f"RSS fallback produced {len(events)} events.")

    if not events:
        # Nothing from any provider: keep previous events if we have them.
        # Stale data is better than a failed run: exit 0 so the schedule
        # stays green and the next hourly run retries. Freshness is still
        # honest — meta.events_last_updated is only bumped on real updates.
        if previous.get("events"):
            print("All providers yielded nothing; keeping previous events file unchanged.")
            return 0
        print("No previous events exist; nothing to fall back to.")
        return 1

    provider = "RSS_FALLBACK" if used_fallback else "GDELT_DOC_API"
    status = "ok"
    if used_fallback:
        status = "ok-fallback"
    elif failed_streams:
        status = "partial"

    out = {
        "metadata": {
            "generated_at_utc": now,
            "provider": provider,
            "status": status,
            "timespan": TIMESPAN,
            "max_events": MAX_EVENTS,
            "streams": stream_results,
            "fetched_articles": sum(
                int(r.get("fetched", 0))
                for r in stream_results
                if r.get("status") == "ok"
            ),
            "previous_event_count": len(previous.get("events") or []),
            "tagging": {
                "method": "string_match",
                "uses": ["node.name", "node.aliases", "node.geoName"],
                "notes": "Heuristic tagging with per-tag-per-day caps.",
                "per_tag_per_day_limit": PER_TAG_PER_DAY_LIMIT,
            },
        },
        "events": events,
    }

    if DRY_RUN:
        print(json.dumps(out["metadata"], ensure_ascii=False, indent=2))
        print(f"Dry run: would write {len(events)} events.")
        return 0

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_meta_events_timestamp(now)
    print(f"Wrote {len(events)} events to {OUT_PATH} (status={status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
