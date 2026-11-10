"""The owner launcher serves the real API and only the deliberate web artifact."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

spec = importlib.util.spec_from_file_location('run_workspace', Path(__file__).resolve().parents[2] / 'scripts/run_workspace.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def web_build(tmp_path):
    web = tmp_path / 'public'
    (web / 'assets').mkdir(parents=True)
    (web / 'data').mkdir()
    (web / 'index.html').write_text('<html>WorldWar local workspace</html>')
    (web / 'data/research.json').write_text('{}')
    return web


def test_same_origin_api_requires_editor_auth_and_does_not_serve_private_siblings(tmp_path):
    web = web_build(tmp_path)
    (tmp_path / 'editor-key.txt').write_text('private-sibling-marker')
    app = launcher.application(web, f'sqlite:///{tmp_path / "private.db"}', 'synthetic-owner-key')
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/api/v1/health').json()['editor_enabled'] is True
        assert client.get('/api/v1/editor/records').status_code == 401
        assert client.get('/api/v1/editor/records', headers={'Authorization': 'Bearer synthetic-owner-key'}).status_code == 200
        for path in ['/editor-key.txt', '/%2E%2E/editor-key.txt', '/private.db']:
            response = client.get(path)
            assert response.status_code == 404
            assert 'private-sibling-marker' not in response.text


def test_refuses_repository_or_incomplete_directory_as_web_root(tmp_path):
    with pytest.raises(ValueError, match='complete production'):
        launcher.application(tmp_path, 'sqlite://', 'test')


def test_refuses_private_database_inside_public_build(tmp_path):
    web = web_build(tmp_path)
    (web / 'research.db').write_bytes(b'private')
    with pytest.raises(ValueError, match='private or backend'):
        launcher.application(web, 'sqlite://', 'test')


@pytest.mark.parametrize('private_name', ['editor-key.txt', 'EDITOR-KEY.TXT', 'research.db-wal'])
def test_refuses_credentials_and_database_sidecars_inside_public_build(tmp_path, private_name):
    web = web_build(tmp_path)
    (web / private_name).write_text('synthetic-private-marker')
    with pytest.raises(ValueError, match='private or backend'):
        launcher.application(web, 'sqlite://', 'test')


def test_rejects_runtime_in_web_before_creating_key_or_bootstrapping(tmp_path, monkeypatch):
    web = web_build(tmp_path)
    runtime = web / 'private-runtime'
    monkeypatch.setenv('WORLDWAR_DATABASE_URL', 'postgresql+psycopg://unused.invalid/test')
    monkeypatch.setattr('sys.argv', ['run_workspace.py', '--runtime-dir', str(runtime), '--web-dir', str(web)])
    with pytest.raises(ValueError, match='directories must be separate'):
        launcher.main()
    assert not runtime.exists()


def test_runtime_web_separation_checks_resolved_paths_both_directions(tmp_path):
    runtime = tmp_path / 'runtime'
    for web in [runtime, runtime / 'web']:
        with pytest.raises(ValueError, match='directories must be separate'):
            launcher.validate_workspace_paths(runtime, web)
    public = web_build(tmp_path)
    alias = tmp_path / 'public-alias'
    alias.symlink_to(public, target_is_directory=True)
    with pytest.raises(ValueError, match='directories must be separate'):
        launcher.validate_workspace_paths(alias / 'runtime', public)
    launcher.validate_workspace_paths(runtime, public)
