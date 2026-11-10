"""Publish a narrowly validated official-source observation, never a race call.

The network adapter is separate. This importer accepts structured metadata and
counts, validates them again, and appends immutable dated revisions. The explicit
CLI flag authorizes only this path; it cannot publish other unreviewed claims.
"""
from __future__ import annotations

from .importers import digest
from .models import ImportBatch, Record
from .schemas import utc_now, validate_record
from .service import (ServiceError, correct_draft, create_draft, identity, key,
                      publish, revision)


def import_official_results(session, data):
    if data.get('schema_version') != '1.0' or set(data) - {'schema_version', 'meta', 'sources', 'contests'}:
        raise ServiceError(422, 'official-results packet supports only schema_version, meta, sources and contests')
    if not isinstance(data.get('sources'), list) or not isinstance(data.get('contests'), list) or not data['sources'] or not data['contests']:
        raise ServiceError(422, 'official-results packet requires sources and contests')
    sources = [validate_record('sources', row) for row in data['sources']]
    contests = [validate_record('contests', row) for row in data['contests']]
    if len({s['id'] for s in sources}) != len(sources) or len({c['id'] for c in contests}) != len(contests):
        raise ServiceError(422, 'duplicate official-results packet IDs')
    if any(s['source_type'] != 'official' for s in sources):
        raise ServiceError(422, 'only official sources are eligible for this adapter')
    for p in contests:
        if p['evidence_status'] != 'unreviewed' or p['review_method'] != 'validated_official_adapter' or p['reviewed_at'] is not None:
            raise ServiceError(422, 'adapter observations must remain unreviewed with explicit review_method')
        if p['status'] != 'reported_unofficial' or p['winner'] is not None or p['winner_basis'] is not None:
            raise ServiceError(422, 'adapter cannot certify results or declare winners')
        if p['total_votes'] is None or p['total_votes'] <= 0 or not p['candidates'] or not any((c['votes'] or 0) > 0 for c in p['candidates']):
            raise ServiceError(422, 'adapter must provide a nonplaceholder positive tally')
        if any(c['votes'] is None for c in p['candidates']):
            raise ServiceError(422, 'each adapter candidate needs a validated vote count')
        if p['total_votes'] != sum(c['votes'] for c in p['candidates']):
            raise ServiceError(422, 'official adapter candidate counts must reconcile with contest total')
        if not p['source_ids'] or set(p['source_ids']) - {s['id'] for s in sources}:
            raise ServiceError(422, 'adapter observations must link packet official sources')
    batch_id = digest(data)
    if session.get(ImportBatch, batch_id):
        return {'updated': 0, 'already_imported': True}
    changed = 0
    strip = lambda x: {k: v for k, v in x.items() if k not in ('revision', 'updated_at')}
    for kind, rows in [('sources', sources), ('contests', contests)]:
        for p in rows:
            record = session.get(Record, key(kind, p['id']))
            if record:
                if record.editorial_status != 'published':
                    raise ServiceError(409, 'official refresh cannot overwrite pending editorial work or retired records')
                current = revision(session, record).payload
                if kind == 'contests':
                    for field in ('office', 'cycle', 'state_code', 'jurisdiction', 'district', 'election_stage'):
                        if current[field] != p[field]:
                            raise ServiceError(422, f'official refresh changes contest identity field {field}')
                    if current['status'] in ('certified', 'provider_called', 'recount', 'contested'):
                        raise ServiceError(409, 'official refresh cannot replace a reviewed finality/dispute state')
                    # Keep an editorially verified geographic identity; an adapter
                    # cannot invalidate or silently assert a new boundary plan.
                    for field in ('geography_version', 'boundary_status', 'longitude', 'latitude'):
                        p[field] = current[field]
                if strip(current) == strip(p):
                    continue
                draft = correct_draft(session, kind, p['id'], p, record.current_revision,
                                      'Validated official-source refresh; not editorial review or certification', preserve_updated_at=True)
            else:
                draft = create_draft(session, kind, p, 'Validated official-source observation', preserve_updated_at=True)
            publish(session, kind, p['id'], draft['revision'],
                    'Publish unofficial official-source observation; no winner inferred', official_import=True, preserve_updated_at=True)
            changed += 1
    session.add(ImportBatch(id=batch_id, imported_at=utc_now(), kind='official_results',
                           counts={'updated': changed}, metadata_payload=data.get('meta', {})))
    return {'updated': changed}
