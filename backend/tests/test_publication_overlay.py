"""Published retirements must survive the documented reviewed-seed rebuild."""
import json
from pathlib import Path

import pytest
from sqlalchemy import select, text

from worldwar.cli import main
from worldwar.database import SCHEMA_VERSION, V2_COLUMNS, make_engine, migrate, sessions
from worldwar.discovery import ingest_discovery
from worldwar.importers import legacy_import, seed_import
from worldwar.models import PROJECTIONS, Record, Revision, SchemaVersion
from worldwar.publication import apply_actions, export_actions, validate_actions
from worldwar.recovery import backup, content_digest, restore
from worldwar.service import ServiceError, get_detail, snapshot
from conftest import AUTH, NOW, create, occurrence_payload, publish, source_payload


def retire_api(client, kind, stable_id, expected, action='retract', target=None):
    command={'expected_revision':expected,'reason':'PRIVATE-EDITORIAL-REASON-MARKER'}
    if target:command['target_id']=target
    response=client.post(f'/api/v1/editor/records/{kind}/{stable_id}/{action}',headers=AUTH,json=command)
    assert response.status_code==200,response.text
    return response.json()


def synthetic_legacy():
    return {'metadata':{'last_reviewed_at':'2026-03-15T00:00:00Z'},'nodes':[
        {'id':stable_id,'name':'Synthetic duplicate '+stable_id,'type':'state','coords':[0,0],
         'category':'TEST','summary':'Synthetic inherited fixture only','sources':[],'updated_at':'2026-03-14T00:00:00Z'}
        for stable_id in ('ALIAS_A','ALIAS_B','TARGET')],'edges':[]}


def export_packet(app,tmp_path):
    path=tmp_path/'public-seed.json'
    assert main(['--database-url',str(app.state.engine.url),'export-seed','--output',str(path)])==0
    packet=json.loads(path.read_text())
    assert 'PRIVATE-EDITORIAL-REASON-MARKER' not in path.read_text()
    assert 'PRIVATE-PENDING-CORRECTION' not in path.read_text()
    assert 'tombstones' not in packet
    return packet


def test_actual_legacy_and_archive_retractions_survive_export_and_fresh_rebuild(app,client,tmp_path):
    legacy=json.loads((Path(__file__).parents[2]/'data/map_data.json').read_text())
    article={'metadata':{'kind':'discovery_archive'},'events':[
        dict(id=identity,headline='Synthetic archive '+identity,url='https://example.org/'+identity,
             discovered_at=NOW,retrieved_at=NOW,published_at=None)
        for identity in ('article-retired','article-kept')]}
    with app.state.session_factory.begin() as session:legacy_import(session,legacy)
    ingest_discovery(app.state.session_factory,article,publish_unreviewed=True)
    original=client.get('/api/v1/editor/records/actors/IRAN',headers=AUTH).json()['record']
    edited=client.put('/api/v1/editor/records/actors/IRAN',headers=AUTH,
                     json={'record':dict(original,summary='PRIVATE-PENDING-CORRECTION'),
                           'expected_revision':original['revision'],'reason':'PRIVATE-EDITORIAL-REASON-MARKER'}).json()
    retired=retire_api(client,'actors','IRAN',edited['revision'])
    retire_api(client,'developments','article-retired',2)
    public=client.get('/api/v1/snapshot').json()
    assert 'PRIVATE-' not in json.dumps(public)
    assert any(t['kind']=='actors' and t['record']['id']=='IRAN' for t in public['tombstones'])
    assert all('legacy_payload' not in t['record'] for t in public['tombstones'])
    assert 'PRIVATE-PENDING-CORRECTION' in client.get('/api/v1/editor/records/actors/IRAN',headers=AUTH).text
    packet=export_packet(app,tmp_path)
    assert {(a['kind'],a['id'],a['action']) for a in packet['publication_actions']}=={
        ('actors','IRAN','retract'),('developments','article-retired','retract')}
    versions=[]
    for index in range(2):
        engine=make_engine('sqlite:///'+str(tmp_path/f'rebuilt-{index}.db'));migrate(engine);factory=sessions(engine)
        with factory.begin() as session:
            legacy_import(session,legacy)
            seed_import(session,packet)  # Validates, deliberately does not apply actions.
        ingest_discovery(factory,article,publish_unreviewed=True)
        with factory() as session:assert any(a['id']=='IRAN' for a in snapshot(session)['actors'])
        with factory.begin() as session:assert apply_actions(session,packet)=={'applied':2,'skipped':0}
        with factory.begin() as session:assert apply_actions(session,packet)=={'applied':0,'skipped':2}
        with factory() as session:
            rebuilt=snapshot(session)
            assert not any(a['id']=='IRAN' for a in rebuilt['actors'])
            assert [a['id'] for a in rebuilt['developments']]==['article-kept']
            assert get_detail(session,'actors','IRAN')['record']['publication_status']=='retracted'
            restored_actions=export_actions(session)
            assert [(a['kind'],a['id'],a['action'],a['published_at']) for a in restored_actions]==[(a['kind'],a['id'],a['action'],a['published_at']) for a in packet['publication_actions']]
            assert all(a['record']['publication_status']=='retracted' for a in restored_actions)
            versions.append(rebuilt['meta']['data_version'])
        engine.dispose()
    assert versions[0]==versions[1]


def test_actual_merge_chain_preserves_targets_and_stable_tombstones(app,client,tmp_path):
    legacy=synthetic_legacy()
    with app.state.session_factory.begin() as session:legacy_import(session,legacy)
    retire_api(client,'actors','ALIAS_A',2,'merge','ALIAS_B')
    retire_api(client,'actors','ALIAS_B',2,'merge','TARGET')
    packet=export_packet(app,tmp_path)
    engine=make_engine('sqlite://');migrate(engine);factory=sessions(engine)
    with factory.begin() as session:
        legacy_import(session,legacy);seed_import(session,packet);apply_actions(session,packet)
        public=snapshot(session)
        assert [a['id'] for a in public['actors']]==['TARGET']
        tombstones={t['record']['id']:t['record'] for t in public['tombstones']}
        assert tombstones['ALIAS_A']['merged_into']=='ALIAS_B'
        assert tombstones['ALIAS_B']['merged_into']=='TARGET'
        assert get_detail(session,'actors','TARGET')['record']['publication_status']=='published'
    with pytest.raises((ServiceError,ValueError)):
        validate_actions({'publication_actions':[dict(kind='actors',id='A',action='merge',target_id='B'),dict(kind='actors',id='B',action='merge',target_id='A')]})


def test_overlay_malformed_conflicting_and_missing_actions_are_atomic(app,client):
    with app.state.session_factory.begin() as session:legacy_import(session,synthetic_legacy())
    for actions in (
        [dict(kind='actors',id='ALIAS_A',action='retract',reason='PRIVATE')],
        [dict(kind='actors',id='ALIAS_A',action='retract'),dict(kind='actors',id='MISSING',action='retract')],
        [dict(kind='actors',id='ALIAS_A',action='retract'),dict(kind='actors',id='ALIAS_A',action='merge',target_id='TARGET')],
    ):
        with pytest.raises((ServiceError,ValueError)):
            with app.state.session_factory.begin() as session:apply_actions(session,{'schema_version':'1.0','publication_actions':actions})
        assert len(client.get('/api/v1/snapshot').json()['actors'])==3
    retire_api(client,'actors','ALIAS_A',2,'merge','TARGET')
    with pytest.raises(ServiceError,match='conflicts'):
        with app.state.session_factory.begin() as session:
            apply_actions(session,{'schema_version':'1.0','publication_actions':[dict(kind='actors',id='ALIAS_A',action='retract')]})


def test_source_retirement_keeps_pinned_historical_evidence(client,source):
    observed=publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    blocked=client.post('/api/v1/editor/records/sources/test-source/retract',headers=AUTH,
                        json={'expected_revision':source['revision'],'reason':'Source still used by active claim'})
    assert blocked.status_code==422
    retire_api(client,'occurrences',observed['id'],observed['revision'])
    retire_api(client,'sources',source['id'],source['revision'])
    detail=client.get('/api/v1/records/occurrences/test-occurrence').json()
    assert detail['sources'][0]['id']=='test-source' and detail['sources'][0]['revision']==source['revision']
    assert detail['sources'][0]['url']=='https://example.org/evidence'
    public=client.get('/api/v1/snapshot').json()
    assert public['sources']==[]
    assert any(t['kind']=='sources' and t['record']['id']=='test-source' for t in public['tombstones'])
    assert 'PRIVATE-EDITORIAL-REASON-MARKER' not in json.dumps(detail)


def test_migration_two_upgrades_v1_projection_columns_without_rewriting_history(app,client,source):
    record=publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    with app.state.session_factory() as session:
        original=[r.payload for r in session.scalars(select(Revision).order_by(Revision.id))]
    # Represent the actually released v1 schema by removing only v2 additions.
    with app.state.engine.begin() as connection:
        for table,columns in V2_COLUMNS.items():
            for column in columns:connection.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {column}')
        connection.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version==2))
    assert migrate(app.state.engine)==2
    assert migrate(app.state.engine)==2
    with app.state.session_factory() as session:
        assert [r.payload for r in session.scalars(select(Revision).order_by(Revision.id))]==original
        assert set(session.scalars(select(SchemaVersion.version)))=={1,2}
        assert session.scalar(select(PROJECTIONS['occurrences'].c.causal_connections))==[]
    assert client.get('/api/v1/records/occurrences/test-occurrence').json()['record']['revision']==record['revision']


def test_prior_v1_private_backup_restores_and_upgrades_without_losing_revisions(app,client,source,tmp_path):
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    create(client,'occurrences',occurrence_payload('private-draft',summary='Private restoration fixture'))
    path=tmp_path/'v1-private-backup.json';backup(app.state.engine,path)
    data=json.loads(path.read_text())
    # A real v1 backup lacks these projection columns and migration 2.
    data['schema_version']=1
    data['tables']['schema_versions']=[r for r in data['tables']['schema_versions'] if r['version']==1]
    for table,columns in V2_COLUMNS.items():
        for row in data['tables'][table]:
            for name in columns:row.pop(name)
    for row in data['tables']['revisions']:
        kind=row['record_key'].split(':',1)[0]
        for name in V2_COLUMNS.get(kind,{}):row['payload'].pop(name,None)
        row['payload'].pop('publication_changed_at',None)
    data['sha256']=content_digest(data['tables']);path.write_text(json.dumps(data))
    engine=make_engine('sqlite:///'+str(tmp_path/'upgraded.db'))
    result=restore(engine,path)
    assert result['source_schema_version']==1 and result['schema_version']==SCHEMA_VERSION
    with sessions(engine)() as session:
        assert set(session.scalars(select(SchemaVersion.version)))=={1,2}
        assert get_detail(session,'occurrences','private-draft',private=True)['record']['summary']=='Private restoration fixture'
        assert len(snapshot(session)['occurrences'])==1
    with sessions(engine).begin() as session:
        assert seed_import(session,{'schema_version':'1.0','meta':{'new_packet':'same source after schema upgrade'},'sources':[source_payload()]})['skipped']==1


def test_new_reviewed_record_and_withdrawn_source_rebuild_as_tombstones_only(app,client,source,tmp_path):
    observed=publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    retire_api(client,'occurrences',observed['id'],observed['revision'])
    retire_api(client,'sources',source['id'],source['revision'])
    packet=export_packet(app,tmp_path)
    assert packet['occurrences']==[] and packet['sources']==[]
    assert {a['kind'] for a in packet['publication_actions']}=={'occurrences','sources'}
    assert all(a.get('record') for a in packet['publication_actions'])
    engine=make_engine('sqlite://');migrate(engine);factory=sessions(engine)
    with factory.begin() as session:
        seed_import(session,packet)
        assert not session.scalar(select(Record))  # No active baseline facts were created.
        assert apply_actions(session,packet)=={'applied':2,'skipped':0}
        public=snapshot(session)
        assert public['occurrences']==[] and public['sources']==[]
        assert len(public['tombstones'])==2
        assert all(t['record']['publication_status']=='retracted' for t in public['tombstones'])
        detail=get_detail(session,'occurrences','test-occurrence')
        assert detail['record']['summary']==observed['summary']
        assert detail['sources'][0]['url']==source['url']
        assert 'PRIVATE-EDITORIAL-REASON-MARKER' not in json.dumps(detail)


def test_historical_tombstone_import_still_requires_review_and_linked_evidence(app,client):
    bad=occurrence_payload(source_ids=[])
    bad.update(publication_status='retracted',publication_changed_at=NOW)
    packet={'schema_version':'1.0','publication_actions':[dict(kind='occurrences',id=bad['id'],action='retract',published_at=NOW,record=bad)]}
    with pytest.raises(ServiceError,match='linked eligible sources'):
        with app.state.session_factory.begin() as session:apply_actions(session,packet)
    assert client.get('/api/v1/editor/records/occurrences/test-occurrence',headers=AUTH).status_code==404


def test_active_and_retired_claims_preserve_original_source_pin_after_correction_and_rebuild(app,client,source,tmp_path):
    observed=publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    correction=dict(source,url='https://example.org/corrected-catalog-url',title='Corrected current source catalog')
    draft=client.put('/api/v1/editor/records/sources/test-source',headers=AUTH,
                     json={'record':correction,'expected_revision':source['revision'],'reason':'Correct current source metadata'}).json()
    publish(client,'sources',draft)
    detail=client.get('/api/v1/records/occurrences/test-occurrence').json()
    assert detail['sources'][0]['url']=='https://example.org/evidence'
    public=client.get('/api/v1/snapshot').json()
    assert public['sources'][0]['url']=='https://example.org/corrected-catalog-url'
    assert public['occurrences'][0]['source_snapshots'][0]['url']=='https://example.org/evidence'
    packet=export_packet(app,tmp_path)
    engine=make_engine('sqlite://');migrate(engine);factory=sessions(engine)
    with factory.begin() as session:
        seed_import(session,packet);apply_actions(session,packet)
        assert snapshot(session)['sources'][0]['url']=='https://example.org/corrected-catalog-url'
        assert get_detail(session,'occurrences','test-occurrence')['sources'][0]['url']=='https://example.org/evidence'
    retire_api(client,'occurrences',observed['id'],observed['revision'])
    assert client.get('/api/v1/records/occurrences/test-occurrence').json()['sources'][0]['url']=='https://example.org/evidence'
    packet=export_packet(app,tmp_path)
    retired_engine=make_engine('sqlite://');migrate(retired_engine);retired_factory=sessions(retired_engine)
    with retired_factory.begin() as session:
        seed_import(session,packet);apply_actions(session,packet)
        assert get_detail(session,'occurrences','test-occurrence')['sources'][0]['url']=='https://example.org/evidence'
        assert snapshot(session)['tombstones'][0]['record']['source_snapshots'][0]['url']=='https://example.org/evidence'


def test_captured_source_metadata_never_exports_private_source_drafts(app,client,source,tmp_path):
    private=dict(source,title='PRIVATE-PENDING-CORRECTION')
    response=client.put('/api/v1/editor/records/sources/test-source',headers=AUTH,
                        json={'record':private,'expected_revision':source['revision'],'reason':'PRIVATE-EDITORIAL-REASON-MARKER'})
    assert response.status_code==200
    observed=publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    assert 'PRIVATE-' not in client.get('/api/v1/snapshot').text
    assert 'PRIVATE-' not in client.get('/api/v1/records/occurrences/test-occurrence').text
    export_packet(app,tmp_path)
    retire_api(client,'occurrences',observed['id'],observed['revision'])
    assert 'PRIVATE-' not in client.get('/api/v1/snapshot').text
    export_packet(app,tmp_path)
