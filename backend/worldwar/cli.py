"""Run with PYTHONPATH=backend python -m worldwar.cli --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .database import SCHEMA_VERSION, make_engine, migrate, sessions
from .discovery import ingest_discovery
from .importers import legacy_import, seed_import
from .official_results import import_official_results
from .jobs import import_jobs
from .source_candidates import ingest_source_candidates
from .publication import apply_actions, export_actions
from .recovery import backup, restore, verify_restore, write_json
from .service import ServiceError, snapshot


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='WorldWar data, editorial publication and recovery commands')
    parser.add_argument('--database-url', help='Override WORLDWAR_DATABASE_URL; default sqlite:///./worldwar.db')
    commands = parser.add_subparsers(dest='command', required=True)
    migration = commands.add_parser('migrate', help='Apply versioned schema, optionally import original legacy map and reviewed seed')
    migration.add_argument('--legacy')
    migration.add_argument('--seed')
    seed = commands.add_parser('seed', help='Import reviewed seed packet atomically; existing changed IDs are rejected')
    seed.add_argument('--input', required=True)
    overlay = commands.add_parser('apply-publication-actions', help='Apply explicit public retirement overlay AFTER every baseline import')
    overlay.add_argument('--input', required=True)
    for name in ('snapshot', 'export-seed'):
        command = commands.add_parser(name, help='Atomically write public snapshot' if name == 'snapshot' else 'Write only reviewed public seed content for Git review')
        command.add_argument('--output', required=True)
    discovery = commands.add_parser('ingest-discovery', help='Persist candidates and run health; no event promotion')
    discovery.add_argument('--input', required=True)
    discovery.add_argument('--adapter', default='gdelt')
    discovery.add_argument('--publish-unreviewed', action='store_true', help='Expose clearly labeled article metadata; never reviewed facts')
    candidates = commands.add_parser('ingest-source-candidates', help='Private source inbox only; no occurrence or development creation')
    candidates.add_argument('--input', required=True)
    candidates.add_argument('--domain', choices=['protests', 'elections', 'conflicts'], required=True)
    candidates.add_argument('--adapter', default='source-candidates')
    jobs = commands.add_parser('import-jobs', help='Import original public-safe collection run health')
    jobs.add_argument('--input', required=True)
    official = commands.add_parser('import-official-results', help='Append validated official unofficial tallies; never declare winners')
    official.add_argument('--input', required=True)
    official.add_argument('--publish-official-results', action='store_true', required=True)
    for name in ('backup', 'restore'):
        command = commands.add_parser(name, help='Private full backup' if name == 'backup' else 'Restore private backup into an EMPTY database')
        command.add_argument('--output' if name == 'backup' else '--input', required=True)
    verify = commands.add_parser('verify-restore', help='Prove all-table and public-snapshot roundtrip in a fresh SQLite DB')
    verify.add_argument('--output', help='Optional public-safe proof report')
    args = parser.parse_args(argv)
    engine = make_engine(args.database_url)
    factory = sessions(engine)
    try:
        if args.command == 'restore':
            result = restore(engine, args.input)
        else:
            migrate(engine)
            if args.command == 'migrate':
                with factory.begin() as session:
                    result = {'schema_version': SCHEMA_VERSION}
                    if args.legacy:
                        result['legacy'] = legacy_import(session, read_json(args.legacy))
                    if args.seed:
                        result['seed'] = seed_import(session, read_json(args.seed))
            elif args.command == 'seed':
                with factory.begin() as session:
                    result = seed_import(session, read_json(args.input))
            elif args.command == 'apply-publication-actions':
                with factory.begin() as session:
                    result = apply_actions(session, read_json(args.input))
            elif args.command == 'ingest-source-candidates':
                try:
                    data = read_json(args.input)
                except (ValueError, OSError):
                    data = {}
                result = ingest_source_candidates(factory, data, domain=args.domain, adapter=args.adapter)
            elif args.command == 'import-jobs':
                with factory.begin() as session:
                    result = import_jobs(session, read_json(args.input))
            elif args.command == 'import-official-results':
                with factory.begin() as session:
                    result = import_official_results(session, read_json(args.input))
            elif args.command == 'ingest-discovery':
                try:
                    data = read_json(args.input)
                except (ValueError, OSError):
                    # Persist a failed run even when the input file is malformed.
                    data = {}
                result = ingest_discovery(factory, data, adapter=args.adapter, publish_unreviewed=args.publish_unreviewed)
            elif args.command in ('snapshot', 'export-seed'):
                with factory() as session:
                    result = snapshot(session)
                    if args.command == 'export-seed':
                        result.pop('jobs', None)
                        result.pop('scorecards', None)
                        result.pop('tombstones', None)
                        actions = export_actions(session)
                        needed_sources = {i for a in actions for i in a.get('record', {}).get('source_ids', [])}
                        needed_sources.update(i for kind, rows in result.items() if isinstance(rows, list) and kind != 'sources' for r in rows if r.get('evidence_status', 'reviewed') == 'reviewed' for i in r.get('source_ids', []))
                        for kind, records in list(result.items()):
                            if isinstance(records, list):
                                if kind == 'sources':
                                    result[kind] = [r for r in records if r['source_type'] not in ('legacy_reference', 'discovery') or r['id'] in needed_sources]
                                else:
                                    result[kind] = [r for r in records if r.get('evidence_status', 'reviewed') == 'reviewed']
                        result['publication_actions'] = actions
                    write_json(args.output, result)
                    result = {'output': args.output, 'data_version': result['meta']['data_version']}
            elif args.command == 'backup':
                result = backup(engine, args.output)
            else:
                result = verify_restore(engine)
                if args.output:
                    write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get('status') == 'error' else 0
    except (ServiceError, ValueError) as exc:
        # CLI payload validation messages contain field paths, not credentials.
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
