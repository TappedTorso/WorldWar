"""FastAPI public research reads and token-protected editorial commands."""
from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from .database import SCHEMA_VERSION, make_engine, migrate, sessions
from .models import Record
from .schemas import CreateCommand, DOMAINS, KINDS, MergeCommand, TransitionCommand, UpdateCommand
from .service import (ServiceError, correct_draft, create_draft, csv_export, editor_records,
                      get_detail, public_records, publish, retire, snapshot)

METHODOLOGY = {
    'schema_version': '1.0',
    'publication': 'A linked source and recorded editorial review are required before factual publication. Discovery articles remain labeled unreviewed reporting and never count as occurrences. Legacy conflict assertions retain inherited/unverified status and original provenance.',
    'coverage': 'Coverage entries describe a bounded reviewed scope, partial samples, unavailable sources, or areas not assessed. An omitted event or country is not evidence of absence.',
    'scorecards': 'Observed counts of distinct reviewed, count-eligible occurrences, documented active dates, named locations and linked campaigns. Calendar month-to-date is compared with the same elapsed days of the previous month only when both entire country windows have explicitly reviewed coverage. There is no composite score or inference from article volume.',
    'dates': 'Occurrence, source publication, discovery, retrieval, source update and editorial review dates are separate. Unknown timestamps stay null; calendar-day and unresolved raw dates retain their precision.',
    'elections': 'Official source identity does not establish certification. Unofficial tallies, provider calls, certified results, recounts and disputes retain distinct states. Missing reports remain null. Boundaries and district vintage remain explicit; unknown geometry is not fabricated.',
    'rights': 'Exports contain original structured summaries and source metadata/links, not source full text, images, credentials or private drafts. Publisher reuse restrictions remain attached to source metadata.',
    'corrections': 'Published records point to immutable public revisions. Corrections stay private until published. Merged and retracted identities retain public tombstones and public revision history; private revision reasons are never exported.'
}


def create_app(database_url=None, editor_token=None, *, initialize=True):
    engine = make_engine(database_url)
    factory = sessions(engine)
    configured_token = editor_token if editor_token is not None else os.environ.get('WORLDWAR_EDITOR_TOKEN', '')

    @asynccontextmanager
    async def lifespan(app):
        if initialize:
            migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(title='WorldWar Research API', version='1.0.0', lifespan=lifespan)
    app.state.engine, app.state.session_factory = engine, factory
    origins = [o.strip() for o in os.environ.get('WORLDWAR_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=['GET', 'POST', 'PUT', 'OPTIONS'], allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def headers(request: Request, call_next):
        # Body limits also belong at the reverse proxy in a service deployment.
        if request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > 2_000_000:
            return JSONResponse({'detail': 'request body is too large'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store' if '/editor/' in request.url.path else 'no-cache'
        return response

    def session_dependency():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def editor(authorization: str | None = Header(default=None)):
        if not configured_token:
            raise ServiceError(503, 'editor access is disabled; configure WORLDWAR_EDITOR_TOKEN on the API')
        scheme, _, candidate = (authorization or '').partition(' ')
        if scheme.lower() != 'bearer' or not secrets.compare_digest(candidate.encode(), configured_token.encode()):
            raise ServiceError(401, 'valid editor bearer token required')

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status,
                            headers={'WWW-Authenticate': 'Bearer'} if exc.status == 401 else None)

    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse({'detail': 'duplicate identity or concurrent revision conflict'}, status_code=409)

    @app.get('/api/v1/health')
    def health(session=Depends(session_dependency)):
        session.execute(text('SELECT 1'))
        return {'status': 'ok', 'schema': SCHEMA_VERSION, 'schema_version': '1.0', 'editor_enabled': bool(configured_token)}

    @app.get('/api/v1/snapshot')
    def get_snapshot(session=Depends(session_dependency)):
        return snapshot(session)

    @app.get('/api/v1/methodology')
    def methodology():
        return METHODOLOGY

    @app.get('/api/v1/search')
    def search(q: str = Query(default='', max_length=300), domain: Literal['conflicts', 'protests', 'elections'] | None = None,
               session=Depends(session_dependency)):
        needle = q.casefold().strip()
        items = []
        for kind in KINDS:
            if kind in ('sources', 'coverage'):
                continue
            for record in public_records(session, kind, q=needle, include_evidence=False):
                record_domain = record.get('domain') or DOMAINS.get(kind)
                if domain and record_domain != domain:
                    continue
                if needle and needle not in (record.get('title', '') + ' ' + record.get('summary', '')).casefold():
                    continue
                items.append(dict(id=record['id'], domain=record_domain, kind=kind, title=record['title'],
                                  summary=record.get('summary', ''), route=f'#/{record_domain}/{kind}/{record["id"]}'))
        return {'items': items}

    @app.get('/api/v1/records/{kind}/{stable_id}')
    def detail(kind: str, stable_id: str, session=Depends(session_dependency)):
        return get_detail(session, kind, stable_id)

    @app.get('/api/v1/export')
    def export(format: Literal['json', 'csv'] = 'json', kind: str | None = None,
               session=Depends(session_dependency)):
        data = snapshot(session, export=True)
        if kind is not None and kind not in data.keys() - {'meta', 'schema_version'}:
            raise ServiceError(422, 'unknown export kind')
        if format == 'json':
            return JSONResponse(data[kind] if kind else data,
                                headers={'Content-Disposition': f'attachment; filename="worldwar-{kind or "research"}.json"'})
        if not kind:
            raise ServiceError(422, 'CSV export requires a kind')
        return Response(csv_export(data[kind]), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="worldwar-{kind}.csv"'})

    @app.get('/api/v1/editor/records', dependencies=[Depends(editor)])
    def list_editor(status: Literal['draft', 'published', 'retracted', 'merged', 'all'] = 'draft', session=Depends(session_dependency)):
        return editor_records(session, status)

    @app.get('/api/v1/editor/records/{kind}/{stable_id}', dependencies=[Depends(editor)])
    def private_detail(kind: str, stable_id: str, session=Depends(session_dependency)):
        return get_detail(session, kind, stable_id, private=True)

    @app.post('/api/v1/editor/records/{kind}', dependencies=[Depends(editor)], status_code=201)
    def create(kind: str, command: CreateCommand, session=Depends(session_dependency)):
        if kind not in KINDS:
            raise ServiceError(404, 'unknown editable kind')
        return create_draft(session, kind, command.record, command.reason)

    @app.put('/api/v1/editor/records/{kind}/{stable_id}', dependencies=[Depends(editor)])
    def correct(kind: str, stable_id: str, command: UpdateCommand, session=Depends(session_dependency)):
        return correct_draft(session, kind, stable_id, command.record, command.expected_revision, command.reason)

    @app.post('/api/v1/editor/records/{kind}/{stable_id}/publish', dependencies=[Depends(editor)])
    def publish_record(kind: str, stable_id: str, command: TransitionCommand, session=Depends(session_dependency)):
        return publish(session, kind, stable_id, command.expected_revision, command.reason)

    @app.post('/api/v1/editor/records/{kind}/{stable_id}/retract', dependencies=[Depends(editor)])
    def retract_record(kind: str, stable_id: str, command: TransitionCommand, session=Depends(session_dependency)):
        return retire(session, kind, stable_id, command.expected_revision, command.reason)

    @app.post('/api/v1/editor/records/{kind}/{stable_id}/merge', dependencies=[Depends(editor)])
    def merge_record(kind: str, stable_id: str, command: MergeCommand, session=Depends(session_dependency)):
        return retire(session, kind, stable_id, command.expected_revision, command.reason, command.target_id)

    return app


app = create_app()
