"""Durable discovery inbox. Article ingestion is never factual event publication."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select

from .importers import digest
from .models import CandidateIngestion, Job, Record
from .schemas import utc_now, valid_url
from .service import ServiceError, create_draft, key, publish


def canonical_url(value):
    valid_url(value)
    parsed = urlsplit(value)
    # Fragments and known campaign trackers do not create new article identities.
    query = sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid'))
    result = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or '/', urlencode(query), ''))
    if len(result) > 3000:
        raise ValueError('article URL exceeds supported length')
    return result


def publication_date(raw):
    if raw is None or raw == '':
        return None, None, 'unknown'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        from datetime import date
        return None, date.fromisoformat(raw).isoformat(), 'day'
    value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('source publication timestamp requires timezone')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'), None, 'timestamp'


def ingest_discovery(factory, data, *, adapter='gdelt', publish_unreviewed=False):
    """Commit job health even when parsing fails; accepted items stay durable.

    Input supports {events:[...], metadata:{...}} and GDELT's {articles:[...]}.
    No network requests or source full text are performed/stored here.
    """
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', adapter):
        raise ValueError('invalid adapter name')
    if isinstance(data, dict) and isinstance(data.get('metadata'), dict) and data['metadata'].get('kind') == 'discovery_archive' and isinstance(data.get('events'), list):
        from .archive import ingest_archive
        return ingest_archive(factory, data, adapter=adapter, publish_unreviewed=publish_unreviewed)
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', adapter):
        raise ValueError('invalid adapter name')
    job_id = 'job-' + uuid.uuid4().hex
    with factory.begin() as session:
        session.add(Job(id=job_id, adapter=adapter, domain='conflicts', started_at=utc_now(),
                        completed_at=None, status='partial', fetched_count=0, accepted_count=0,
                        error='Refresh is in progress; a missing completion indicates interruption.'))
    errors, accepted, fetched = 0, 0, 0
    try:
        rows = data.get('events', data.get('articles'))
        if not isinstance(rows, list):
            raise ValueError('discovery input requires an events or articles array')
        fetched = len(rows)
        metadata = data.get('metadata', {})
        old_gdelt = metadata.get('provider') == 'GDELT_DOC_API' and not metadata.get('date_semantics_corrected')
        session = factory()
        if session.bind.dialect.name == 'sqlite':
            session.connection().exec_driver_sql('BEGIN')
        for index, article in enumerate(rows):
            try:
                with session.begin_nested():
                    if not isinstance(article, dict):
                        raise ValueError('candidate must be an object')
                    url = canonical_url(article.get('url', ''))
                    existing = session.scalar(select(CandidateIngestion).where(CandidateIngestion.canonical_url == url))
                    seen = article.get('discovered_at') or metadata.get('generated_at_utc') or utc_now()
                    # Retrieval means our actual read time, not an event/publication date.
                    retrieved_at = article.get('retrieved_at') or utc_now()
                    retrieved_at, _, _ = publication_date(retrieved_at)
                    if retrieved_at is None:
                        raise ValueError('retrieved_at requires timestamp precision when supplied')
                    seen_value, _, _ = publication_date(seen)
                    if seen_value is None:
                        raise ValueError('discovered_at requires an exact timestamp or null')
                    provider_raw = article.get('provider_seen_raw') or article.get('seendate')
                    published_raw = article.get('published_at')
                    if old_gdelt:
                        provider_raw = provider_raw or published_raw
                        published_raw = None
                    published_at, published_day, precision = publication_date(published_raw)
                    content_hash = digest({k: article.get(k) for k in ('headline', 'title', 'url', 'published_at')})
                    last_seen_value, _, _ = publication_date(article.get('last_seen_at') or seen_value)
                    if last_seen_value is None:
                        raise ValueError('last_seen_at requires timestamp precision')
                    if existing:
                        existing.last_seen_at = max(existing.last_seen_at, last_seen_value)
                        existing.content_sha256 = content_hash
                        existing.job_id = job_id
                        # Deliberately keep editorial/public records immutable. A changed
                        # title is candidate metadata, never an automatic correction.
                        continue
                    stable_id = article.get('id')
                    if not isinstance(stable_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', stable_id):
                        stable_id = 'discovery-' + hashlib.sha256(url.encode()).hexdigest()[:24]
                    if session.get(Record, key('developments', stable_id)):
                        stable_id += '-' + hashlib.sha256(url.encode()).hexdigest()[:12]
                    source_id = 'discovery-source-' + hashlib.sha256(url.encode()).hexdigest()[:24]
                    title = article.get('headline') or article.get('title')
                    if not isinstance(title, str) or not title.strip():
                        raise ValueError('discovery title is required')
                    if not session.get(Record, key('sources', source_id)):
                        s = dict(id=source_id, title=title, url=url, publisher=article.get('source') or article.get('domain') or urlsplit(url).hostname,
                                 source_type='discovery', published_at=published_at, published_date=published_day,
                                 publication_precision=precision, retrieved_at=retrieved_at, retrieval_precision='timestamp',
                                 rights='Article metadata and link only; linked publisher rights apply.',
                                 note='Discovery article metadata is not independent verification or a real-world occurrence.')
                        src = create_draft(session, 'sources', s, 'Ingest source metadata into discovery inbox')
                        if publish_unreviewed:
                            publish(session, 'sources', source_id, src['revision'], 'Publish discovery link metadata only')
                    # Heuristic tags are preserved only as candidate hints when they
                    # match existing actors. They do not create relationships.
                    actor_ids = [t for t in article.get('tags', []) if isinstance(t, str) and session.get(Record, key('actors', t))]
                    p = dict(id=stable_id, title=title, summary='Unreviewed discovery article. Follow the original reporting; no event or relationship is established by inclusion.',
                             source_ids=[source_id], evidence_status='unreviewed', actor_ids=actor_ids,
                             occurred_start=None, occurred_end=None, date_precision='unknown',
                             development_type='discovery_article', url=url, discovered_at=seen_value,
                             published_at=published_at, provider_seen_raw=provider_raw)
                    draft = create_draft(session, 'developments', p, 'Persist unreviewed discovery candidate')
                    if publish_unreviewed:
                        publish(session, 'developments', stable_id, draft['revision'], 'Publish labeled discovery article; no factual event promotion')
                    session.add(CandidateIngestion(id=hashlib.sha256(url.encode()).hexdigest(), adapter=adapter,
                                external_id=str(article.get('id') or stable_id), canonical_url=url, content_sha256=content_hash,
                                first_seen_at=article.get('first_seen_at') or seen_value, last_seen_at=last_seen_value, source_published_at=published_at,
                                provenance={k: article[k] for k in ('provider', 'provider_seen_raw', 'date_basis', 'legacy_published_at', 'first_repository_revision', 'last_repository_revision', 'retrieved_at') if k in article},
                                record_key=key('developments', stable_id), job_id=job_id))
                    accepted += 1
            except (ValueError, TypeError, KeyError, ServiceError):
                errors += 1
            finally:
                if (index + 1) % 200 == 0:
                    session.commit()
                    if session.bind.dialect.name == 'sqlite':
                        session.connection().exec_driver_sql('BEGIN')
        session.commit()
        session.close()
        provider_status = metadata.get('status', 'ok')
        status = 'error' if errors and not accepted and fetched else 'partial' if errors or provider_status in ('partial', 'error') else 'ok'
        error = f'{errors} candidate(s) rejected by validation.' if errors else ('Provider reported an incomplete refresh; previous candidates are retained.' if provider_status in ('partial', 'error') else None)
    except (ValueError, TypeError, KeyError):
        status, error = 'error', 'Discovery adapter input was invalid; previous candidates are retained.'
    except Exception:
        if 'session' in locals():
            session.rollback()
            session.close()
        # Do not expose provider bodies, URLs with secrets, credentials or stack traces.
        with factory.begin() as session:
            job = session.get(Job, job_id)
            job.status, job.error, job.completed_at = 'error', 'Discovery refresh failed; inspect private service logs.', utc_now()
            job.fetched_count, job.accepted_count = fetched, accepted
        raise
    with factory.begin() as session:
        job = session.get(Job, job_id)
        job.status, job.error, job.completed_at = status, error, utc_now()
        job.fetched_count, job.accepted_count = fetched, accepted
    return {'id': job_id, 'status': status, 'fetched_count': fetched, 'accepted_count': accepted, 'rejected_count': errors, 'error': error}
