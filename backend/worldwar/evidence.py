"""Public source metadata at the actual claiming revision, never private notes."""
from sqlalchemy import select
from sqlalchemy.orm import aliased

from .models import EvidenceLink, Revision
from .schemas import Source


def validate_source_snapshots(source_ids, snapshots):
    if not isinstance(snapshots, list):
        raise ValueError('source_snapshots must be an array')
    result = {}
    for raw in snapshots:
        source = Source.model_validate(raw).model_dump(mode='json')
        if source['id'] not in source_ids or source['id'] in result:
            raise ValueError('source snapshot must identify one unique linked source')
        result[source['id']] = source
    return result


def linked_sources(session, revision_ids, *, private=False):
    if not revision_ids:
        return {}
    source_revision = aliased(Revision)
    result = {}
    statement = select(EvidenceLink.revision_id, EvidenceLink.source_snapshot,
                       source_revision.payload, source_revision.public_visible).join(
        source_revision, (source_revision.record_key == EvidenceLink.source_key) &
        (source_revision.number == EvidenceLink.source_revision)).where(
            EvidenceLink.revision_id.in_(revision_ids)).order_by(EvidenceLink.revision_id, EvidenceLink.source_key)
    for claiming_id, captured, payload, visible in session.execute(statement):
        if private or visible:
            result.setdefault(claiming_id, []).append(dict(captured or payload))
    return result
