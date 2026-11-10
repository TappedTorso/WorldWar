"""The private queue pages current revisions in SQL, with literal search."""
from sqlalchemy import event

from conftest import AUTH, create, occurrence_payload, publish, source_payload
from worldwar.service import create_draft


def queue(client, **params):
    response = client.get('/api/v1/editor/records', params=params, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_queue_default_bound_stable_pages_and_constant_query_count(client, app):
    with app.state.session_factory.begin() as session:
        for number in reversed(range(105)):
            create_draft(session, 'sources', source_payload(f'source-{number:03}'), 'Synthetic paginated queue')
    selects = []
    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            selects.append(statement)
    event.listen(app.state.engine, 'before_cursor_execute', record_select)
    try:
        first = queue(client)
    finally:
        event.remove(app.state.engine, 'before_cursor_execute', record_select)
    assert len(selects) == 2  # Count + page; never one revision query per row.
    assert first['total'] == 105 and first['limit'] == 100 and first['offset'] == 0
    assert first['has_more'] is True
    assert [x['record']['id'] for x in first['items']] == [f'source-{n:03}' for n in range(100)]
    last = queue(client, limit=100, offset=100)
    assert last['total'] == 105 and last['has_more'] is False
    assert [x['record']['id'] for x in last['items']] == [f'source-{n:03}' for n in range(100, 105)]
    beyond = queue(client, limit=50, offset=999)
    assert beyond == {'items': [], 'total': 105, 'limit': 50, 'offset': 999, 'has_more': False}


def test_queue_kind_status_and_mixed_kind_order(client, source):
    create(client, 'occurrences', occurrence_payload('draft-a'))
    publish(client, 'occurrences', create(client, 'occurrences', occurrence_payload('published-b')))
    retired = publish(client, 'occurrences', create(client, 'occurrences', occurrence_payload('retired-c')))
    response = client.post('/api/v1/editor/records/occurrences/retired-c/retract', headers=AUTH,
                           json={'expected_revision': retired['revision'], 'reason': 'Synthetic queue retirement'})
    assert response.status_code == 200, response.text
    assert queue(client, kind='occurrences')['total'] == 1
    assert queue(client, status='published', kind='occurrences')['total'] == 1
    assert queue(client, status='retracted')['items'][0]['record']['id'] == 'retired-c'
    first = queue(client, status='all', limit=2)
    last = queue(client, status='all', kind='all', limit=2, offset=2)
    assert first['total'] == last['total'] == 4
    assert [(x['kind'], x['record']['id']) for x in first['items'] + last['items']] == [
        ('occurrences', 'draft-a'), ('occurrences', 'published-b'), ('occurrences', 'retired-c'),
        ('sources', 'test-source')]


def test_queue_searches_only_current_revision_id_title_summary_and_escapes_wildcards(client, source):
    original = create(client, 'occurrences', occurrence_payload('search-id', title='Obsolete historical needle'))
    updated = dict(original, title='Current title 100%_real', summary='Current summary UNIQUE-SUMMARY')
    response = client.put('/api/v1/editor/records/occurrences/search-id', headers=AUTH,
                          json={'record': updated, 'expected_revision': original['revision'],
                                'reason': 'Synthetic current revision search'})
    assert response.status_code == 200, response.text
    create(client, 'occurrences', occurrence_payload('other-id', title='Current title 100X-real'))
    for needle in ['SEARCH-ID', 'current TITLE 100%_real', 'unique-summary', '100%_real']:
        page = queue(client, kind='occurrences', q=needle, limit=1)
        assert page['total'] == 1 and page['items'][0]['record']['id'] == 'search-id'
        assert page['items'][0]['record']['revision'] == 2
    assert queue(client, kind='occurrences', q='Obsolete historical needle')['total'] == 0
    assert queue(client, kind='sources', q='UNIQUE-SUMMARY')['total'] == 0


def test_queue_parameter_validation_and_authentication(client):
    for params in [{'limit': 0}, {'limit': 201}, {'offset': -1}, {'kind': 'unknown'}, {'q': 'x' * 301}]:
        assert client.get('/api/v1/editor/records', params=params, headers=AUTH).status_code == 422
    assert client.get('/api/v1/editor/records', params={'limit': 50, 'offset': 0}).status_code == 401
