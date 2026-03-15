#!/usr/bin/env python3
"""update_map.py

Reads events.json, finds nodes with significant recent activity,
calls the Anthropic API to propose map_data.json patches,
and writes the result to data/map_data_proposed.json for human review.

Never commits directly to map_data.json — all changes go through a PR.

Usage:
  python scripts/update_map.py

Env vars required:
  ANTHROPIC_API_KEY   — Anthropic API key (store as GitHub secret)

Env vars optional:
  MIN_CLUSTER_SIZE    — Min events per node to trigger LLM review (default: 3)
  LOOKBACK_HOURS      — How many hours of events to consider (default: 24)
  DRY_RUN             — Set to "1" to print output without writing files
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EVENTS_PATH = DATA_DIR / "events.json"
MAP_DATA_PATH = DATA_DIR / "map_data.json"
PROPOSED_PATH = DATA_DIR / "map_data_proposed.json"
PATCH_PATH = DATA_DIR / "map_patch_latest.json"
SUMMARY_PATH = DATA_DIR / "map_patch_summary.md"

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

MIN_CLUSTER_SIZE = int(os.getenv("MIN_CLUSTER_SIZE", "3"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))
DRY_RUN = os.getenv("DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: Optional[str]) -> Optional[_dt.datetime]:
    if not s:
        return None
    s = str(s).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", s)
    if m:
        y, mo, d, h, mi, sec = (int(x) for x in m.groups())
        return _dt.datetime(y, mo, d, h, mi, sec, tzinfo=_dt.timezone.utc)
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_json(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


# ── Step 1: Cluster recent events by node tag ─────────────────────────────────

def cluster_events(events_data: Dict, lookback_hours: int) -> Dict[str, List[Dict]]:
    cutoff = _utc_now() - _dt.timedelta(hours=lookback_hours)
    clusters: Dict[str, List[Dict]] = {}
    for evt in (events_data.get("events") or []):
        dt = _parse_iso(evt.get("published_at"))
        if dt and dt < cutoff:
            continue
        for tag in (evt.get("tags") or []):
            clusters.setdefault(tag, []).append(evt)
    return clusters


def significant_clusters(clusters: Dict, min_size: int) -> Dict:
    return {k: v for k, v in clusters.items() if len(v) >= min_size}


# ── Step 2: Build prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a structured data extractor for a conflict mapping database.
Your job is to read recent news event clusters and the current state of affected nodes,
then propose a minimal JSON patch — only what actually changed — to keep the map current.

## Output format

Return ONLY valid JSON. No prose, no markdown fences, no explanation.
The JSON must have this exact top-level shape:

{
  "extracted_at": "<ISO datetime>",
  "source_title": "GDELT event cluster analysis",
  "nodes_add": [],
  "nodes_update": [],
  "edges_add": [],
  "edges_update": [],
  "nodes_remove": [],
  "edges_remove": [],
  "change_summary": "<2-3 sentence plain-English summary of what changed and why>"
}

## Node schema (nodes_add items)

{
  "id": "<SCREAMING_SNAKE_CASE max 40 chars>",
  "name": "<display name>",
  "type": "<state | territory | org | nonstate>",
  "geoName": "<exact ECharts world map name, or null for orgs>",
  "theaters": ["<ME | UKR | ASIA | AFR | AMER>"],
  "coords": [<longitude -180..180>, <latitude -90..90>],
  "category": "<WAR | ALLY | POLICY | SPILLOVER | TENSION | INTERNAL>",
  "ihl": "<brief IHL framing or null>",
  "exposure": "<brief exposure label or null>",
  "intensity": <0-10>,
  "color": "<hex: WAR=#ef4444 ALLY=#0ea5e9 POLICY=#10b981 SPILLOVER=#f97316 TENSION=#eab308 INTERNAL=#a855f7>",
  "summary": "<1-3 sentence editorial summary>",
  "updated_at": "<ISO datetime>",
  "confidence": "<High | Medium | Low>",
  "sources": [],
  "aliases": ["<alternate names for news matching>"],
  "tags": []
}

For nodes_update: include ONLY id + changed fields.
For nodes_remove / edges_remove: { "id": "<id>", "reason": "<why>" }

## Edge schema (edges_add items)

{
  "id": "<FROM__TO__CATEGORY>",
  "from": "<node id>",
  "to": "<node id>",
  "theater": "<ME | UKR | ASIA | AFR | AMER>",
  "category": "<WAR | ALLY | POLICY | SPILLOVER | TENSION | INTERNAL>",
  "type": "<short label>",
  "effect": "<solid | dashed | dotted>",
  "color": "<hex matching category>",
  "summary": "<1-2 sentence description>",
  "updated_at": "<ISO datetime>",
  "confidence": "<High | Medium | Low>",
  "sources": []
}

## Category rules

WAR       — Active kinetic conflict. Both sides of the fight get WAR category.
ALLY      — Military support, arms, co-belligerency, forward basing authorization.
POLICY    — Sanctions, financial aid, diplomatic opposition, training, maritime ops.
SPILLOVER — Indirect: refugee flows, cross-border strikes on third parties, chokepoint exposure.
TENSION   — Militarized standoff with no active kinetic exchange yet.
INTERNAL  — Civil war, NIAC, domestic insurgency — primarily intrastate.

## Confidence rules

High   — Multiple corroborating sources, well-documented
Medium — Single strong source or fast-moving but credible
Low    — Single secondary source, early reports, highly uncertain

## Critical rules

- ONLY propose changes directly supported by the event headlines.
- Do NOT invent actors or relationships not evidenced in the events.
- Do NOT update nodes not mentioned in the events.
- Prefer nodes_update over nodes_add — check existing IDs first.
- Fast-moving situations default to Medium or Low confidence.
- If nothing meaningful changed, return empty arrays and say so in change_summary.
"""


def build_user_message(clusters: Dict, map_data: Dict) -> str:
    nodes_by_id = {n["id"]: n for n in (map_data.get("nodes") or [])}
    parts: List[str] = [
        f"Today's date: {_utc_now_iso()}\n\n",
        "## Existing node IDs (use nodes_update not nodes_add for these)\n\n",
        ", ".join(sorted(nodes_by_id.keys())),
        "\n\n## Recent event clusters\n",
    ]

    for node_id, events in sorted(clusters.items(), key=lambda x: -len(x[1])):
        parts.append(f"\n### {node_id} — {len(events)} events\n")

        if node_id in nodes_by_id:
            n = nodes_by_id[node_id]
            parts.append(
                f"Current: category={n.get('category')} | ihl={n.get('ihl')} | "
                f"exposure={n.get('exposure')} | intensity={n.get('intensity')} | "
                f"confidence={n.get('confidence')}\n"
            )
            parts.append(f"Current summary: {n.get('summary', '')}\n")
            related = [
                e for e in map_data.get("edges", [])
                if e.get("from") == node_id or e.get("to") == node_id
            ]
            if related:
                parts.append("Current edges:\n")
                for e in related:
                    parts.append(f"  - {e['id']}: {e.get('from')} → {e.get('to')} [{e.get('category')}]\n")
        else:
            parts.append("NOT IN DATASET — add via nodes_add if the events justify it.\n")

        parts.append("\nHeadlines:\n")
        for evt in events[:10]:
            parts.append(f"  [{evt.get('source', '')}] {evt.get('headline', '')}\n")

    parts.append("\nPropose a JSON patch based on the above.")
    return "".join(parts)


# ── Step 3: Call Anthropic API ────────────────────────────────────────────────

def call_anthropic(system: str, user: str, api_key: str) -> str:
    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    for attempt, backoff in enumerate([2, 4, 8, 16]):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                raise RuntimeError(f"No text block in API response")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 529) and attempt < 3:
                time.sleep(backoff)
                continue
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API {exc.code}: {body[:300]}") from exc

    raise RuntimeError("Anthropic API failed after retries")


# ── Step 4: Parse + validate patch ───────────────────────────────────────────

def parse_patch(raw: str) -> Dict:
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\s*```$", "", clean.strip(), flags=re.MULTILINE)
    return json.loads(clean.strip())


def validate_patch(patch: Dict, node_ids: set) -> List[str]:
    warnings: List[str] = []
    valid_cats = {"WAR", "ALLY", "POLICY", "SPILLOVER", "TENSION", "INTERNAL"}
    valid_theaters = {"ME", "UKR", "ASIA", "AFR", "AMER"}
    valid_types = {"state", "territory", "org", "nonstate"}

    for n in (patch.get("nodes_add") or []):
        if not n.get("id"):
            warnings.append("nodes_add item missing id")
        if n.get("category") not in valid_cats:
            warnings.append(f"nodes_add {n.get('id')}: invalid category '{n.get('category')}'")
        if n.get("type") not in valid_types:
            warnings.append(f"nodes_add {n.get('id')}: invalid type '{n.get('type')}'")
        for t in (n.get("theaters") or []):
            if t not in valid_theaters:
                warnings.append(f"nodes_add {n.get('id')}: invalid theater '{t}'")

    for n in (patch.get("nodes_update") or []):
        if n.get("id") not in node_ids:
            warnings.append(f"nodes_update: '{n.get('id')}' not in existing nodes")

    all_ids = node_ids | {n.get("id") for n in (patch.get("nodes_add") or [])}
    for e in (patch.get("edges_add") or []):
        if e.get("from") not in all_ids:
            warnings.append(f"edges_add {e.get('id')}: from='{e.get('from')}' unknown")
        if e.get("to") not in all_ids:
            warnings.append(f"edges_add {e.get('id')}: to='{e.get('to')}' unknown")
        if e.get("category") not in valid_cats:
            warnings.append(f"edges_add {e.get('id')}: invalid category")

    return warnings


# ── Step 5: Apply patch ───────────────────────────────────────────────────────

def apply_patch(map_data: Dict, patch: Dict) -> Dict:
    result = copy.deepcopy(map_data)
    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])

    remove_nids = {r["id"] for r in (patch.get("nodes_remove") or [])}
    remove_eids = {r["id"] for r in (patch.get("edges_remove") or [])}
    nodes[:] = [n for n in nodes if n["id"] not in remove_nids]
    edges[:] = [e for e in edges if e["id"] not in remove_eids]

    nidx = {n["id"]: i for i, n in enumerate(nodes)}
    eidx = {e["id"]: i for i, e in enumerate(edges)}

    for upd in (patch.get("nodes_update") or []):
        idx = nidx.get(upd["id"])
        if idx is not None:
            nodes[idx] = {**nodes[idx], **upd}

    for upd in (patch.get("edges_update") or []):
        idx = eidx.get(upd["id"])
        if idx is not None:
            edges[idx] = {**edges[idx], **upd}

    existing_nids = {n["id"] for n in nodes}
    for n in (patch.get("nodes_add") or []):
        if n["id"] not in existing_nids:
            nodes.append(n)

    existing_eids = {e["id"] for e in edges}
    for e in (patch.get("edges_add") or []):
        if e["id"] not in existing_eids:
            edges.append(e)

    return result


# ── Step 6: Write PR summary ──────────────────────────────────────────────────

def build_summary(patch: Dict, warnings: List[str], clusters: Dict) -> str:
    lines = [
        "# Proposed map update",
        "",
        f"**Generated:** {_utc_now_iso()}",
        f"**Trigger:** {sum(len(v) for v in clusters.values())} events "
        f"across {len(clusters)} nodes in the last {LOOKBACK_HOURS}h",
        "",
        "## Change summary",
        "",
        patch.get("change_summary", "No summary provided."),
        "",
        "## Patch contents",
        "",
    ]

    for label, key in [
        ("Nodes added", "nodes_add"),
        ("Nodes updated", "nodes_update"),
        ("Nodes removed", "nodes_remove"),
        ("Edges added", "edges_add"),
        ("Edges updated", "edges_update"),
        ("Edges removed", "edges_remove"),
    ]:
        items = patch.get(key) or []
        if items:
            lines.append(f"**{label}** ({len(items)})")
            for item in items:
                lines.append(f"- `{item.get('id', '?')}`")
            lines.append("")

    if warnings:
        lines += ["## ⚠️ Validation warnings", "", "Review before merging:", ""]
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines += [
        "## How to merge",
        "",
        "1. Review the diff in `data/map_data_proposed.json`",
        "2. Copy it over `data/map_data.json` if you're satisfied",
        "3. Bump `last_updated` and `ui_date_label` in `data/meta.json`",
        "4. Delete `data/map_data_proposed.json`, `data/map_patch_latest.json`, "
        "and `data/map_patch_summary.md`",
        "5. Merge — deploy triggers automatically",
        "",
        "> Auto-generated. All IHL labels and editorial assessments "
        "require human verification before merging.",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return 1

    events_data = _load_json(EVENTS_PATH, {"events": []})
    map_data = _load_json(MAP_DATA_PATH, {"nodes": [], "edges": []})

    if not events_data.get("events"):
        print("No events found. Skipping.")
        return 0

    all_clusters = cluster_events(events_data, LOOKBACK_HOURS)
    sig = significant_clusters(all_clusters, MIN_CLUSTER_SIZE)

    if not sig:
        print(f"No clusters with {MIN_CLUSTER_SIZE}+ events in the last {LOOKBACK_HOURS}h.")
        return 0

    print(f"Significant clusters ({len(sig)}): {list(sig.keys())}")

    user_msg = build_user_message(sig, map_data)
    print(f"Calling Anthropic API ({ANTHROPIC_MODEL})...")
    raw = call_anthropic(SYSTEM_PROMPT, user_msg, ANTHROPIC_API_KEY)

    patch = parse_patch(raw)
    node_ids = {n["id"] for n in (map_data.get("nodes") or [])}
    warnings = validate_patch(patch, node_ids)

    if warnings:
        print("Validation warnings:")
        for w in warnings:
            print(f"  ⚠ {w}")

    has_changes = any(
        patch.get(k) for k in
        ["nodes_add", "nodes_update", "nodes_remove",
         "edges_add", "edges_update", "edges_remove"]
    )

    if not has_changes:
        print(f"No changes proposed: {patch.get('change_summary', '')}")
        return 0

    proposed = apply_patch(map_data, patch)
    summary_md = build_summary(patch, warnings, sig)

    if DRY_RUN:
        print("=== DRY RUN patch ===")
        print(json.dumps(patch, indent=2, ensure_ascii=False))
        return 0

    PATCH_PATH.write_text(
        json.dumps(patch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    PROPOSED_PATH.write_text(
        json.dumps(proposed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    SUMMARY_PATH.write_text(summary_md, encoding="utf-8")

    print(f"Wrote: {PROPOSED_PATH.name}, {PATCH_PATH.name}, {SUMMARY_PATH.name}")
    print(f"Summary: {patch.get('change_summary', '')}")

    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write("has_changes=true\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
