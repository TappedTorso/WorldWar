import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from worldwar.api import create_app
from worldwar.models import PROJECTIONS, Record, Revision
from worldwar.service import ServiceError, append_revision, create_draft, identity
from conftest import AUTH, NOW, TOKEN, create, occurrence_payload, publish, source_payload


def test_disabled_editor_blocks_private_reads_and_all_writes(tmp_path):
    with TestClient(create_app('sqlite:///' + str(tmp_path / 'disabled.db'), '')) as client:
        assert client.get('/api/v1/editor/records', headers=AUTH).status_code == 503
        assert client.post('/api/v1/editor/records/sources', headers=AUTH, json={'record':source_payload(), 'reason':'Test only'}).status_code == 503
        assert client.get('/api/v1/health').json()['editor_enabled'] is False


def test_authentication_no_token_leak_and_no_cookie_auth(client):
    for headers in ({}, {'Authorization': 'Bearer wrong'}, {'Cookie': 'WORLDWAR_EDITOR_TOKEN=' + TOKEN}, {'Authorization': 'Basic ' + TOKEN}):
        response = client.get('/api/v1/editor/records', headers=headers)
        assert response.status_code == 401
        assert TOKEN not in response.text
    response = client.get('/api/v1/editor/records', headers=AUTH)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'


def test_private_draft_correction_publication_separation_and_safe_history(client, source):
    draft = create(client, 'occurrences', occurrence_payload())
    assert client.get('/api/v1/records/occurrences/test-occurrence').status_code == 404
    assert client.get('/api/v1/snapshot').json()['occurrences'] == []
    assert len(client.get('/api/v1/editor/records', headers=AUTH).json()['items']) == 1
    original = publish(client, 'occurrences', draft)
    edited = dict(original, summary='PRIVATE-CORRECTION-MARKER')
    response = client.put('/api/v1/editor/records/occurrences/test-occurrence',
                          headers=AUTH, json={'record':edited, 'expected_revision':original['revision'], 'reason':'PRIVATE-REASON-MARKER'})
    assert response.status_code == 200
    updated = response.json()
    for path in ('/api/v1/snapshot', '/api/v1/search?q=PRIVATE', '/api/v1/export', '/api/v1/records/occurrences/test-occurrence'):
        public = client.get(path)
        assert 'PRIVATE-' not in public.text
    assert client.get('/api/v1/editor/records/occurrences/test-occurrence', headers=AUTH).json()['record']['summary'] == 'PRIVATE-CORRECTION-MARKER'
    publish(client, 'occurrences', updated)
    detail = client.get('/api/v1/records/occurrences/test-occurrence').json()
    assert detail['record']['summary'] == 'PRIVATE-CORRECTION-MARKER'
    assert 'PRIVATE-REASON-MARKER' not in json.dumps(detail)
    assert [r['revision'] for r in detail['revisions']] == [4, 2]


def test_source_validation_and_no_arbitrary_keys(client):
    for url in ('javascript:alert(1)', 'file:///etc/passwd', 'https://user:password@example.org/evidence', 'http://example.org/\nsecret'):
        record = source_payload(); record['url'] = url
        response = client.post('/api/v1/editor/records/sources', headers=AUTH, json={'record':record, 'reason':'Invalid source fixture'})
        assert response.status_code == 422
    record = source_payload(); record['full_text'] = 'SOURCE FULL TEXT MUST NOT BE STORED'
    assert client.post('/api/v1/editor/records/sources', headers=AUTH, json={'record':record, 'reason':'Invalid source fixture'}).status_code == 422


def test_publication_requires_eligible_evidence_and_review_and_rolls_back(client, source):
    for suffix, changes in [('missing-source', {'source_ids':[]}), ('unreviewed', {'evidence_status':'unreviewed'}),
                            ('no-review-date', {'reviewed_at':None}), ('bad-source', {'source_ids':['does-not-exist']})]:
        draft = create(client, 'occurrences', occurrence_payload(suffix, **changes))
        response = client.post(f'/api/v1/editor/records/occurrences/{suffix}/publish', headers=AUTH,
                               json={'expected_revision':draft['revision'], 'reason':'Should fail validation'})
        assert response.status_code == 422
        assert client.get(f'/api/v1/editor/records/occurrences/{suffix}',headers=AUTH).json()['record']['revision'] == 1
    assert client.get('/api/v1/snapshot').json()['occurrences'] == []


def test_duplicate_ids_stale_revisions_and_id_changes(client, source):
    draft = create(client, 'occurrences', occurrence_payload())
    assert client.post('/api/v1/editor/records/occurrences', headers=AUTH, json={'record':occurrence_payload(),'reason':'Duplicate ID fixture'}).status_code == 409
    public = publish(client,'occurrences',draft)
    assert client.put('/api/v1/editor/records/occurrences/test-occurrence', headers=AUTH,
                      json={'record':public,'expected_revision':1,'reason':'Stale fixture edit'}).status_code == 409
    changed = dict(public,id='other-id')
    assert client.put('/api/v1/editor/records/occurrences/test-occurrence', headers=AUTH,
                      json={'record':changed,'expected_revision':2,'reason':'Invalid identity change'}).status_code == 422


def test_retraction_tombstone_cannot_leak_pending_draft(client, source):
    public = publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    edited = dict(public,summary='SECRET-UNPUBLISHED-DRAFT')
    private = client.put('/api/v1/editor/records/occurrences/test-occurrence', headers=AUTH,
                          json={'record':edited,'expected_revision':public['revision'],'reason':'Private reason fixture'}).json()
    response = client.post('/api/v1/editor/records/occurrences/test-occurrence/retract', headers=AUTH,
                           json={'expected_revision':private['revision'],'reason':'Withdraw synthetic observation'})
    assert response.status_code == 200
    assert client.get('/api/v1/snapshot').json()['occurrences'] == []
    detail = client.get('/api/v1/records/occurrences/test-occurrence').json()
    assert detail['record']['publication_status'] == 'retracted'
    assert 'SECRET-' not in json.dumps(detail)


def test_merge_tombstone_target_validation_and_history(client, source):
    first = publish(client,'occurrences',create(client,'occurrences',occurrence_payload('first')))
    second = publish(client,'occurrences',create(client,'occurrences',occurrence_payload('second')))
    for target in ('first','missing'):
        assert client.post('/api/v1/editor/records/occurrences/first/merge',headers=AUTH,
                           json={'target_id':target,'expected_revision':2,'reason':'Merge duplicate test'}).status_code == 422
    merged = client.post('/api/v1/editor/records/occurrences/first/merge',headers=AUTH,
                          json={'target_id':'second','expected_revision':2,'reason':'Merge duplicate test'})
    assert merged.status_code == 200
    assert merged.json()['merged_into'] == 'second'
    assert [r['id'] for r in client.get('/api/v1/snapshot').json()['occurrences']] == ['second']
    assert client.get('/api/v1/records/occurrences/first').json()['record']['publication_status'] == 'merged'


def test_used_source_cannot_be_retracted(client, source):
    publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    response = client.post('/api/v1/editor/records/sources/test-source/retract',headers=AUTH,
                           json={'expected_revision':source['revision'],'reason':'Cannot orphan evidence'})
    assert response.status_code == 422


def test_relational_projection_and_immutable_audit(client, source, app):
    public = publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    with app.state.session_factory() as session:
        assert session.scalar(select(PROJECTIONS['occurrences'].c.country_code)) == 'ZZ'
        row = session.scalar(select(Revision).where(Revision.record_key=='occurrences:test-occurrence'))
        row.reason='Illegal history rewrite'
        with pytest.raises(ValueError, match='immutable'):
            session.flush()
        session.rollback()


def test_actual_concurrent_compare_and_swap(client, source, app):
    public = publish(client,'occurrences',create(client,'occurrences',occurrence_payload()))
    def edit(marker):
        response = client.put('/api/v1/editor/records/occurrences/test-occurrence',headers=AUTH,
                              json={'record':dict(public,summary=marker),'expected_revision':public['revision'],'reason':'Concurrent edit fixture'})
        return response.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(edit,('First concurrent edit','Second concurrent edit')))
    assert sorted(statuses) == [200,409]


def test_invalid_typed_data_fails(client, source):
    for changes in ({'longitude':181,'latitude':0},{'occurred_end':'2026-11-01'}, {'occurred_start':'2026-08-01'},
                    {'location_precision':'point','longitude':None,'latitude':None}):
        assert client.post('/api/v1/editor/records/occurrences',headers=AUTH,
                           json={'record':occurrence_payload(**changes),'reason':'Invalid typed fixture'}).status_code==422


def test_direct_sql_cannot_rewrite_revision_history(client,source,app):
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    with app.state.session_factory.begin() as session:
        with pytest.raises(IntegrityError,match='immutable'):
            session.execute(update(Revision).values(reason='Illegal direct SQL rewrite'))
        session.rollback()
