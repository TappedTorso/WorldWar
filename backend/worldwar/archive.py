"""Bulk restoration of owner-preserved article metadata, in durable chunks.

This is an import of already collected discovery metadata, not a network refresh
or factual publication. Validation and two-step revision semantics match the
incremental inbox; executemany avoids thousands of ORM roundtrips on rebuilds.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime

from pydantic import ValidationError
from sqlalchemy import Date, DateTime, insert, select

from .models import CandidateIngestion, EvidenceLink, Job, PROJECTIONS, Record, RecordReference, Revision
from .schemas import utc_now, validate_record
from .service import key


def typed_projection(kind, revision_id, payload):
    values = {'revision_id': revision_id}
    for c in PROJECTIONS[kind].c:
        if c.name == 'revision_id':
            continue
        value = payload.get(c.name)
        if value is not None and isinstance(c.type, DateTime):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        elif value is not None and isinstance(c.type, Date):
            value = date.fromisoformat(value)
        values[c.name] = value
    return values


def ingest_archive(factory, data, *, adapter, publish_unreviewed):
    from .discovery import canonical_url, publication_date
    from .importers import digest
    rows = data['events']
    now = utc_now()
    job_id = 'archive-' + digest(data)[:32]
    with factory.begin() as session:
        existing_job = session.get(Job, job_id)
        if not existing_job:
            session.add(Job(id=job_id, adapter=adapter, domain='conflicts', started_at=now, completed_at=None,
                            status='partial', fetched_count=len(rows), accepted_count=0, error=None,
                            public_visible=False, note='Internal preserved-archive import; not a collection refresh'))
        urls = set(session.scalars(select(CandidateIngestion.canonical_url)))
        record_keys = set(session.scalars(select(Record.key)))
        existing_sources = {r.key: (r.public_revision, r.current_revision) for r in session.scalars(select(Record).where(Record.kind == 'sources'))}
        actors = set(session.scalars(select(Record.stable_id).where(Record.kind == 'actors', Record.public_revision.is_not(None))))
    accepted, rejected = 0, 0
    # Archive rebuilds must be byte-stable; the import clock is private audit data.
    for chunk_start in range(0, len(rows), 500):
        prepared = []
        for article in rows[chunk_start:chunk_start + 500]:
            try:
                if not isinstance(article, dict):
                    raise ValueError('candidate must be an object')
                url = canonical_url(article.get('url', ''))
                if url in urls:
                    continue
                title = article.get('headline') or article.get('title')
                if not isinstance(title, str) or not title.strip():
                    raise ValueError('missing article title')
                raw_seen = article.get('discovered_at') or article.get('first_seen_at')
                seen, _, _ = publication_date(raw_seen)
                if raw_seen and seen is None:
                    raise ValueError('discovery timestamp must retain exact precision')
                retrieved, _, _ = publication_date(article.get('retrieved_at'))
                first_seen, _, _ = publication_date(article.get('first_seen_at') or seen)
                last_seen, _, _ = publication_date(article.get('last_seen_at') or seen)
                published, published_day, precision = publication_date(article.get('published_at'))
                if first_seen and last_seen and first_seen > last_seen:
                    raise ValueError('invalid discovery interval')
                hash_id = hashlib.sha256(url.encode()).hexdigest()
                stable_id = article.get('id')
                from .schemas import ID
                from pydantic import TypeAdapter
                try:
                    TypeAdapter(ID).validate_python(stable_id)
                except ValidationError:
                    stable_id = 'discovery-' + hash_id[:24]
                if key('developments', stable_id) in record_keys:
                    stable_id = 'discovery-' + hash_id[:32]
                source_id = 'discovery-source-' + hash_id[:24]
                source_key = key('sources', source_id)
                if publish_unreviewed and source_key in existing_sources and existing_sources[source_key][0] is None:
                    raise ValueError('existing source is private; archive cannot publish it')
                source = validate_record('sources', dict(id=source_id, title=title, url=url,
                    publisher=article.get('source') or article.get('domain') or url.split('/')[2], source_type='discovery',
                    published_at=published, published_date=published_day, publication_precision=precision,
                    retrieved_at=retrieved, retrieval_precision='timestamp' if retrieved else 'unknown',
                    rights='Article metadata and link only; linked publisher rights apply.',
                    note='Preserved discovery metadata; provider-seen time is not source publication or event time.'))
                development = validate_record('developments', dict(id=stable_id, title=title,
                    summary='Unreviewed discovery article. Follow the original reporting; no event or relationship is established by inclusion.',
                    source_ids=[source_id], evidence_status='unreviewed', actor_ids=list(dict.fromkeys(t for t in article.get('tags', []) if t in actors)),
                    occurred_start=None, occurred_end=None, date_precision='unknown', development_type='discovery_article',
                    url=url, discovered_at=seen, published_at=published, provider_seen_raw=article.get('provider_seen_raw'),
                    updated_at=retrieved or seen))
                candidate = dict(id=hash_id, adapter=adapter, external_id=str(article.get('id') or stable_id), canonical_url=url,
                    content_sha256=digest({k: article.get(k) for k in ('headline', 'title', 'url', 'published_at')}),
                    first_seen_at=first_seen or now, last_seen_at=last_seen or now, source_published_at=published,
                    provenance={k: article[k] for k in ('provider', 'provider_seen_raw', 'date_basis', 'legacy_published_at',
                        'first_repository_revision', 'last_repository_revision', 'retrieved_at') if k in article},
                    record_key=key('developments', stable_id), job_id=job_id)
                prepared.append((source, development, candidate))
                urls.add(url)
                record_keys.update((key('sources', source_id), key('developments', stable_id)))
            except (ValueError, TypeError, KeyError):
                rejected += 1
        if not prepared:
            continue
        with factory.begin() as session:
            identities, revisions, revision_kinds = [], [], []
            last_revision = 2 if publish_unreviewed else 1
            for source, development, candidate in prepared:
                for kind, payload in [('sources', source), ('developments', development)]:
                    record_key = key(kind, payload['id'])
                    if kind == 'sources' and record_key in existing_sources:
                        continue  # Reviewed export/catalog metadata must never be overwritten by archive reconstruction.
                    identities.append(dict(key=record_key, kind=kind, stable_id=payload['id'], current_revision=last_revision,
                        public_revision=last_revision if publish_unreviewed else None,
                        editorial_status='published' if publish_unreviewed else 'draft', created_at=now))
                    for number in range(1, last_revision + 1):
                        p = dict(payload, revision=number)
                        revisions.append(dict(record_key=record_key, number=number, action='create' if number == 1 else 'publish',
                            reason='Preserve article metadata as unreviewed discovery; no event promotion', created_at=now,
                            public_visible=number == 2, payload=p))
                        revision_kinds.append(kind)
            session.execute(insert(Record.__table__), identities)
            ids = list(session.execute(insert(Revision.__table__).returning(Revision.id, sort_by_parameter_order=True), revisions).scalars())
            projections = {'sources': [], 'developments': []}
            evidence, references = [], []
            metadata_by_source = {key('sources', source['id']): source for source, _, _ in prepared}
            for rid, row, kind in zip(ids, revisions, revision_kinds):
                p = row['payload']
                projections[kind].append(typed_projection(kind, rid, p))
                if kind == 'developments':
                    source_key = key('sources', p['source_ids'][0])
                    public_number, current_number = existing_sources.get(source_key, (None, None))
                    source_number = (public_number if row['public_visible'] else current_number) if source_key in existing_sources else row['number']
                    captured = dict(metadata_by_source[source_key], revision=source_number) if source_key in existing_sources else None
                    evidence.append(dict(revision_id=rid, source_key=source_key, source_revision=source_number, source_snapshot=captured))
                    references.extend(dict(revision_id=rid, target_key=key('actors', a), relation='actor_ids') for a in p['actor_ids'])
            for kind, values in projections.items():
                if values:
                    session.execute(insert(PROJECTIONS[kind]), values)
            if evidence:
                session.execute(insert(EvidenceLink.__table__), evidence)
            if references:
                session.execute(insert(RecordReference.__table__), references)
            session.execute(insert(CandidateIngestion.__table__), [c for _, _, c in prepared])
            accepted += len(prepared)
            job = session.get(Job, job_id)
            job.accepted_count += len(prepared)
    with factory.begin() as session:
        job = session.get(Job, job_id)
        job.status = 'partial' if rejected else 'ok'
        job.error = f'{rejected} candidate(s) rejected by validation.' if rejected else None
        job.completed_at = utc_now()
    return dict(id=job_id, status='partial' if rejected else 'ok', fetched_count=len(rows),
                accepted_count=accepted, rejected_count=rejected, error=job.error)
