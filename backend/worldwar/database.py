"""SQLAlchemy setup and a forward-only, versioned migration registry."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, SchemaVersion
from .schemas import utc_now

SCHEMA_VERSION = 2
MIGRATIONS = {
    1: 'Initial typed domains, identities, revisions, evidence, jobs and candidate inbox',
    2: 'Explicit source, observation, campaign, coverage and pinned-evidence provenance',
}
# (portable SQL type/default clause, Python default for restoring v1 backups).
V2_COLUMNS = {
    'evidence_links': {'source_snapshot': ('JSON', None)},
    'sources': {'source_updated_date': ('DATE', None), 'published_time_raw': ('TEXT', None)},
    'occurrences': {'evidence_locator': ('TEXT', None), 'causal_connections': ("JSON NOT NULL DEFAULT '[]'", []),
                    'time_local_raw': ('TEXT', None), 'purpose': ('TEXT', None), 'event_scope': ('TEXT', None),
                    'reported_ongoing_as_of': ('DATE', None)},
    'campaigns': {'count_eligible': ('BOOLEAN NOT NULL DEFAULT FALSE', False),
                  'causal_connections': ("JSON NOT NULL DEFAULT '[]'", []),
                  'inclusion_rationale': ('TEXT', None), 'evidence_locator': ('TEXT', None),
                  'places_reported': ("JSON NOT NULL DEFAULT '[]'", []), 'date_uncertainty': ('TEXT', None),
                  'campaign_scope': ('TEXT', None), 'action_mix': ("JSON NOT NULL DEFAULT '[]'", [])},
    'coverage': {'assessment_method': ('TEXT', None), 'search_audit_key': ('TEXT', None)},
}



def make_engine(url: str | None = None):
    url = url or os.environ.get('WORLDWAR_DATABASE_URL', 'sqlite:///./worldwar.db')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    kwargs = {'pool_pre_ping': True}
    if url.startswith('sqlite:'):
        kwargs['connect_args'] = {'check_same_thread': False, 'timeout': 30}
        if url in ('sqlite://', 'sqlite:///:memory:'):
            kwargs['poolclass'] = StaticPool
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def sqlite_constraints(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=30000')
    return engine


def migrate(engine):
    """Apply registered versions atomically; never silently adopt a newer schema.

    Run once as a deployment step before starting multiple API workers. Initial
    create_all is the explicit v1 migration, not an unversioned startup mutation.
    """
    SchemaVersion.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(192023001)'))
        versions = set(connection.scalars(select(SchemaVersion.version)))
        if versions and max(versions) > SCHEMA_VERSION:
            raise RuntimeError('database schema is newer than this service')
        if versions and versions != set(range(1, max(versions) + 1)):
            raise RuntimeError('database migration registry has gaps')
        if 1 not in versions:
            Base.metadata.create_all(connection)
            install_immutability(connection)
            connection.execute(SchemaVersion.__table__.insert().values(
                version=1, applied_at=utc_now(), description=MIGRATIONS[1]))
        if 2 not in versions:
            for table, columns in V2_COLUMNS.items():
                existing = {c['name'] for c in inspect(connection).get_columns(table)}
                for name, (ddl, _) in columns.items():
                    if name not in existing:
                        connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
            install_evidence_immutability(connection)
            connection.execute(SchemaVersion.__table__.insert().values(
                version=2, applied_at=utc_now(), description=MIGRATIONS[2]))
    return SCHEMA_VERSION


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)


def install_immutability(connection):
    """Database-enforced append-only revision log, including direct SQL access."""
    if connection.dialect.name == 'sqlite':
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT, 'revisions are immutable'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT, 'revisions are immutable'); END")
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql("CREATE OR REPLACE FUNCTION worldwar_immutable_revision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'revisions are immutable'; END; $$")
        connection.exec_driver_sql("CREATE TRIGGER revisions_immutable BEFORE UPDATE OR DELETE ON revisions FOR EACH ROW EXECUTE FUNCTION worldwar_immutable_revision()")


def install_evidence_immutability(connection):
    if connection.dialect.name == 'sqlite':
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence_links BEGIN SELECT RAISE(ABORT, 'evidence links are immutable'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence_links BEGIN SELECT RAISE(ABORT, 'evidence links are immutable'); END")
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'evidence_links_immutable' AND tgrelid = 'evidence_links'::regclass) THEN CREATE TRIGGER evidence_links_immutable BEFORE UPDATE OR DELETE ON evidence_links FOR EACH ROW EXECUTE FUNCTION worldwar_immutable_revision(); END IF; END; $$")
