"""Portable private backups, empty-target restores and reproducible verification."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import Date, DateTime, func, insert, select, text

from .database import SCHEMA_VERSION, V2_COLUMNS, make_engine, migrate, sessions
from .models import Base, Record, Revision
from .schemas import utc_now, validate_record
from .service import ServiceError, snapshot


def json_value(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
    return value.isoformat() if isinstance(value, date) else value


def content_digest(data):
    # Stream canonical JSON into the digest to avoid a second full-size string
    # and bytes allocation when backing up a large discovery archive.
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    sha = hashlib.sha256()
    pending, size = [], 0
    for part in encoder.iterencode(data):
        pending.append(part)
        size += len(part)
        if size >= 65536:
            sha.update(''.join(pending).encode())
            pending, size = [], 0
    if pending:
        sha.update(''.join(pending).encode())
    return sha.hexdigest()


def write_json(path, value, *, private=False):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Publish/backup via atomic rename; an interrupted write cannot truncate the
    # previous known-good artifact. Backups contain private drafts and reasons.
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.' + target.name + '-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600 if private else 0o644)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backup(engine, path):
    with engine.connect() as connection:
        if engine.dialect.name == 'postgresql':
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
        with connection.begin():
            if engine.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN')
            tables = {}
            for table in Base.metadata.sorted_tables:
                rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
                tables[table.name] = [{k: json_value(v) for k, v in row.items()} for row in rows]
    data = {'format': 'worldwar-private-backup-1', 'schema_version': SCHEMA_VERSION,
            'created_at': utc_now(), 'tables': tables, 'sha256': content_digest(tables)}
    write_json(path, data, private=True)
    return {'sha256': data['sha256'], 'counts': {k: len(v) for k, v in tables.items()}}


def restore(engine, path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format') != 'worldwar-private-backup-1' or data.get('schema_version') not in (1, SCHEMA_VERSION):
        raise ServiceError(422, 'unsupported backup format/schema')
    tables = data.get('tables')
    if not isinstance(tables, dict) or data.get('sha256') != content_digest(tables):
        raise ServiceError(422, 'backup checksum does not match')
    if set(tables) != set(Base.metadata.tables):
        raise ServiceError(422, 'backup table registry does not match this schema')
    for row in tables['revisions']:
        kind = row['record_key'].split(':', 1)[0]
        validate_record(kind, row['payload'])
    migrate(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name != 'schema_versions' and connection.scalar(select(func.count()).select_from(table)):
                raise ServiceError(409, 'restore target must be empty; choose a fresh database')
        versions = tables['schema_versions']
        if {v['version'] for v in versions} != set(range(1, data['schema_version'] + 1)):
            raise ServiceError(422, 'backup migration registry is inconsistent')
        # Keep the original migration provenance rather than the new target's time.
        connection.execute(Base.metadata.tables['schema_versions'].delete())
        for table in Base.metadata.sorted_tables:
            rows = []
            for row in tables[table.name]:
                expected = {c.name for c in table.c}
                missing = expected - set(row)
                defaults = V2_COLUMNS.get(table.name, {}) if data['schema_version'] == 1 else {}
                if set(row) - expected or missing - set(defaults):
                    raise ServiceError(422, 'backup row has missing or unknown columns')
                parsed = dict(row)
                for name in missing:
                    parsed[name] = defaults[name][1]
                for c in table.c:
                    if parsed[c.name] is not None and isinstance(c.type, DateTime):
                        parsed[c.name] = datetime.fromisoformat(parsed[c.name])
                    elif parsed[c.name] is not None and isinstance(c.type, Date):
                        parsed[c.name] = date.fromisoformat(parsed[c.name])
                rows.append(parsed)
            for start in range(0, len(rows), 500):
                connection.execute(insert(table), rows[start:start + 500])
        if engine.dialect.name == 'sqlite':
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
                raise ServiceError(422, 'restored data failed foreign-key validation')
        elif engine.dialect.name == 'postgresql':
            connection.execute(text("SELECT setval(pg_get_serial_sequence('revisions', 'id'), COALESCE((SELECT MAX(id) FROM revisions), 1), EXISTS(SELECT 1 FROM revisions))"))
    if data['schema_version'] < SCHEMA_VERSION:
        migrate(engine)  # Upgrade after preserving the original immutable rows.
    return {'sha256': data['sha256'], 'counts': {k: len(v) for k, v in tables.items()}, 'source_schema_version': data['schema_version'], 'schema_version': SCHEMA_VERSION}


def verify_restore(engine, *, backup_path=None):
    with tempfile.TemporaryDirectory(prefix='worldwar-restore-') as directory:
        path = backup_path or str(Path(directory) / 'backup.json')
        original = backup(engine, path)
        with sessions(engine)() as session:
            before_sha256 = content_digest(snapshot(session, export=True))
        restored = make_engine('sqlite:///' + str(Path(directory) / 'restored.db'))
        try:
            recovered = restore(restored, path)
            with sessions(restored)() as session:
                after_sha256 = content_digest(snapshot(session, export=True))
            # Compare every table again, including private revisions, evidence links,
            # ingestion identities and source date precision, not just public counts.
            second = backup(restored, str(Path(directory) / 'restored-backup.json'))
            public_equal = before_sha256 == after_sha256
            all_tables_equal = original['sha256'] == second['sha256']
            if not public_equal or not all_tables_equal:
                raise RuntimeError('restore roundtrip did not preserve all database content')
            return dict(status='ok', verified_at=utc_now(), target='fresh SQLite database',
                        public_snapshot_sha256=before_sha256, database_sha256=original['sha256'],
                        public_equal=public_equal, all_tables_equal=all_tables_equal, counts=recovered['counts'])
        finally:
            restored.dispose()
