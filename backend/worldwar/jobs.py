"""Import durable collection-run health without provider bodies or secrets."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field

from .models import Job
from .schemas import Domain, ID, StrictModel
from .service import ServiceError


class JobInput(StrictModel):
    id: ID
    adapter: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.:-]+$')
    domain: Domain
    started_at: datetime
    completed_at: datetime | None = None
    status: Literal['ok', 'partial', 'error']
    fetched_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    error: str | None = None
    note: str | None = None


def sanitize_error(value):
    if value is None:
        return None
    def safe_url(match):
        try:
            p = urlsplit(match.group())
            return urlunsplit((p.scheme, p.hostname or '', p.path, '', ''))
        except ValueError:
            return '[redacted URL]'
    value = re.sub(r'https?://[^\s]+', safe_url, value)
    value = re.sub(r'(?i)bearer\s+[^\s,;]+', 'Bearer [redacted]', value)
    value = re.sub(r'(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+', r'\1=[redacted]', value)
    return ''.join(c for c in value if c in '\n\t' or ord(c) >= 32)[:1000]


def import_jobs(session, rows):
    if not isinstance(rows, list):
        raise ServiceError(422, 'job import requires an array')
    created, skipped = 0, 0
    seen = set()
    for row in rows:
        p = JobInput.model_validate(row).model_dump(mode='json')
        if p['id'] in seen:
            raise ServiceError(422, 'duplicate collection-job IDs')
        seen.add(p['id'])
        if p['completed_at'] and p['completed_at'] < p['started_at']:
            raise ServiceError(422, 'job completion precedes start')
        p['error'], p['note'] = sanitize_error(p['error']), sanitize_error(p['note'])
        existing = session.get(Job, p['id'])
        if existing:
            if any(getattr(existing, f) != v for f, v in p.items()):
                raise ServiceError(409, 'immutable collection run already exists with different metadata')
            skipped += 1
        else:
            session.add(Job(**p, public_visible=True))
            created += 1
    return {'created': created, 'skipped': skipped}
