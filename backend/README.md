# WorldWar research and editorial service

The same typed Python service builds the public static snapshot and serves the live API. SQLite runs locally with no purchased service; PostgreSQL is the service deployment path. All commands below run from the repository root unless stated otherwise. Python 3.12 or newer is supported. Exact runtime versions are in `requirements.lock`, with separately pinned test dependencies in `requirements-dev.txt`.

## Run a local workspace

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
export PYTHONPATH=backend
export WORLDWAR_DATABASE_URL=sqlite:///./work/worldwar.db
.venv/bin/python -m worldwar.cli migrate --legacy data/map_data.json --seed data/publication/seed.json
.venv/bin/python -m worldwar.cli import-official-results --input data/publication/official-results.json --publish-official-results
.venv/bin/python -m worldwar.cli ingest-discovery --input data/discovery/archive.json --adapter gdelt --publish-unreviewed
.venv/bin/python -m worldwar.cli import-jobs --input data/discovery/runs.json
.venv/bin/python -m worldwar.cli import-jobs --input data/discovery/election-runs.json
.venv/bin/python -m worldwar.cli snapshot --output web/public/data/research.json
```

Create the SQLite parent directory (`work/` in this example) before connecting. If `WORLDWAR_DATABASE_URL` is absent, the default is `sqlite:///./worldwar.db`. To run the live API, configure an editor token only in the process environment and bind the local service to loopback:

```sh
export WORLDWAR_EDITOR_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/uvicorn worldwar.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

The token is never written by this service or included in a snapshot. Enter it into the protected workspace's in-memory token field. Missing configuration returns 503 for all private reads and writes; a missing/incorrect bearer returns 401. `WORLDWAR_CORS_ORIGINS` is a comma-separated list of allowed frontend origins; the default permits only local Vite origins. A self-hosted internet deployment needs an HTTPS reverse proxy and the exact frontend origin. Do not expose a development SQLite server as a multi-maintainer deployment.

The API exposes health, methodology, snapshot, search, stable record detail, JSON/CSV exports, and real create/correct/publish/retract/merge commands under `/api/v1`. Interactive API documentation is at `/docs`. Editorial commands require a reason and, after creation, the exact current revision. A stale command returns 409 and does not change the record. A malformed or unpublishable record returns 422.

## Storage, migrations, and publication

`worldwar.database.MIGRATIONS` is the forward-only registry. Version 1 creates relational identities, immutable revisions, evidence links, record references, explicit typed per-revision domain tables, coverage, jobs, import batches and durable discovery candidates. JSON is used for audit snapshots, original legacy payloads and intrinsically list-valued fields, not a single generic event table. SQLite foreign keys are enabled; both SQLite and PostgreSQL install database triggers forbidding revision UPDATE and DELETE. ORM guards also reject history rewrites.

Run `migrate` as a deployment step before starting multiple API processes. Databases with a newer schema version fail closed. Future schema changes must add a numbered migration rather than silently mutate version 1. This initial version was built in isolated scratch databases; scratch databases created by earlier unreleased prototypes should be rebuilt rather than reused.

An identity has separate latest editorial and latest public revision pointers. Draft correction never changes a public read. Publication appends a new immutable revision in the same transaction as the public-pointer change. Retraction and merge tombstone the **public** revision, even when a private correction exists, so a pending draft cannot leak. Public detail includes previous public record snapshots and public revision actions/times. Private reasons and unpublished revisions are available only to authenticated editors. Source evidence links pin the source revision used at publication.

Normal factual publication requires typed data, linked eligible sources, evidence_status `reviewed` and a review timestamp. An ordinary discovery source cannot establish a reviewed occurrence. Optional participant/response/outcome claims require attribution. Crowd estimates carry their own named attribution and a linked source ID. Effect and intent claims require separate attributed evidence. Source URLs must be HTTP(S), contain no embedded credentials or credential query fields, and include rights metadata. Unknown fields and source full-text fields are rejected. `legacy_payload` is reserved for the lossless importer and cannot be introduced or altered by normal editorial writes.

The legacy importer retains every stable actor and relationship ID, every original JSON record byte-equivalent as structured `legacy_payload`, original citations/confidence/update strings, and original map metadata in the import batch. It does not reverify historical assertions. Explicit state/territory identity-to-alpha-2 mappings in `worldwar/legacy_country_codes.json` support country filtering; organizations/nonstate groups retain null country code. The crosswalk describes geography, not sovereignty, organizational nationality, or updated conflict facts. Relationship titles identify both endpoint actors and the original relationship type. `legacy_payload` is available in research exports, while normal snapshots and detail views use the labeled inherited metadata.

A reviewed seed packet is an explicit publication input. Identical reimports are no-ops. A changed seed cannot silently overwrite an existing reviewed record or pending editorial draft; use correction commands. A reviewed correction of an inherited legacy record can overlay that identity during a fresh build, retaining the exact inherited payload and history. Reciprocal campaign/occurrence links are validated and published atomically as one reviewed packet. An invalid packet rolls back entirely.

## Discovery and official results

`ingest-discovery` accepts an events/articles JSON wrapper. Without `--publish-unreviewed`, candidates and source drafts remain private. With that explicit flag, it can publish only visibly unreviewed **article metadata**, with no occurrence date and no promotion to an event/relationship. Unknown source publication timestamps stay null. Legacy GDELT provider-seen values are preserved as `provider_seen_raw`, never relabeled publication time. Retrieval, first/last seen, source publication and repository provenance are stored separately. Canonical URL deduplication removes fragments and common trackers; repeat imports do not create duplicate records or overwrite editorial content.

The preserved `discovery_archive` wrapper uses a bulk validated importer in durable 500-article chunks. It creates the same immutable create/publication revisions, typed projections and evidence links as the live inbox. Internal archive reconstruction jobs remain private; actual original collection runs are loaded with `import-jobs`. Public run errors are sanitized, and failed/partial refreshes retain earlier candidates. Job IDs are immutable. A source/provider failure never empties the archive or invents an occurrence.

The normal snapshot includes the newest 250 discovery articles, all reviewed developments and the sources those included records reference, plus the small non-discovery source catalog. `meta.discovery_total` and `meta.discovery_visible` state that boundary. Full-archive search, stable detail and JSON/CSV exports remain available through the API. Public static Pages does not imply a live database search service. The coordinator also preserves downloadable original discovery metadata outside the app's startup bundle.

`import-official-results --publish-official-results` is a narrow, explicit source-observation path. It accepts only 2026 House/Senate contest packets linked to official sources, positive candidate counts reconciling with the contest total, `reported_unofficial`, winner/basis null, `evidence_status=unreviewed`, `review_method=validated_official_adapter`, and no fabricated human review date. It cannot publish unrelated claims, declare winners, certify results, replace reviewed finality/dispute states, alter contest identity, or overwrite pending editorial work. Dated prior tallies remain immutable public revisions. Source reporting status is independent from editorial evidence status. A timezone-unknown source timestamp remains `result_as_of_raw`; no midnight or timezone is guessed.

## Scorecards and exports

Scorecards deterministically count distinct reviewed, count-eligible observations; documented active dates, named locations, and linked campaigns. A date range alone never establishes activity on every intervening day. Exact-day observations count that day; range observations contribute active days only through explicit `active_dates`. An uncertain range contributes an occurrence to a window only if it fits wholly inside that window, unless documented active dates place it there. Month/unknown-date observations, aggregate campaign narratives, excluded records, discovery articles, merged identities and retracted identities do not inflate occurrence counts.

The calendar month-to-date window compares with the same number of elapsed days in the previous calendar month, capped at that month's last day. Momentum is `insufficient_data` and the previous count is null without explicitly reviewed whole-country coverage of **both** windows. Partial sampled coverage cannot establish a country trend. There is no composite temperature number, ranking or article-volume proxy. Corrections, merges, retractions and campaign reassignment are recomputed from current public revisions.

Snapshots derive their dataset time from known public source/review/data/run times. If none are known, the actual immutable publication clock is used; an empty store uses null. No epoch timestamp is invented. The stable content hash excludes generated/calculated timestamp metadata. Reconstruction preserves genuine input dates rather than using the build/import clock. A live API and CLI snapshot from the same store use this identical projection.

`export-seed --output PATH` writes only public reviewed records, source metadata and coverage for Git review. It excludes unreviewed discovery/results, inherited unverified records, jobs, scorecards, private revisions and private reasons. Copying it into the publication inputs and releasing the static site are separate owner actions. Full JSON/CSV research exports retain published factual records and labeled inherited provenance; CSV neutralizes formula prefixes even after leading whitespace/control characters. JSON uses null for unknown counts/dates rather than zero.

## Backup, restore, and rollback

```sh
.venv/bin/python -m worldwar.cli backup --output work/backups/worldwar-private.json
.venv/bin/python -m worldwar.cli verify-restore --output work/restore-proof.json
WORLDWAR_DATABASE_URL=sqlite:///./work/restored.db .venv/bin/python -m worldwar.cli restore --input work/backups/worldwar-private.json
```

A backup includes the entire private database: drafts, reasons, all public/private revisions, evidence, references, jobs, candidates, provenance and migration registry. It contains no environment token but **must stay private**. Files are written atomically with mode 0600; snapshots use 0644. The backup records a canonical SHA-256 over all table content. SQLite is read inside an explicit transaction and PostgreSQL uses repeatable-read isolation.

Restore accepts only a fresh/empty destination, checks the format, schema, registry, checksum, row columns and typed revision payloads, restores in foreign-key order, validates constraints and resets the PostgreSQL revision sequence. It never drops a populated database. `verify-restore` creates a fresh SQLite destination and compares every restored table's canonical digest **and** the full public snapshot, so a superficially matching row count is insufficient. `validation/restore-proof.json` records a real roundtrip on the accepted dataset; test coverage separately proves private draft preservation and corruption/nonempty-target rejection.

For rollback, stop writers, preserve the current private backup, restore the chosen known-good backup into a new database, verify it, point `WORLDWAR_DATABASE_URL` at that destination and restart the matching code version. Retain the old database until acceptance. Static publication rollback uses the prior reviewed public artifact/release and does not require exposing a database backup.

## PostgreSQL and container operation

`WORLDWAR_DATABASE_URL=postgresql+psycopg://user:password@host:5432/worldwar` selects PostgreSQL; `postgresql://` and `postgres://` are normalized to psycopg. SQLite-specific transaction pragmas are not run on PostgreSQL. `Dockerfile` builds a nonroot API image. `compose.yaml` provides PostgreSQL 17, a persistent database volume, health checks and a loopback API binding, without committed credentials:

```sh
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
export WORLDWAR_EDITOR_TOKEN="$(openssl rand -hex 32)"
docker compose -f backend/compose.yaml up --build
```

The empty container database is a service foundation; import reviewed publication inputs through the CLI before expecting public records. Keep imports/reviewed snapshots separate from the database volume. Container and PostgreSQL runtime proof depend on host/CI availability; the acceptance report must distinguish the local SQLite proof from the PostgreSQL CI check rather than claim an unrun container deployment.

## Validation

```sh
.venv/bin/pytest -q -c backend/pytest.ini
WORLDWAR_DATABASE_URL=postgresql+psycopg://... PYTHONPATH=backend .venv/bin/python backend/tests/postgres_smoke.py --disposable-test-database
```

The smoke script requires an explicit disposable test database, runs the real migration, publishes a synthetic source and observation, checks private/public revision separation and a stale conflict, publishes a correction and proves a portable all-table restore. It appends synthetic fixtures and never deletes existing data. The main suite covers token boundaries, private leakage, source/typed validation, actual concurrent writes, immutable SQL history, duplicate IDs/URLs, seed atomicity, original legacy parity, source date semantics, discovery failures, bounded snapshot/full-archive access, export/formula handling, retraction/merge history, scorecard corrections/coverage/range uncertainty, official-source observations and recovery. These are engineering checks, not certification of worldwide factual coverage.

Implementation references: [SQLAlchemy version counters](https://docs.sqlalchemy.org/en/20/orm/versioning.html), [FastAPI timing-safe credential comparison](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/), [ISO country-code standard](https://www.iso.org/iso-3166-country-codes.html) and [UN geographic-code context](https://unstats.un.org/unsd/methodology/m49/).

For the protest acquisition source queue, run `python -m worldwar.cli ingest-source-candidates --input data/discovery/protest-candidates.json --domain protests`. This command creates only private source drafts and durable candidate/provenance rows. It creates no conflict development, protest occurrence, action or public source. Known canonical URLs add a domain-interest hint without a duplicate source. An editor must inspect the original source, correct the source type/metadata, publish that source and separately create/review/publish a dated occurrence. Original collection health is imported with `import-jobs`; internal inbox import jobs are private.

## Public retirement overlay and schema 2

Public snapshots include an additive `tombstones: [{kind, record}]` array. Normal domain/source arrays, search, maps and scorecards still contain only active published records. Tombstones use the public-safe record shape, omit raw legacy payloads and private reasons/history, retain the retired identity and `publication_status`, and carry `merged_into` for merged identities. `publication_changed_at` records the actual public retirement time when known. Static clients can resolve old stable links and retain withdrawn-source citation metadata through this array.

`export-seed` now also writes `publication_actions`. Each action has `kind`, `id`, `action` (`retract` or `merge`), optional `target_id`, optional known `published_at`, and an exported public-safe `record` tombstone. The public record is necessary for identities created by editors that have no legacy/archive baseline, and preserves the retired public summary if baseline inputs later change. It contains no private editorial revision or reason. A hand-authored ID-only action can retire an existing baseline identity; a missing identity requires the exported public tombstone payload. Unknown action dates remain null rather than using the build clock.

The seed importer validates actions but deliberately does not apply them during baseline creation. Apply the final overlay **after** legacy, reviewed seed, official-result, discovery and source-candidate imports, before serving or exporting:

```sh
python -m worldwar.cli apply-publication-actions --input data/publication/seed.json
python -m worldwar.cli snapshot --output web/public/data/research.json
```

The overlay is transactional and idempotent. It never publishes an imported tombstone as an active fact. Historical records still require typed data, eligible linked public source metadata and their explicit reviewed/legacy/discovery/official-observation evidence status. It preserves historical redirects such as A → B → C, rejects cycles, duplicate/conflicting actions and missing targets, and retains the merge target. Rebuilding from baseline inputs plus the exported overlay cannot resurrect retired legacy, discovery or editor-created records. Source retirement remains blocked while an active claim uses it; after dependent claims are retired, historical evidence links and source URLs remain available. A publisher's withdrawal can also be recorded as a source metadata correction without removing the pinned historical evidence.

Database migration 2 adds explicit optional source/observation/campaign/coverage provenance fields for later reviewed research. It preserves all existing immutable revisions and supplies only null/empty-list/false defaults to old projection rows. Existing version-1 private backups remain restorable into a fresh current database: their original revision payloads are preserved, then the new projection columns and migration registry are upgraded. A same-version backup/restore still compares every table exactly; an older-version restore necessarily records the new migration and columns. The committed large-store proof remains the historical version-1 proof described in `validation/README.md`; focused tests separately prove the version-2 upgrade, version-1 backup recovery and retirement publication roundtrip.

Published records also expose read-only `source_snapshots`, containing only the linked public source metadata captured for that exact claiming revision. Current source catalog corrections remain separate. Ordinary editor POST/PUT does not accept this derived field; editor detail returns editable record data and a separate authorized sources list. Reviewed seed import explicitly validates these public source snapshots and stores them on immutable evidence links, so exporting and rebuilding an unchanged claim preserves its original source URL/title/date even after the source catalog was corrected. Retirement preserves the original claiming revision's source pins instead of selecting the latest source revision. Public action records carry the same bounded snapshots; no private source draft or full revision history is exported. Migration 2 adds a nullable evidence snapshot column and database guards against evidence-link updates/deletes. Older version-1 rows continue to resolve their original immutable source revision when that column is null.
