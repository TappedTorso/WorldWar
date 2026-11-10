from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worldwar.api import create_app

TOKEN = 'test-token-only-never-a-real-credential'
AUTH = {'Authorization': f'Bearer {TOKEN}'}
NOW = '2026-11-10T12:00:00Z'


def source_payload(stable_id='test-source'):
    return dict(id=stable_id, title='Synthetic primary-source fixture', url='https://example.org/evidence',
                publisher='Synthetic test publisher', source_type='primary', published_at=None,
                published_date='2026-10-01', publication_precision='day', retrieved_at=NOW,
                retrieval_precision='timestamp', rights='Synthetic test fixture only', note='Not a real-world claim')


def occurrence_payload(stable_id='test-occurrence', **changes):
    payload = dict(id=stable_id, title='Synthetic observation', summary='Test-only observation, not a real-world claim.',
                   source_ids=['test-source'], evidence_status='reviewed', reviewed_at=NOW,
                   country_code='ZZ', country='Synthetic fixture', place_name='Synthetic square',
                   location_precision='city', occurred_start='2026-11-05', occurred_end=None,
                   date_precision='day', action_type='demonstration', demands=[], targets=[],
                   campaign_ids=[], inclusion_rationale='Synthetic significant-observation test', confidence_note='Test only')
    payload.update(changes)
    return payload


@pytest.fixture
def app(tmp_path):
    return create_app('sqlite:///' + str(tmp_path / 'test.db'), TOKEN)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def create(client, kind, record):
    response = client.post('/api/v1/editor/records/' + kind,
                           json={'record': record, 'reason': 'Synthetic test creation'}, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


def publish(client, kind, record):
    response = client.post(f'/api/v1/editor/records/{kind}/{record["id"]}/publish',
                           json={'expected_revision': record['revision'], 'reason': 'Synthetic publication test'}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def source(client):
    return publish(client, 'sources', create(client, 'sources', source_payload()))
