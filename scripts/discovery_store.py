"""Lossless-enough metadata archive. Discovery is never occurrence evidence by itself.

Article identity is a canonical URL, not a headline or tracking parameter. Preserve
first/last provider sightings and the original legacy fields for research recovery.
No page body is fetched or republished here.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {'fbclid', 'gclid', 'dclid', 'mc_cid', 'mc_eid'}


def canonical_url(value: str) -> str:
    try:
        u = urlsplit(value.strip())
        if u.scheme.lower() not in ('http', 'https') or not u.hostname or u.username or u.password:
            return ''
        query = [(k,v) for k,v in parse_qsl(u.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in TRACKING]
        # Paths/query values can be case-sensitive; never lowercase them.
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path or '/', urlencode(sorted(query)), ''))
    except ValueError:
        return ''


def normalize_timestamp(value):
    if not value:
        return None
    raw = str(value).strip()
    for pattern in ('%Y%m%dT%H%M%SZ', '%Y%m%d%H%M%S'):
        try:
            return dt.datetime.strptime(raw, pattern).replace(tzinfo=dt.timezone.utc).isoformat().replace('+00:00', 'Z')
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None or re.fullmatch(r'\d{4}-\d\d-\d\d', raw):
            return None  # Do not assign an unstated time zone or midnight.
        return parsed.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError):
        return None


def normalize_article(article, *, provider='GDELT_DOC_API', retrieved_at=None, revision=None):
    url = canonical_url(article.get('url', ''))
    title = str(article.get('headline') or article.get('title') or '').strip()
    if not url or not title:
        return None
    legacy = 'discovered_at' not in article and 'date_basis' not in article
    provider_seen = article.get('provider_seen_raw') or article.get('seendate')
    if legacy and provider.startswith('GDELT'):
        provider_seen = provider_seen or article.get('published_at')
    discovered = normalize_timestamp(article.get('discovered_at') or provider_seen)
    published = None if (legacy and provider.startswith('GDELT')) else normalize_timestamp(article.get('published_at'))
    result = {
        'id': article.get('id') or 'article_' + hashlib.sha256(url.encode()).hexdigest()[:20],
        'headline': title, 'url': url, 'source': str(article.get('source') or article.get('domain') or urlsplit(url).hostname),
        'published_at': published, 'discovered_at': discovered,
        'first_seen_at': article.get('first_seen_at') or discovered or retrieved_at,
        'last_seen_at': article.get('last_seen_at') or discovered or retrieved_at,
        'retrieved_at': retrieved_at, 'provider': provider,
        'provider_seen_raw': provider_seen, 'date_basis': 'publisher' if published else 'provider_seen' if discovered else 'unknown',
        'record_kind': 'discovery_article', 'evidence_status': 'unreviewed',
        'tags': sorted(set(article.get('tags') or [])),
    }
    if legacy and article.get('published_at'):
        result['legacy_published_at'] = article['published_at']
    if revision:
        result['first_repository_revision'] = revision
    return result


def merge_articles(previous, incoming):
    by_url = {canonical_url(a['url']): dict(a) for a in previous if canonical_url(a.get('url',''))}
    for item in incoming:
        if item is None:
            continue
        url = canonical_url(item.get('url', ''))
        if not url:
            continue
        old = by_url.get(url)
        if old:
            merged = {**old, **item, 'id': old['id']}
            for key in ('first_seen_at','first_repository_revision','legacy_published_at'):
                if old.get(key): merged[key] = old[key]
            dates = [v for v in (old.get('first_seen_at'), item.get('first_seen_at')) if v]
            merged['first_seen_at'] = min(dates) if dates else None
            dates = [v for v in (old.get('last_seen_at'), item.get('last_seen_at')) if v]
            merged['last_seen_at'] = max(dates) if dates else None
            merged['tags'] = sorted(set(old.get('tags',[])) | set(item.get('tags',[])))
            if old.get('published_at') and not item.get('published_at'):
                merged['published_at'] = old['published_at']
                merged['date_basis'] = 'publisher'
            by_url[url] = merged
        else:
            by_url[url] = dict(item)
    return sorted(by_url.values(), key=lambda a: (a.get('first_seen_at') or '', a['id']))


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def archive_articles(root: Path, articles, run):
    path = root / 'archive.json'
    previous = json.loads(path.read_text())['events'] if path.exists() else []
    merged = merge_articles(previous, articles)
    atomic_json(path, {'metadata': {'schema_version':'1.0', 'kind':'discovery_archive',
        'note':'Article discovery metadata, not verified real-world occurrences.',
        'article_count':len(merged)}, 'events':merged})
    runs_path = root / 'runs.json'
    runs = json.loads(runs_path.read_text()) if runs_path.exists() else []
    runs = [r for r in runs if r['id'] != run['id']] + [run]
    atomic_json(runs_path, runs)
    return len(merged)
