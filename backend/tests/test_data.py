import csv
import io
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from worldwar.database import make_engine, migrate, sessions
from worldwar.discovery import ingest_discovery
from worldwar.importers import legacy_import, seed_import
from worldwar.models import CandidateIngestion, ImportBatch, Job, Record, Revision
from worldwar.official_results import import_official_results
from worldwar.recovery import backup, restore, verify_restore
from worldwar.service import ServiceError, public_records, snapshot
from conftest import AUTH, NOW, create, occurrence_payload, publish, source_payload


def test_lossless_legacy_migration_every_record_and_provenance(app, client):
    original=json.loads((Path(__file__).parents[2]/'data/map_data.json').read_text())
    with app.state.session_factory.begin() as session:
        counts=legacy_import(session,original)
        assert counts=={'actors':82,'relationships':75}
    with app.state.session_factory.begin() as session:
        assert legacy_import(session,original)['already_imported'] is True
        result=snapshot(session,export=True)
    assert len(result['actors'])==82 and len(result['relationships'])==75
    assert {r['id']:r['legacy_payload'] for r in result['actors']} == {r['id']:r for r in original['nodes']}
    assert {r['id']:r['legacy_payload'] for r in result['relationships']} == {r['id']:r for r in original['edges']}
    assert all(r['evidence_status']=='legacy_unverified' and r['reviewed_at'] is None for r in result['actors']+result['relationships'])
    assert result['meta']['legacy_reviewed_at']==original['metadata']['last_reviewed_at']
    assert 'legacy_payload' not in client.get('/api/v1/snapshot').json()['actors'][0]


def test_atomic_seed_failure_preserves_nothing(app,client):
    packet={'schema_version':'1.0','sources':[source_payload()], 'occurrences':[occurrence_payload(source_ids=['unknown-source'])]}
    with pytest.raises(ServiceError):
        with app.state.session_factory.begin() as session:
            seed_import(session,packet)
    assert client.get('/api/v1/snapshot').json()['sources']==[]


def test_source_calendar_precision_is_not_fabricated_timestamp(client):
    source=source_payload(); source.update(retrieved_at=None,retrieval_date='2026-11-10',retrieval_precision='day')
    published=publish(client,'sources',create(client,'sources',source))
    assert published['published_at'] is None and published['published_date']=='2026-10-01'
    assert published['retrieved_at'] is None and published['retrieval_date']=='2026-11-10'
    assert published['publication_precision']=='day'


def test_discovery_dedup_failure_health_and_date_semantics(app,client):
    data={'metadata':{'provider':'GDELT_DOC_API','generated_at_utc':NOW,'status':'partial'},'events':[
        {'id':'old-article','headline':'Synthetic article','url':'https://example.org/article?utm_source=test','published_at':'20261110T000000Z'},
        {'id':'other-id','headline':'Same article','url':'https://example.org/article#fragment','published_at':'20261110T000000Z'},
        {'id':'bad-url','headline':'Invalid fixture','url':'javascript:alert(secret-token)'}]}
    result=ingest_discovery(app.state.session_factory,data,publish_unreviewed=True)
    assert result['accepted_count']==1 and result['rejected_count']==1 and result['status']=='partial'
    again=ingest_discovery(app.state.session_factory,data,publish_unreviewed=True)
    assert again['accepted_count']==0
    snapshot_data=client.get('/api/v1/snapshot').json()
    article=snapshot_data['developments'][0]
    assert article['evidence_status']=='unreviewed'
    assert article['published_at'] is None and article['occurred_start'] is None
    assert article['provider_seen_raw']=='20261110T000000Z'
    assert snapshot_data['occurrences']==[]
    assert 'secret-token' not in json.dumps(snapshot_data)
    failed=ingest_discovery(app.state.session_factory,{'not_events':[]})
    assert failed['status']=='error'
    assert len(client.get('/api/v1/snapshot').json()['developments'])==1


def test_private_discovery_candidates_not_in_public_build(app,client):
    data={'events':[{'id':'candidate','headline':'Private discovery fixture','url':'https://example.org/candidate','discovered_at':NOW,'published_at':None}]}
    assert ingest_discovery(app.state.session_factory,data)['accepted_count']==1
    assert client.get('/api/v1/snapshot').json()['developments']==[]
    items=client.get('/api/v1/editor/records',headers=AUTH).json()['items']
    assert {i['kind'] for i in items}=={'sources','developments'}


def test_csv_formula_neutralization_and_export_parity(client,source):
    public=publish(client,'occurrences',create(client,'occurrences',occurrence_payload(summary='\t=HYPERLINK("https://example.org")')))
    expected=client.get('/api/v1/snapshot').json()['occurrences']
    assert client.get('/api/v1/export?kind=occurrences').json()==expected
    csv_rows=list(csv.DictReader(io.StringIO(client.get('/api/v1/export?kind=occurrences&format=csv').text)))
    assert csv_rows[0]['summary'].startswith("'\t=")
    assert client.get('/api/v1/export?format=csv').status_code==422
    assert client.get('/api/v1/search?q=HYPERLINK&domain=protests').json()['items'][0]['id']=='test-occurrence'


def test_scorecard_correction_coverage_and_merge_change_counts(client,source):
    def coverage(stable_id,start,end):
        return dict(id=stable_id,domain='protests',geography='ZZ',country_code='ZZ',period_start=start,period_end=end,
                    status='reviewed',source_ids=['test-source'],note='Synthetic whole-country coverage fixture',reviewed_at=NOW)
    publish(client,'coverage',create(client,'coverage',coverage('current-coverage','2026-11-01','2026-11-10')))
    first=publish(client,'occurrences',create(client,'occurrences',occurrence_payload('first')))
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==1 and card['momentum']=='insufficient_data' and card['previous_occurrence_count'] is None
    publish(client,'coverage',create(client,'coverage',coverage('prior-coverage','2026-10-01','2026-10-10')))
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['momentum']=='increased' and card['previous_occurrence_count']==0
    edit=dict(first,occurred_start='2026-10-05')
    draft=client.put('/api/v1/editor/records/occurrences/first',headers=AUTH,
                     json={'record':edit,'expected_revision':2,'reason':'Correct synthetic observation date'}).json()
    assert client.get('/api/v1/snapshot').json()['scorecards'][0]['occurrence_count']==1
    publish(client,'occurrences',draft)
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==0 and card['previous_occurrence_count']==1 and card['momentum']=='decreased'
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload('second',count_eligible=False)))
    assert client.get('/api/v1/snapshot').json()['scorecards'][0]['occurrence_count']==0


def test_backup_restore_private_public_and_corruption_checks(app,client,source,tmp_path):
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    create(client,'occurrences',occurrence_payload('private',summary='PRIVATE-RESTORE-PROOF'))
    report=verify_restore(app.state.engine)
    assert report['all_tables_equal'] and report['public_equal']
    backup_path=tmp_path/'private-backup.json'
    backup(app.state.engine,backup_path)
    assert backup_path.stat().st_mode & 0o777 == 0o600
    restored=make_engine('sqlite:///'+str(tmp_path/'restored.db'))
    restore(restored,backup_path)
    with pytest.raises(ServiceError,match='empty'):
        restore(restored,backup_path)
    data=json.loads(backup_path.read_text()); data['tables']['records'][0]['kind']='corrupted'
    backup_path.write_text(json.dumps(data))
    fresh=make_engine('sqlite://')
    with pytest.raises(ServiceError,match='checksum'):
        restore(fresh,backup_path)


def test_snapshot_bounds_discovery_search_and_export_preserve_archive(app,client):
    packet={'events':[dict(id=f'article-{n:03}',headline=f'Synthetic discovery {n}',url=f'https://example.org/article/{n}',discovered_at=NOW) for n in range(255)]}
    assert ingest_discovery(app.state.session_factory,packet,publish_unreviewed=True)['accepted_count']==255
    data=client.get('/api/v1/snapshot').json()
    assert len(data['developments'])==250
    assert data['meta']['discovery_total']==255 and data['meta']['discovery_visible']==250
    assert len(client.get('/api/v1/export?kind=developments').json())==255
    assert len(client.get('/api/v1/search?q=Synthetic%20discovery').json()['items'])==255
    assert client.get('/api/v1/records/developments/article-000').status_code==200


def test_reciprocal_campaign_occurrence_seed_is_atomic_and_idempotent(app,client):
    occurrence=occurrence_payload(campaign_ids=['test-campaign'])
    campaign=dict(id='test-campaign',title='Synthetic campaign',summary='Not a real-world finding',source_ids=['test-source'],
                  evidence_status='reviewed',reviewed_at=NOW,country_codes=['ZZ'],started_at='2026-11-01',
                  demands=[],targets=[],occurrence_ids=['test-occurrence'])
    packet={'schema_version':'1.0','sources':[source_payload()],'occurrences':[occurrence],'campaigns':[campaign]}
    with app.state.session_factory.begin() as session:
        assert seed_import(session,packet)['created']==3
    with app.state.session_factory.begin() as session:
        assert seed_import(session,packet)['already_imported']
    assert client.get('/api/v1/snapshot').json()['scorecards'][0]['campaign_count']==1


def test_bulk_archive_semantics_provenance_and_deterministic_build(tmp_path):
    data={'metadata':{'kind':'discovery_archive'},'events':[
        dict(id='archive-fixture',headline='Synthetic archived article',url='https://example.org/archive',
             discovered_at='2026-10-01T12:00:00Z',retrieved_at='2026-10-01T13:00:00Z',
             first_seen_at='2026-10-01T12:00:00Z',last_seen_at='2026-10-02T12:00:00Z',published_at=None,
             provider_seen_raw='20261001T120000Z',first_repository_revision='synthetic-revision')
    ]}
    builds=[]
    for index in range(2):
        engine=make_engine('sqlite:///'+str(tmp_path/f'build-{index}.db'));migrate(engine);factory=sessions(engine)
        assert ingest_discovery(factory,data,publish_unreviewed=True)['accepted_count']==1
        assert ingest_discovery(factory,data,publish_unreviewed=True)['accepted_count']==0
        with factory() as session:
            builds.append(snapshot(session))
            candidate=session.scalar(select(CandidateIngestion))
            assert candidate.first_seen_at=='2026-10-01T12:00:00Z'
            assert candidate.last_seen_at=='2026-10-02T12:00:00Z'
            assert candidate.provenance['first_repository_revision']=='synthetic-revision'
        engine.dispose()
    assert builds[0]==builds[1]
    assert builds[0]['jobs']==[]
    assert builds[0]['sources'][0]['published_at'] is None
    assert builds[0]['sources'][0]['retrieved_at']=='2026-10-01T13:00:00Z'


def test_collection_run_health_idempotency_and_secret_sanitization(app,client):
    from worldwar.jobs import import_jobs
    packet=[dict(id='test-job',adapter='test-adapter',domain='conflicts',started_at=NOW,completed_at=NOW,status='partial',
                 fetched_count=0,accepted_count=2,error='HTTP 429 https://user:pass@example.org/api?token=SECRET api_key=SECRET Bearer SECRET')]
    with app.state.session_factory.begin() as session:
        assert import_jobs(session,packet)['created']==1
    with app.state.session_factory.begin() as session:
        assert import_jobs(session,packet)['skipped']==1
    data=client.get('/api/v1/snapshot').json()
    assert data['jobs'][0]['status']=='partial'
    assert 'SECRET' not in json.dumps(data) and 'user:pass' not in json.dumps(data)


def test_official_adapter_is_bounded_unreviewed_and_preserves_prior_tallies(app,client):
    official=source_payload('official-test');official['source_type']='official'
    contest=dict(id='synthetic-contest',title='Synthetic unofficial tally',summary='Test only',source_ids=['official-test'],
                 evidence_status='unreviewed',review_method='validated_official_adapter',reviewed_at=None,
                 office='house',state_code='ZZ',jurisdiction='Synthetic jurisdiction',district='01',
                 geography_version=None,boundary_status='unavailable',status='reported_unofficial',result_as_of=NOW,
                 election_date='2026-11-03',candidates=[dict(name='Synthetic candidate',party=None,votes=10,percentage=100)],
                 winner=None,winner_basis=None,total_votes=10,reporting_note='Synthetic test-only source observation')
    packet={'schema_version':'1.0','sources':[official],'contests':[contest]}
    with app.state.session_factory.begin() as session:
        assert import_official_results(session,packet)['updated']==2
    result=client.get('/api/v1/snapshot').json()['contests'][0]
    assert result['evidence_status']=='unreviewed' and result['winner'] is None and result['reviewed_at'] is None
    changed=json.loads(json.dumps(packet));changed['contests'][0]['candidates'][0]['votes']=12;changed['contests'][0]['total_votes']=12
    with app.state.session_factory.begin() as session:
        assert import_official_results(session,changed)['updated']==1
    detail=client.get('/api/v1/editor/records/contests/synthetic-contest',headers=AUTH).json()
    assert detail['record']['total_votes']==12
    assert any(r['record']['total_votes']==10 for r in detail['revisions'])
    invalid=json.loads(json.dumps(changed));invalid['contests'][0]['winner']='Synthetic candidate';invalid['contests'][0]['winner_basis']='Fabricated fixture claim'
    with pytest.raises((ServiceError,ValueError)):
        with app.state.session_factory.begin() as session:
            import_official_results(session,invalid)
    # An ordinary editor publish cannot bypass the reviewed factual gate.
    response=client.post('/api/v1/editor/records/contests/synthetic-contest/publish',headers=AUTH,
                         json={'expected_revision':4,'reason':'Normal publish must require review'})
    assert response.status_code==422


def test_range_boundaries_do_not_invent_active_days_or_cross_window_counts(client,source):
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload('uncertain-range',occurred_start='2026-11-01',occurred_end='2026-11-05',date_precision='range')))
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==1 and card['active_days']==0
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload('explicit-dates',occurred_start='2026-11-01',occurred_end='2026-11-05',date_precision='range',active_dates=['2026-11-02','2026-11-04'])))
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==2 and card['active_days']==2
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload('cross-month-uncertainty',occurred_start='2026-10-31',occurred_end='2026-11-02',date_precision='range')))
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==2


def test_reviewed_legacy_correction_survives_publication_seed_rebuild(app,client):
    legacy={'metadata':{'last_reviewed_at':'2026-03-15T00:00:00Z'},'nodes':[
        dict(id='LEGACY',name='Synthetic actor',type='state',coords=[0,0],category='TEST',summary='Inherited test assertion',sources=[],updated_at='2026-03-14T00:00:00Z')], 'edges':[]}
    with app.state.session_factory.begin() as session:
        legacy_import(session,legacy)
    corrected=dict(id='LEGACY',title='Synthetic corrected actor',name='Synthetic actor',summary='Reviewed synthetic correction',
                   source_ids=['test-source'],evidence_status='reviewed',reviewed_at=NOW,updated_at=NOW,actor_type='state',
                   country_code='ZZ',longitude=0,latitude=0,theaters=[],category='TEST')
    packet={'schema_version':'1.0','sources':[source_payload()],'actors':[corrected]}
    with app.state.session_factory.begin() as session:
        seed_import(session,packet)
    public=client.get('/api/v1/export?kind=actors').json()[0]
    assert public['summary']=='Reviewed synthetic correction' and public['legacy_payload']==legacy['nodes'][0]
    detail=client.get('/api/v1/records/actors/LEGACY').json()
    assert any(r['record']['summary']=='Inherited test assertion' for r in detail['revisions'])
    assert all('reason' not in r for r in detail['revisions'])


def test_unknown_source_dates_never_create_epoch_metadata(client):
    record=source_payload();record.update(published_date=None,publication_precision='unknown',retrieved_at=None,retrieval_precision='unknown')
    publish(client,'sources',create(client,'sources',record))
    data=client.get('/api/v1/snapshot').json()
    assert data['meta']['generated_at'] and not data['meta']['generated_at'].startswith('1970')
    assert data['sources'][0]['retrieved_at'] is None and data['sources'][0]['published_at'] is None


def test_legacy_country_identity_and_relationship_titles(app,client):
    original=json.loads((Path(__file__).parents[2]/'data/map_data.json').read_text())
    with app.state.session_factory.begin() as session:
        legacy_import(session,original)
        data=snapshot(session)
    actors={r['id']:r for r in data['actors']}
    assert actors['UKRAINE']['country_code']=='UA'
    assert actors['UNITED_STATES']['country_code']=='US'
    assert actors['PALESTINE']['country_code']=='PS'
    assert actors['IRGC']['country_code'] is None
    relation=next(r for r in data['relationships'] if r['id']=='IRAN__ISRAEL__WAR')
    assert relation['title']=='Iran → Israel · Active Interstate War'
    assert relation['relationship_type']=='Active Interstate War'


def test_new_editor_records_cannot_smuggle_private_data_as_legacy_payload(client,source):
    payload=occurrence_payload(legacy_payload={'private_notes':'MUST NOT ENTER EXPORT'})
    response=client.post('/api/v1/editor/records/occurrences',headers=AUTH,json={'record':payload,'reason':'Reject reserved provenance field'})
    assert response.status_code==422
    assert 'MUST NOT ENTER EXPORT' not in client.get('/api/v1/export').text


def test_protest_source_candidate_inbox_never_publishes_facts(app,client):
    from worldwar.source_candidates import ingest_source_candidates
    packet={'events':[dict(id='synthetic-protest-article',headline='Synthetic candidate report',url='https://example.org/protest-candidate',
                           discovered_at=NOW,retrieved_at=NOW,published_at=None,provider_seen_raw='20261110T120000Z',lang='en')]}
    assert ingest_source_candidates(app.state.session_factory,packet,domain='protests')['accepted_count']==1
    assert ingest_source_candidates(app.state.session_factory,packet,domain='protests')['accepted_count']==0
    public=client.get('/api/v1/snapshot').json()
    assert not any(public[k] for k in ('sources','occurrences','developments','jobs'))
    items=client.get('/api/v1/editor/records',headers=AUTH).json()['items']
    assert len(items)==1 and items[0]['kind']=='sources' and items[0]['record']['source_type']=='discovery'
    with app.state.session_factory() as session:
        candidate=session.scalar(select(CandidateIngestion))
        assert candidate.provenance['candidate_domains']==['protests']
        assert candidate.source_published_at is None


def test_retracted_campaign_is_excluded_from_current_campaign_component(client,source):
    campaign=dict(id='synthetic-campaign',title='Synthetic campaign fixture',source_ids=['test-source'],evidence_status='reviewed',reviewed_at=NOW,
                  country_codes=['ZZ'],started_at='2026-11-01',demands=[],targets=[],occurrence_ids=[])
    publish(client,'campaigns',create(client,'campaigns',campaign))
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload(campaign_ids=['synthetic-campaign'])))
    assert client.get('/api/v1/snapshot').json()['scorecards'][0]['campaign_count']==1
    response=client.post('/api/v1/editor/records/campaigns/synthetic-campaign/retract',headers=AUTH,
                         json={'expected_revision':2,'reason':'Retract synthetic campaign fixture'})
    assert response.status_code==200
    card=client.get('/api/v1/snapshot').json()['scorecards'][0]
    assert card['occurrence_count']==1 and card['campaign_count']==0
