#!/usr/bin/env python3
"""Run a persistent, single-owner editorial workspace on the local computer."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def validate_workspace_paths(runtime: Path, web_directory: Path):
    """Keep private owner state outside every served directory."""
    runtime, web_directory = runtime.resolve(), web_directory.resolve()
    if runtime.is_relative_to(web_directory) or web_directory.is_relative_to(runtime):
        raise ValueError('runtime and web directories must be separate, without containing one another')


def application(web_directory: Path, database_url: str, editor_token: str):
    """Serve only an explicit production web build beside the authenticated API."""
    from fastapi.staticfiles import StaticFiles
    from worldwar.api import create_app

    web_directory = web_directory.resolve()
    if not all((web_directory / p).exists() for p in ('index.html', 'assets', 'data/research.json')):
        raise ValueError('web directory must contain the complete production frontend build')
    for file in web_directory.rglob('*'):
        name = file.name.lower()
        if file.is_file() and (name == 'editor-key.txt' or name.startswith('.env') or
                              name.endswith(('.db', '.sqlite', '.sqlite3', '.py', '.db-wal', '.db-shm',
                                             '.sqlite-wal', '.sqlite-shm', '.sqlite3-wal', '.sqlite3-shm'))):
            raise ValueError('private or backend files must not be inside the served web directory')
    app = create_app(database_url=database_url, editor_token=editor_token)
    app.mount('/', StaticFiles(directory=web_directory, html=True), name='web')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=ROOT / 'runtime')
    parser.add_argument('--web-dir', type=Path, default=ROOT / 'web/dist-owner')
    parser.add_argument('--seed-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--quiet-key', action='store_true', help='Do not print the private editor key')
    args = parser.parse_args()
    runtime = args.runtime_dir.expanduser().resolve()
    web_directory = args.web_dir.expanduser().resolve()
    validate_workspace_paths(runtime, web_directory)
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    token_file = runtime / 'editor-key.txt'
    if token_file.is_symlink():
        raise ValueError('editor key must be an ordinary owner-controlled file')
    token = os.environ.get('WORLDWAR_EDITOR_TOKEN', '')
    if not token:
        if not token_file.exists():
            descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                handle.write(secrets.token_urlsafe(32) + '\n')
        token_file.chmod(0o600)
        token = token_file.read_text().strip()
    if not token:
        raise ValueError('editor key cannot be empty')
    database_url = os.environ.get('WORLDWAR_DATABASE_URL', f'sqlite:///{runtime / "research.db"}')
    os.environ['WORLDWAR_DATABASE_URL'] = database_url
    os.environ['WORLDWAR_EDITOR_TOKEN'] = token
    os.environ['WORLDWAR_SEED_DIRECTORY'] = str(args.seed_dir.resolve())
    # Child CLI imports use the exact backend installed beside this launcher.
    os.environ['PYTHONPATH'] = str(ROOT / 'backend')
    from worldwar.database import make_engine
    from bootstrap_store import initialize
    engine = make_engine(database_url)
    try:
        print(initialize(engine, args.seed_dir.resolve()), flush=True)
    finally:
        engine.dispose()
    app = application(web_directory, database_url, token)
    url = f'http://127.0.0.1:{args.port}/'
    print(f'WorldWar owner workspace: {url}', flush=True)
    print(f'Private research data: {runtime}', flush=True)
    if not args.quiet_key:
        print(f'Editor key (paste into Editorial): {token}', flush=True)
    print('Keep this terminal open. Control-C stops the server; data remains saved.', flush=True)
    if args.open_browser:
        timer = threading.Timer(1.0, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
