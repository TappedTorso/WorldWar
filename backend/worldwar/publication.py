"""Explicit public retirement overlay, separate from private editorial history."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import model_validator
from sqlalchemy import select

from .evidence import linked_sources, validate_source_snapshots
from .models import EvidenceLink, Record, Revision
from .schemas import ID, KINDS, StrictModel, utc_now, validate_record
from .service import ServiceError, append_revision, identity, key, publication_checks, public_join, public_payload, retire, revision


class PublicationAction(StrictModel):
    kind: str
    id: ID
    action: Literal['retract', 'merge']
    target_id: ID | None = None
    published_at: datetime | None = None
    record: dict[str, Any] | None = None

    @model_validator(mode='after')
    def valid_action(self):
        if self.kind not in KINDS:
            raise ValueError('unknown publication action kind')
        if self.action == 'merge' and (not self.target_id or self.target_id == self.id):
            raise ValueError('merge requires a distinct target_id')
        if self.action == 'retract' and self.target_id is not None:
            raise ValueError('retract cannot carry target_id')
        if self.record is not None:
            raw_record = dict(self.record)
            snapshots = raw_record.pop('source_snapshots', [])
            self.record = validate_record(self.kind, raw_record)
            captured = validate_source_snapshots(self.record.get('source_ids', []), snapshots)
            if captured:
                self.record['source_snapshots'] = list(captured.values())
            desired = 'merged' if self.action == 'merge' else 'retracted'
            if self.record['id'] != self.id or self.record['publication_status'] != desired:
                raise ValueError('publication action and tombstone record identity/status disagree')
            if self.action == 'merge' and self.record.get('merged_into') != self.target_id:
                raise ValueError('publication action and tombstone merge target disagree')
            if self.record.get('legacy_payload') is not None:
                raise ValueError('public publication overlay cannot contain raw legacy_payload')
            self.record.pop('legacy_payload', None)
        return self


def validate_actions(data):
    rows = data.get('publication_actions', [])
    if not isinstance(rows, list):
        raise ServiceError(422, 'publication_actions must be an array')
    actions = [PublicationAction.model_validate(row).model_dump(mode='json') for row in rows]
    keys = [(a['kind'], a['id']) for a in actions]
    if len(keys) != len(set(keys)):
        raise ServiceError(422, 'duplicate publication actions for one identity')
    # A previously merged alias can point to an identity retired later. Preserve
    # that public history by applying aliases before their targets; reject cycles.
    by_key = {(a['kind'], a['id']): a for a in actions}
    incoming = {k: 0 for k in by_key}
    edges = {}
    for k, action in by_key.items():
        target = (action['kind'], action['target_id'])
        if action['action'] == 'merge' and target in by_key:
            edges[k] = target
            incoming[target] += 1
    ordered = []
    while incoming:
        ready = sorted((k for k, degree in incoming.items() if degree == 0), key=lambda k: (k[0] == 'sources', *k))
        if not ready:
            raise ServiceError(422, 'publication merge actions contain a redirect cycle')
        k = ready[0]
        ordered.append(by_key[k])
        del incoming[k]
        if k in edges:
            incoming[edges[k]] -= 1
    return ordered


def tombstones(session, *, export=False):
    statement = select(Record.kind, Revision.id, Revision.payload).select_from(Record).join(Revision, public_join()).where(
        Revision.payload['publication_status'].as_string().in_(['retracted', 'merged'])).order_by(Record.kind, Record.stable_id)
    rows = list(session.execute(statement))
    sources = linked_sources(session, [rid for _, rid, p in rows if p.get('source_ids')])
    return [{'kind': kind, 'record': dict(public_payload(payload, export), **({'source_snapshots': sources[rid]} if rid in sources else {}))} for kind, rid, payload in rows]


def export_actions(session):
    statement = select(Record, Revision).join(Revision, public_join()).where(
        Revision.payload['publication_status'].as_string().in_(['retracted', 'merged'])).order_by(Record.kind, Record.stable_id)
    actions = []
    rows = list(session.execute(statement))
    sources = linked_sources(session, [r.id for _, r in rows if r.payload.get('source_ids')])
    for record, row in rows:
        status = row.payload['publication_status']
        # An applied overlay records the genuine exported publication date in
        # updated_at. Unknown authored dates stay null, never become build time.
        date = row.payload.get('publication_changed_at')
        if 'publication_changed_at' not in row.payload:
            date = row.payload.get('updated_at')
            if row.action != 'publication_overlay' and date is None:
                date = row.created_at
        action = dict(kind=record.kind, id=record.stable_id,
                      action='merge' if status == 'merged' else 'retract', published_at=date, record=dict(public_payload(row.payload), **({'source_snapshots': sources[row.id]} if row.id in sources else {})))
        if status == 'merged':
            action['target_id'] = row.payload['merged_into']
        actions.append(action)
    return actions


def apply_actions(session, data):
    if data.get('schema_version') != '1.0':
        raise ServiceError(422, 'publication overlay schema_version must be 1.0')
    actions = validate_actions(data)
    applied, skipped = 0, 0
    planned = {key(a['kind'], a['id']) for a in actions}
    source_records = {a['id']: a['record'] for a in actions if a['kind'] == 'sources' and a.get('record')}
    # Retired editor-created identities may not exist in the legacy/active seed
    # or discovery archive. Precreate only their identities, never active facts.
    for action in actions:
        if session.get(Record, key(action['kind'], action['id'])) is None:
            if action.get('record') is None:
                raise ServiceError(422, 'missing baseline identity requires an exported public tombstone record')
            session.add(Record(key=key(action['kind'], action['id']), kind=action['kind'], stable_id=action['id'],
                               current_revision=0, public_revision=None, editorial_status='draft', created_at=utc_now()))
    session.flush()
    new_rows = []
    for action in actions:
        record = identity(session, action['kind'], action['id'])
        current_public = revision(session, record, record.public_revision) if record.public_revision else None
        desired = 'merged' if action['action'] == 'merge' else 'retracted'
        if current_public and current_public.payload.get('publication_status') in ('merged', 'retracted'):
            if current_public.payload['publication_status'] != desired or (desired == 'merged' and current_public.payload.get('merged_into') != action['target_id']):
                raise ServiceError(409, 'existing tombstone conflicts with publication overlay')
            skipped += 1
            continue
        captured_sources = {}
        if action.get('record') is None:
            retire(session, action['kind'], action['id'], record.current_revision,
                   'Apply explicit public publication overlay', action.get('target_id'),
                   overlay_published_at=action['published_at'], publication_overlay=True)
        else:
            payload = dict(action['record'])
            captured_sources = validate_source_snapshots(payload.get('source_ids', []), payload.pop('source_snapshots', []))
            if current_public and current_public.payload.get('legacy_payload') is not None:
                payload['legacy_payload'] = current_public.payload['legacy_payload']
            as_published = dict(payload, publication_status='published')
            publication_checks(session, action['kind'], as_published,
                               legacy_import=True, official_import=payload.get('review_method') == 'validated_official_adapter',
                               publication_batch=planned, historical_import=True, historical_sources=source_records, evidence_snapshots=captured_sources)
            if action['action'] == 'merge':
                target = identity(session, action['kind'], action['target_id'])
                if target.public_revision is None and target.key not in planned:
                    raise ServiceError(422, 'merge target has no public identity')
            if action['kind'] == 'sources':
                # Historical pins remain valid, but an active claim cannot lose
                # its catalog source unless that claim is retired in this packet.
                statement = select(Record.key).join(Revision, public_join()).join(EvidenceLink, EvidenceLink.revision_id == Revision.id).where(
                    EvidenceLink.source_key == record.key, Revision.payload['publication_status'].as_string() == 'published')
                if any(k not in planned for k in session.scalars(statement)):
                    raise ServiceError(422, 'source is used by active public records; retire/correct those links first')
            changed_at = action['published_at'] or payload.get('publication_changed_at') or payload.get('updated_at')
            payload['publication_changed_at'] = changed_at
            if 'updated_at' in payload:
                payload['updated_at'] = changed_at
            append_revision(session, record, payload, action='publication_overlay',
                            reason='Apply explicit public publication overlay', expected_revision=record.current_revision,
                            public=True, preserve_updated_at=True, source_snapshots=captured_sources)
        new_rows.append((record.key, record.public_revision, captured_sources))
        applied += 1
    # Source tombstones can have been imported after their historical claims.
    # Finish normalized evidence pins only after every planned identity exists.
    for record_key, number, captured_sources in new_rows:
        record = session.get(Record, record_key)
        row = revision(session, record, number)
        for source_id in row.payload.get('source_ids', []):
            source = session.get(Record, key('sources', source_id))
            if source and source.public_revision and session.get(EvidenceLink, (row.id, source.key)) is None:
                session.add(EvidenceLink(revision_id=row.id, source_key=source.key, source_revision=source.public_revision, source_snapshot=captured_sources.get(source_id) or revision(session, source, source.public_revision).payload))
    session.flush()
    return {'applied': applied, 'skipped': skipped}
