"""Transactional editorial commands and one shared public projection."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, DateTime, func, insert, or_, select, update
from sqlalchemy.orm import Session

from .evidence import linked_sources
from .models import EvidenceLink, ImportBatch, Job, PROJECTIONS, Record, RecordReference, Revision
from .schemas import DOMAINS, KINDS, utc_now, validate_record


class ServiceError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


def key(kind, stable_id):
    return f'{kind}:{stable_id}'


def identity(session, kind, stable_id):
    if kind not in KINDS:
        raise ServiceError(404, 'unknown record kind')
    record = session.get(Record, key(kind, stable_id))
    if record is None:
        raise ServiceError(404, 'record not found')
    return record


def revision(session, record, number=None):
    number = number if number is not None else record.current_revision
    return session.scalar(select(Revision).where(Revision.record_key == record.key, Revision.number == number))


def public_payload(payload, export=False):
    result = dict(payload)
    if not export or result.get('legacy_payload') is None:
        result.pop('legacy_payload', None)
    return result


def public_join():
    return (Revision.record_key == Record.key) & (Revision.number == Record.public_revision)


def discovery_query():
    table = PROJECTIONS['developments']
    return select(Record.key).select_from(Record).join(Revision, public_join()).join(
        table, table.c.revision_id == Revision.id).where(Record.kind == 'developments',
        table.c.development_type == 'discovery_article', Revision.payload['publication_status'].as_string() == 'published')


def public_records(session, kind, *, export=False, discovery_limit=None, source_ids=None, q=None, include_evidence=True):
    statement = select(Revision.id, Revision.payload).select_from(Record).join(Revision, public_join()).where(Record.kind == kind, Revision.payload['publication_status'].as_string() == 'published')
    if kind == 'developments' and discovery_limit is not None:
        table = PROJECTIONS[kind]
        recent = discovery_query().order_by(table.c.discovered_at.desc(), Record.stable_id.desc()).limit(discovery_limit)
        statement = statement.join(table, table.c.revision_id == Revision.id).where(
            or_(table.c.development_type != 'discovery_article', Record.key.in_(recent)))
    if kind == 'sources' and source_ids is not None:
        table = PROJECTIONS[kind]
        statement = statement.join(table, table.c.revision_id == Revision.id).where(
            or_(table.c.source_type != 'discovery', Record.stable_id.in_(source_ids)))
    if q:
        # SQLAlchemy compiles JSON string access for both SQLite and PostgreSQL.
        statement = statement.where(or_(Revision.payload['title'].as_string().icontains(q, autoescape=True),
                                        Revision.payload['summary'].as_string().icontains(q, autoescape=True)))
    statement = statement.order_by(Record.stable_id)
    rows = list(session.execute(statement))
    sources = linked_sources(session, [rid for rid, p in rows if p.get('source_ids')]) if include_evidence else {}
    return [dict(public_payload(p, export), **({'source_snapshots': sources[rid]} if rid in sources else {}))
            for rid, p in rows if p.get('publication_status', 'published') == 'published']


def references_for(kind, payload):
    refs = []
    if kind == 'relationships':
        refs.extend(('actors', payload[f], f) for f in ('from_actor_id', 'to_actor_id'))
    elif kind == 'developments':
        refs.extend(('actors', i, 'actor_ids') for i in payload['actor_ids'])
    elif kind == 'occurrences':
        refs.extend(('campaigns', i, 'campaign_ids') for i in payload['campaign_ids'])
    elif kind == 'campaigns':
        refs.extend(('occurrences', i, 'occurrence_ids') for i in payload['occurrence_ids'])
    elif kind == 'election_actions':
        refs.extend(('contests', i, 'related_contest_ids') for i in payload['related_contest_ids'])
    elif kind in ('connections', 'political_context'):
        ids = [payload['from_id'], payload['to_id']] if kind == 'connections' else payload['related_ids']
        refs.extend((None, i, 'documented_connection' if kind == 'connections' else 'related_ids') for i in ids)
    refs.extend(('connections', i, 'causal_connections') for i in payload.get('causal_connections', []))
    return refs


def resolve_reference(session, kind, stable_id, published=True):
    rows = list(session.scalars(select(Record).where(Record.stable_id == stable_id,
                                                  *([Record.kind == kind] if kind else []))))
    if len(rows) != 1:
        raise ServiceError(422, f'unknown or ambiguous referenced record: {stable_id}')
    record = rows[0]
    rev = revision(session, record, record.public_revision) if record.public_revision else None
    if published and (rev is None or rev.payload.get('publication_status') != 'published'):
        raise ServiceError(422, f'reference is not published: {stable_id}')
    return record


def publication_checks(session, kind, payload, *, legacy_import=False, publication_batch=None, official_import=False, historical_import=False, historical_sources=None, evidence_snapshots=None):
    if payload.get('publication_status', 'published') != 'published':
        raise ServiceError(422, 'use explicit retract or merge commands for tombstones')
    if kind == 'sources':
        return
    source_ids = payload.get('source_ids', [])
    legacy = legacy_import and kind in ('actors', 'relationships') and payload.get('evidence_status') == 'legacy_unverified' and payload.get('legacy_payload') is not None
    discovery = kind == 'developments' and payload.get('development_type') == 'discovery_article'
    official = official_import and kind == 'contests' and payload.get('review_method') == 'validated_official_adapter'
    if official:
        if payload.get('evidence_status') != 'unreviewed' or payload.get('reviewed_at') is not None or payload['status'] != 'reported_unofficial' or payload.get('winner') is not None or payload.get('winner_basis') is not None:
            raise ServiceError(422, 'official adapter can publish only unreviewed unofficial tallies without a winner')
    if kind == 'coverage':
        if payload['status'] == 'reviewed' and (not payload.get('reviewed_at') or not source_ids):
            raise ServiceError(422, 'reviewed coverage requires sources and review timestamp')
    elif not legacy:
        if not source_ids:
            raise ServiceError(422, 'publication requires linked eligible sources')
        if not discovery and not official and (payload.get('evidence_status') != 'reviewed' or not payload.get('reviewed_at')):
            raise ServiceError(422, 'publication requires editorial review and reviewed_at')
        if discovery and payload.get('evidence_status') != 'unreviewed':
            raise ServiceError(422, 'discovery articles remain unreviewed')
    for source_id in source_ids:
        source = resolve_reference(session, 'sources', source_id, published=not historical_import)
        p = (evidence_snapshots or {}).get(source_id) or ((historical_sources or {}).get(source_id) if historical_import else None)
        if p is not None and not historical_import and p.get('publication_status', 'published') != 'published':
            raise ServiceError(422, 'active claims require an originally published source snapshot')
        if p is None and source.public_revision:
            p = revision(session, source, source.public_revision).payload
        if p is None:
            raise ServiceError(422, 'historical source has no public metadata')
        if official and p['source_type'] != 'official':
            raise ServiceError(422, 'official adapter requires official sources only')
        if not legacy and (p['source_type'] == 'legacy_reference' or (not discovery and p['source_type'] == 'discovery')):
            raise ServiceError(422, 'legacy references and discovery feeds cannot establish reviewed claims')
    for ref_kind, stable_id, _ in references_for(kind, payload):
        target = resolve_reference(session, ref_kind, stable_id, published=False)
        if target.key not in (publication_batch or set()) and not (historical_import and target.public_revision):
            resolve_reference(session, ref_kind, stable_id)
    if kind == 'occurrences':
        if any(e['source_id'] not in source_ids for e in payload.get('crowd_estimates', [])):
            raise ServiceError(422, 'crowd estimates must cite one of the linked sources')
    if kind == 'occurrences' and any(payload.get(f) for f in ('participants', 'response', 'outcome')) and not payload.get('attribution'):
        raise ServiceError(422, 'participants, response and outcome require attribution')


def projection(session, kind, revision_row, payload, *, source_versions=None, source_snapshots=None):
    table = PROJECTIONS[kind]
    values = {'revision_id': revision_row.id}
    for c in table.c:
        if c.name == 'revision_id':
            continue
        value = payload.get(c.name)
        if value is not None and isinstance(c.type, DateTime):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        elif value is not None and isinstance(c.type, Date):
            value = date.fromisoformat(value)
        values[c.name] = value
    session.execute(insert(table).values(**values))
    for source_id in payload.get('source_ids', []):
        source = session.get(Record, key('sources', source_id))
        if source:
            source_rev = (source_versions or {}).get(source.key) or (source.public_revision if revision_row.public_visible else source.current_revision)
            if source_rev:
                captured = (source_snapshots or {}).get(source_id) or revision(session, source, source_rev).payload
                session.add(EvidenceLink(revision_id=revision_row.id, source_key=source.key, source_revision=source_rev, source_snapshot=captured))
    for ref_kind, stable_id, relation in references_for(kind, payload):
        candidates = list(session.scalars(select(Record).where(Record.stable_id == stable_id,
                                        *([Record.kind == ref_kind] if ref_kind else []))))
        if len(candidates) == 1:
            session.add(RecordReference(revision_id=revision_row.id, target_key=candidates[0].key, relation=relation))


def append_revision(session, record, payload, *, action, reason, expected_revision, public=False, preserve_updated_at=False, source_versions=None, source_snapshots=None):
    new_number = expected_revision + 1
    result = session.execute(update(Record).where(Record.key == record.key,
                                                  Record.current_revision == expected_revision).values(
        current_revision=new_number,
        editorial_status=payload.get('publication_status', 'published') if public else 'draft',
        **({'public_revision': new_number} if public else {})))
    if result.rowcount != 1:
        raise ServiceError(409, 'stale revision; reload the record before changing it')
    payload = dict(payload, revision=new_number)
    # Preserve genuine source/review timestamps; updated_at describes our revision.
    if 'updated_at' in payload and not preserve_updated_at:
        payload['updated_at'] = utc_now()
    row = Revision(record_key=record.key, number=new_number, action=action, reason=reason,
                   created_at=utc_now(), public_visible=public, payload=payload)
    session.add(row)
    session.flush()
    projection(session, record.kind, row, payload, source_versions=source_versions, source_snapshots=source_snapshots)
    session.refresh(record)
    return payload


def create_draft(session, kind, payload, reason, *, preserve_updated_at=False, allow_legacy_payload=False):
    validated = validate_record(kind, payload)
    if validated.get('legacy_payload') is not None and not allow_legacy_payload:
        raise ServiceError(422, 'legacy_payload is reserved for the lossless legacy importer')
    if session.get(Record, key(kind, validated['id'])):
        raise ServiceError(409, 'ID already exists; correct or merge the existing record')
    record = Record(key=key(kind, validated['id']), kind=kind, stable_id=validated['id'],
                    current_revision=0, created_at=utc_now(), editorial_status='draft')
    session.add(record)
    session.flush()
    return append_revision(session, record, validated, action='create', reason=reason, expected_revision=0, preserve_updated_at=preserve_updated_at)


def correct_draft(session, kind, stable_id, payload, expected, reason, *, preserve_updated_at=False):
    record = identity(session, kind, stable_id)
    if record.current_revision != expected:
        raise ServiceError(409, 'stale revision; reload the record before changing it')
    if payload.get('id') != stable_id:
        raise ServiceError(422, 'stable IDs cannot change; use merge')
    if record.editorial_status in ('merged', 'retracted'):
        raise ServiceError(422, 'create an explicit correction record for a retired identity')
    validated = validate_record(kind, payload)
    inherited = revision(session, record).payload.get('legacy_payload')
    if inherited is None and validated.get('legacy_payload') is not None:
        raise ServiceError(422, 'new legacy provenance cannot be attached through editorial correction')
    if inherited is not None:
        if validated.get('legacy_payload') not in (None, inherited):
            raise ServiceError(422, 'original legacy provenance is immutable')
        validated['legacy_payload'] = inherited
    if validated.get('publication_status') != 'published':
        raise ServiceError(422, 'use the retract/merge transition')
    return append_revision(session, record, validated, action='correct', reason=reason, expected_revision=expected, preserve_updated_at=preserve_updated_at)


def publish(session, kind, stable_id, expected, reason, *, legacy_import=False, publication_batch=None, official_import=False, preserve_updated_at=False, source_snapshots=None):
    record = identity(session, kind, stable_id)
    if record.current_revision != expected:
        raise ServiceError(409, 'stale revision; reload the record before changing it')
    if record.editorial_status in ('merged', 'retracted'):
        raise ServiceError(422, 'retired identities cannot be republished')
    payload = validate_record(kind, revision(session, record).payload)
    publication_checks(session, kind, payload, legacy_import=legacy_import, publication_batch=publication_batch, official_import=official_import, evidence_snapshots=source_snapshots)
    return append_revision(session, record, payload, action='publish', reason=reason, expected_revision=expected, public=True, preserve_updated_at=preserve_updated_at, source_snapshots=source_snapshots)


def retire(session, kind, stable_id, expected, reason, target_id=None, *, publication_overlay=False, overlay_published_at=None):
    record = identity(session, kind, stable_id)
    if record.current_revision != expected:
        raise ServiceError(409, 'stale revision; reload the record before changing it')
    if record.public_revision is None or record.editorial_status in ('merged', 'retracted'):
        raise ServiceError(422, 'only active published records can be retired')
    if target_id:
        if target_id == stable_id:
            raise ServiceError(422, 'cannot merge a record into itself')
        target = resolve_reference(session, kind, target_id)
        if target.kind != kind:
            raise ServiceError(422, 'merge target must have the same kind')
    if kind == 'sources':
        # Do not strand an active public claim without its published evidence.
        for other in session.scalars(select(Record).where(Record.public_revision.is_not(None))):
            p = revision(session, other, other.public_revision).payload
            if p.get('publication_status') == 'published' and stable_id in p.get('source_ids', []):
                raise ServiceError(422, 'source is used by active public records; correct those links first')
    # Always tombstone the public revision, never reveal an unpublished correction.
    original_public = revision(session, record, record.public_revision)
    original_links = list(session.scalars(select(EvidenceLink).where(EvidenceLink.revision_id == original_public.id)))
    original_sources = {p['id']: p for p in linked_sources(session, [original_public.id]).get(original_public.id, [])}
    payload = dict(original_public.payload,
                   publication_status='merged' if target_id else 'retracted')
    if target_id:
        payload['merged_into'] = target_id
    changed_at = overlay_published_at if publication_overlay else utc_now()
    payload['publication_changed_at'] = changed_at
    if 'updated_at' in payload:
        payload['updated_at'] = changed_at
    return append_revision(session, record, payload, action='publication_overlay' if publication_overlay else 'merge' if target_id else 'retract',
                           reason=reason, expected_revision=expected, public=True, preserve_updated_at=True,
                           source_versions={link.source_key: link.source_revision for link in original_links}, source_snapshots=original_sources)


def get_detail(session, kind, stable_id, *, private=False):
    record = identity(session, kind, stable_id)
    number = record.current_revision if private else record.public_revision
    if not number:
        raise ServiceError(404, 'published record not found')
    row = revision(session, record, number)
    payload = row.payload if private else public_payload(row.payload)
    history = list(session.scalars(select(Revision).where(Revision.record_key == record.key,
                   *([] if private else [Revision.public_visible.is_(True)])).order_by(Revision.number.desc())))
    histories = [dict(revision=r.number, action=r.action, created_at=r.created_at,
                      record=r.payload if private else public_payload(r.payload),
                      **({'reason': r.reason} if private else {})) for r in history]
    sources = linked_sources(session, [row.id], private=private).get(row.id, [])
    if not private and sources:
        payload = dict(payload, source_snapshots=sources)
    if not private:
        history_sources = linked_sources(session, [r.id for r in history])
        for item, historic_row in zip(histories, history):
            if historic_row.id in history_sources:
                item['record'] = dict(item['record'], source_snapshots=history_sources[historic_row.id])
    return {'kind': kind, 'record': payload, 'sources': sources, 'revisions': histories,
            **({'editorial_status': record.editorial_status, 'public_revision': record.public_revision} if private else {})}


def editor_records(session, status='draft'):
    statement = select(Record).order_by(Record.kind, Record.stable_id)
    if status != 'all':
        statement = statement.where(Record.editorial_status == status)
    return {'items': [{'kind': r.kind, 'editorial_status': r.editorial_status,
                        'record': revision(session, r).payload} for r in session.scalars(statement)]}


def covered(coverage, country, start, end):
    """Comparable only with one explicitly reviewed whole-country interval."""
    return any(c['domain'] == 'protests' and c.get('country_code') == country
               and c['geography'] in (country, f'country:{country}') and c['status'] == 'reviewed'
               and c['period_start'] <= start.isoformat() and c['period_end'] >= end.isoformat()
               for c in coverage)


def scorecards(occurrences, campaigns, coverage, *, calculated_at):
    cards = []
    countries = sorted({o['country_code'] for o in occurrences} | {c['country_code'] for c in coverage if c['domain'] == 'protests' and c.get('country_code')})
    # Fixed calendar month windows make snapshots reproducible and transparent.
    for country in countries:
        relevant = [c for c in coverage if c['domain'] == 'protests' and c.get('country_code') == country]
        latest = max([c['period_end'] for c in relevant] + [o.get('occurred_end') or o['occurred_start'] for o in occurrences if o['country_code'] == country])
        end = date.fromisoformat(latest)
        start = end.replace(day=1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        def in_period(a, b):
            result = []
            for o in occurrences:
                if o['country_code'] != country or not o.get('count_eligible', True) or o.get('evidence_status') != 'reviewed':
                    continue
                if o['date_precision'] == 'day' and a.isoformat() <= o['occurred_start'] <= b.isoformat():
                    result.append(o)
                elif o['date_precision'] == 'range':
                    documented = o.get('active_dates', [])
                    # A bounded uncertain date can support a period count only
                    # when the entire uncertainty interval falls in that period.
                    within = a.isoformat() <= o['occurred_start'] and (o.get('occurred_end') or o['occurred_start']) <= b.isoformat()
                    if within or any(a.isoformat() <= d <= b.isoformat() for d in documented):
                        result.append(o)
            return result
        current, previous = in_period(start, end), in_period(prev_start, prev_end)
        # Partial current months compare the same number of calendar days.
        prev_end = min(prev_end, prev_start + timedelta(days=(end - start).days))
        previous = in_period(prev_start, prev_end)
        eligible = covered(coverage, country, start, end) and covered(coverage, country, prev_start, prev_end)
        days = set()
        for o in current:
            documented = o.get('active_dates', [])
            if o['date_precision'] == 'day':
                documented = list(documented) + [o['occurred_start']]
            days.update(d for d in documented if start.isoformat() <= d <= end.isoformat())
        momentum = 'insufficient_data'
        if eligible:
            momentum = 'increased' if len(current) > len(previous) else 'decreased' if len(current) < len(previous) else 'unchanged'
        active_campaign_ids = {c['id'] for c in campaigns}
        campaign_ids = {i for o in current for i in o.get('campaign_ids', []) if i in active_campaign_ids}
        campaign_ids.update(c['id'] for c in campaigns if set(c.get('occurrence_ids', [])) & {o['id'] for o in current})
        cards.append(dict(id=f'protests-{country}-{start}-{end}', geography=country, country_code=country,
                          period_start=start.isoformat(), period_end=end.isoformat(), occurrence_count=len(current),
                          active_days=len(days), location_count=len({(o['place_name'], o['location_precision']) for o in current if o['location_precision'] != 'unknown'}),
                          campaign_count=len(campaign_ids), comparison_start=prev_start.isoformat(), comparison_end=prev_end.isoformat(),
                          previous_occurrence_count=len(previous) if eligible else None, momentum=momentum,
                          coverage_status='reviewed' if covered(coverage, country, start, end) else 'partial' if any(c['status'] in ('reviewed', 'partial') for c in relevant) else 'unavailable' if relevant and all(c['status'] == 'unavailable' for c in relevant) else 'not_assessed',
                          method_version='observed-counts-1.0', calculated_at=calculated_at,
                          input_ids=sorted(o['id'] for o in current),
                          note='Distinct reviewed, count-eligible occurrences; exact-day or explicitly documented active dates and named locations. A range alone does not establish daily activity; an uncertain range must fit wholly inside a count window unless active dates are supplied. Calendar month-to-date versus the same elapsed days of the preceding month. Comparison requires explicitly reviewed whole-country coverage of both windows; source volume is not activity.'))
    return cards


def snapshot(session, *, export=False):
    result = {'schema_version': '1.0'}
    for kind in KINDS:
        if kind != 'sources':
            result[kind] = public_records(session, kind, export=export, discovery_limit=None if export else 250)
    from .publication import tombstones
    result['tombstones'] = tombstones(session, export=export)
    discovery_total = session.scalar(select(func.count()).select_from(discovery_query().subquery()))
    used_sources = {i for kind in KINDS if kind != 'sources' for r in result[kind] for i in r.get('source_ids', [])}
    used_sources.update(i for item in result['tombstones'] for i in item['record'].get('source_ids', []))
    result['sources'] = public_records(session, 'sources', export=export, source_ids=None if export else used_sources)
    jobs = list(session.scalars(select(Job).where(Job.public_visible.is_(True)).order_by(Job.started_at.desc(), Job.id).limit(100)))
    result['jobs'] = [{name: getattr(j, name) for name in ('id', 'adapter', 'domain', 'started_at', 'completed_at', 'status', 'fetched_count', 'accepted_count', 'error', 'note')} for j in jobs]
    # Derived publication time: unchanged public data yields byte-identical files.
    public_times = []
    for kind in KINDS:
        for p in result[kind]:
            public_times.extend(p[f] for f in ('updated_at', 'reviewed_at', 'retrieved_at', 'source_updated_at', 'discovered_at') if p.get(f))
    public_times.extend(item['record'].get('publication_changed_at') or item['record']['updated_at'] for item in result['tombstones'] if item['record'].get('publication_changed_at') or item['record'].get('updated_at'))
    public_times.extend(j.completed_at or j.started_at for j in jobs)
    normalize = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat().replace('+00:00', 'Z')
    generated_at = max((normalize(t) for t in public_times), default=None)
    if generated_at is None:
        generated_at = session.scalar(select(func.max(Revision.created_at)).where(Revision.public_visible.is_(True)))
    result['scorecards'] = scorecards(result['occurrences'], result['campaigns'], result['coverage'], calculated_at=generated_at)
    batches = list(session.scalars(select(ImportBatch).where(ImportBatch.kind == 'legacy')))
    legacy_date = batches[0].metadata_payload.get('last_reviewed_at') if batches else None
    result['meta'] = dict(generated_at=generated_at, data_version=hashlib.sha256(json.dumps({**result, 'scorecards': [{k: v for k, v in c.items() if k != 'calculated_at'} for c in result['scorecards']]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16],
                          legacy_reviewed_at=legacy_date, coverage_summary='Reviewed observations with explicit coverage gaps; partial samples are not a census.',
                          publication_mode='reviewed_snapshot', discovery_total=discovery_total, discovery_visible=min(discovery_total, 250) if not export else discovery_total)
    return result


def csv_export(records):
    stream = io.StringIO(newline='')
    fields = sorted({k for r in records for k in r}) or ['id']
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for record in records:
        row = {}
        for name, value in record.items():
            if value is None:
                value = ''
            elif isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                value = str(value)
            # Spreadsheet programs trim whitespace and controls before formulas.
            prefix = value
            while prefix and (prefix[0].isspace() or ord(prefix[0]) < 32 or prefix[0] == '\ufeff'):
                prefix = prefix[1:]
            if prefix.startswith(('=', '+', '-', '@')):
                value = "'" + value
            row[name] = value
        writer.writerow(row)
    return stream.getvalue()
