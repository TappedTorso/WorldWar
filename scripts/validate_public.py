#!/usr/bin/env python3
"""Deployment gates: no private runtime files, unsafe source URLs or dangling evidence."""
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'web/dist'
DATA=ROOT/'web/public/data/research.json'
data=json.loads(DATA.read_text())
sources={s['id']:s for s in data['sources']}
tombstones=data.get('tombstones',[])
historical_sources={t['record']['id']:t['record'] for t in tombstones if t['kind']=='sources'}
errors=[]
for kind in ['actors','relationships','developments','occurrences','campaigns','connections','contests','election_actions','political_context','sources','coverage']:
    seen=set()
    for r in data.get(kind,[]):
        if r['id'] in seen:errors.append(f'duplicate {kind}/{r["id"]}')
        seen.add(r['id'])
        if r.get('publication_status')!='published':errors.append(f'non-active status in normal array {kind}/{r["id"]}')
        for source in r.get('source_ids',[]):
            if source not in sources:errors.append(f'missing source {source}')
        if 'private_notes' in r or 'editor_token' in r:errors.append('private field in snapshot')
        if kind=='contests' and r.get('status')=='not_assessed' and (r.get('total_votes') is not None or r.get('winner') is not None):errors.append('unassessed contest contains result')
for tombstone in tombstones:
    record=tombstone['record']
    if record.get('publication_status') not in ('retracted','merged'):errors.append('invalid public tombstone status')
    if 'private_notes' in record or 'editor_token' in record or 'private_reason' in record:errors.append('private field in tombstone')
    for source in record.get('source_ids',[]):
        if source not in sources and source not in historical_sources:errors.append(f'missing historical source {source}')
all_sources=list({**historical_sources,**sources}.values())
for kind, rows in data.items():
    if isinstance(rows,list):
        for row in rows:
            record=row.get('record',row)
            pins=record.get('source_snapshots',[])
            if len({s['id'] for s in pins})!=len(pins):errors.append('duplicate source evidence pins')
            if any(s['id'] not in record.get('source_ids',[]) for s in pins):errors.append('source pin is not linked to its claim')
            all_sources.extend(pins)
for source in all_sources:
    if source.get('url'):
        url=urlsplit(source['url'])
        if url.scheme not in ('https','http') or not url.netloc or url.username:errors.append(f'unsafe source {source["id"]}')
def identities(kind):
    return {r['id'] for r in data[kind]} | {t['record']['id'] for t in tombstones if t['kind']==kind}
legacy=json.loads((ROOT/'data/map_data.json').read_text())
if {r['id'] for r in legacy['nodes']} - identities('actors'):errors.append('legacy actor identities lost')
if {r['id'] for r in legacy['edges']} - identities('relationships'):errors.append('legacy relationship identities lost')
if len(identities('contests'))<470:errors.append('national registry identities incomplete')
if DIST.exists():
    for file in DIST.rglob('*'):
        if file.is_file() and (file.name.lower() == 'editor-key.txt' or file.suffix.lower() in {'.db','.sqlite','.sqlite3','.py','.env'} or file.name.lower().startswith('.env') or file.name.lower().endswith(('.db-wal','.db-shm','.sqlite-wal','.sqlite-shm','.sqlite3-wal','.sqlite3-shm'))):
            errors.append(f'private/backend artifact in build: {file.name}')
    if not (DIST/'index.html').exists():errors.append('build lacks entry point')
    if not (DIST/'data/research.json').exists() or (DIST/'data/research.json').read_bytes()!=DATA.read_bytes():errors.append('built publication does not match validated snapshot')
else:errors.append('production build is missing')
if errors:raise SystemExit('\n'.join(errors))
print('Public release gates passed: IDs, source references, result semantics, legacy counts and deliberate build files.')
