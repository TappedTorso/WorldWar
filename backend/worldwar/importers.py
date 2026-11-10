"""Idempotent, lossless legacy migration and deliberately reviewed seed loading."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import date

from sqlalchemy import select

from .evidence import validate_source_snapshots
from .models import ImportBatch, Record
from .schemas import KINDS, utc_now, valid_url, validate_record
from .service import ServiceError, correct_draft, create_draft, identity, key, publish, revision


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def legacy_import(session, data):
    batch_id = digest(data)
    if session.get(ImportBatch, batch_id):
        return {'actors': 0, 'relationships': 0, 'already_imported': True}
    nodes, edges = data.get('nodes'), data.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ServiceError(422, 'legacy input requires nodes and edges arrays')
    for name, records in [('nodes', nodes), ('edges', edges)]:
        ids = [r['id'] for r in records]
        if len(set(ids)) != len(ids):
            raise ServiceError(422, f'duplicate legacy {name} IDs')
    node_ids = {n['id'] for n in nodes}
    if any(e.get('from') not in node_ids or e.get('to') not in node_ids for e in edges):
        raise ServiceError(422, 'legacy relationships contain unknown actors')
    country_codes = json.loads((Path(__file__).parent / 'legacy_country_codes.json').read_text())['codes']
    actor_names = {n['id']: n['name'] for n in nodes}
    counts = {'actors': 0, 'relationships': 0}
    for kind, records in [('actors', nodes), ('relationships', edges)]:
        for original in records:
            if session.get(Record, key(kind, original['id'])):
                raise ServiceError(409, 'legacy identity already exists with a different import batch; never overwrite editorial work')
            source_ids, citations = [], []
            for source in original.get('sources', []):
                source = source if isinstance(source, dict) else {'citation': str(source)}
                citation = source.get('citation') or source.get('title') or json.dumps(source, ensure_ascii=False)
                citations.append(citation)
                source_id = 'legacy-source-' + digest(source)[:24]
                if not session.get(Record, key('sources', source_id)):
                    raw_url = source.get('url')
                    try:
                        url = valid_url(raw_url) if raw_url else None
                    except ValueError:
                        url = None  # Original malformed citation remains losslessly in legacy_payload.
                    source_record = dict(id=source_id, title=source.get('title') or citation,
                                         publisher=source.get('publisher') or 'Inherited reference; publisher unverified',
                                         url=url, source_type='legacy_reference', published_at=None,
                                         retrieved_at=None, retrieval_date=None, publication_precision='unknown',
                                         retrieval_precision='unknown', rights='Inherited citation only; reuse rights unverified',
                                         note='Imported original citation; not current verification.')
                    if isinstance(source.get('published_at'), str):
                        try:
                            source_record['published_date'] = date.fromisoformat(source['published_at']).isoformat()
                            source_record['publication_precision'] = 'day'
                        except ValueError:
                            pass
                    draft = create_draft(session, 'sources', source_record, 'Lossless legacy citation migration')
                    publish(session, 'sources', source_id, draft['revision'], 'Publish inherited citation metadata')
                source_ids.append(source_id)
            payload = dict(id=original['id'], title=original.get('name') or original.get('type') or original['id'],
                           summary=original.get('summary', ''), source_ids=list(dict.fromkeys(source_ids)),
                           evidence_status='legacy_unverified', reviewed_at=None,
                           legacy_citation_text=citations, legacy_confidence=original.get('confidence'),
                           legacy_updated_at=original.get('updated_at'), legacy_payload=original, updated_at=original.get('updated_at'))
            if kind == 'actors':
                coords = original.get('coords')
                if not isinstance(coords, list) or len(coords) != 2:
                    raise ServiceError(422, f'legacy actor {original["id"]} lacks valid coordinates')
                payload.update(name=original['name'], actor_type=original.get('type', 'unknown'), country_code=country_codes.get(original['id']) if original.get('type') in ('state', 'territory') else None,
                               longitude=coords[0], latitude=coords[1], theaters=original.get('theaters', []), category=original.get('category', 'unknown'))
            else:
                payload['title'] = f"{actor_names[original['from']]} → {actor_names[original['to']]} · {original.get('type', 'Relationship')}"
                payload.update(from_actor_id=original['from'], to_actor_id=original['to'],
                               relationship_type=original.get('type', 'unknown'), category=original.get('category', 'unknown'),
                               theaters=[original['theater']] if original.get('theater') else [])
            draft = create_draft(session, kind, payload, 'Lossless legacy import; inherited and unverified', preserve_updated_at=True, allow_legacy_payload=True)
            publish(session, kind, original['id'], draft['revision'], 'Publish inherited legacy record without recertifying evidence', legacy_import=True, preserve_updated_at=True)
            counts[kind] += 1
    metadata = data.get('metadata', {})
    session.add(ImportBatch(id=batch_id, imported_at=utc_now(), kind='legacy', counts=counts, metadata_payload=metadata))
    return counts


def seed_import(session, data):
    """Load an owner-reviewed publication packet. Never replace an existing ID.

    Publication is transactional: a failed record rolls back the whole packet.
    Existing identical records are skipped; corrections use the editor API.
    """
    if data.get('schema_version') != '1.0':
        raise ServiceError(422, 'seed schema_version must be 1.0')
    allowed = set(KINDS) | {'meta', 'schema_version', 'jobs', 'scorecards', 'publication_actions'}
    if set(data) - allowed:
        raise ServiceError(422, 'seed contains unknown top-level fields')
    from .publication import validate_actions
    validate_actions(data)  # Shape only: baseline archive targets may not exist yet.
    batch_id = digest(data)
    if session.get(ImportBatch, batch_id):
        return {'created': 0, 'skipped': 0, 'already_imported': True}
    prepared, skipped = [], 0
    evidence = {}
    for kind in KINDS:
        rows = data.get(kind, [])
        if not isinstance(rows, list):
            raise ServiceError(422, f'{kind} must be an array')
        seen = set()
        for row in rows:
            raw = dict(row)
            captured = raw.pop('source_snapshots', [])
            p = validate_record(kind, raw)
            evidence[key(kind, p['id'])] = validate_source_snapshots(p.get('source_ids', []), captured)
            if p['id'] in seen:
                raise ServiceError(422, f'duplicate {kind} seed ID')
            seen.add(p['id'])
            if p.get('publication_status') != 'published':
                raise ServiceError(422, 'publication seeds contain active records only')
            if p.get('evidence_status') == 'legacy_unverified':
                raise ServiceError(422, 'use the legacy importer to preserve inherited assertions')
            existing = session.get(Record, key(kind, p['id']))
            if existing:
                old = revision(session, existing, existing.public_revision).payload if existing.public_revision else {}
                if old:
                    old = validate_record(kind, old)  # Normalize new optional defaults without rewriting immutable history.
                if old.get('legacy_payload') is not None:
                    if p.get('legacy_payload') not in (None, old['legacy_payload']):
                        raise ServiceError(422, 'seed cannot replace original legacy provenance')
                    p['legacy_payload'] = old['legacy_payload']
                strip = lambda x: {k: v for k, v in x.items() if k not in ('revision', 'updated_at')}
                if strip(old) != strip(p):
                    if existing.editorial_status == 'published' and ((old.get('evidence_status') == 'legacy_unverified' and p.get('evidence_status') == 'reviewed') or (kind == 'sources' and old.get('source_type') == 'legacy_reference')):
                        prepared.append((kind, p))
                        continue
                    raise ServiceError(409, f'seed identity differs from existing publication: {kind}/{p["id"]}; use editorial correction')
                skipped += 1
                continue
            prepared.append((kind, p))
    # Create all identities first; publish acyclic source/domain dependencies.
    for kind, p in prepared:
        existing = session.get(Record, key(kind, p['id']))
        if existing:
            correct_draft(session, kind, p['id'], p, existing.current_revision, 'Owner-reviewed correction of inherited legacy record', preserve_updated_at=True)
        else:
            create_draft(session, kind, p, 'Owner-reviewed seed packet', preserve_updated_at=True)
    publication_batch = {key(kind, p['id']) for kind, p in prepared}
    # A reviewed packet may contain reciprocal occurrence/campaign links. All
    # identities and typed payloads are validated first; the single transaction
    # guarantees no reader sees a partially published graph.
    for kind, p in sorted(prepared, key=lambda item: item[0] != 'sources'):
        record = identity(session, kind, p['id'])
        publish(session, kind, p['id'], record.current_revision,
                'Publish owner-reviewed seed packet', publication_batch=publication_batch, preserve_updated_at=True, source_snapshots=evidence.get(key(kind, p['id'])))
    session.add(ImportBatch(id=batch_id, imported_at=utc_now(), kind='seed', counts={'created': len(prepared), 'skipped': skipped}, metadata_payload=data.get('meta', {})))
    return {'created': len(prepared), 'skipped': skipped}
