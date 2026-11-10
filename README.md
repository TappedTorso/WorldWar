# WorldWar research observatory

One research application for conflict systems, significant collective action and the 2026 U.S. federal election cycle. The public site is at [tappedtorso.github.io/WorldWar](https://tappedtorso.github.io/WorldWar/). It combines geographic exploration, accessible record lists, chronology, source evidence, coverage, search and research exports.

The November 2026 rebuild preserves the original 82 actor identities, 75 relationships, editorial classifications and citation text. Those inherited assessments retain their original verification status. Source-reviewed conflict developments and protest occurrences are separate from unreviewed news discovery. Elections covers 435 voting House seats and 35 scheduled Senate contests; after voting, its emphasis is reported results, certification, recounts, litigation and documented institutional actions. A registered contest is not an assessed result, an unofficial tally is not a race call, and no result is represented as zero merely because it has not been collected.

## Start the public application locally

Requirements: Node 22.12 or later and Python 3.12 or later.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci
npm --prefix web ci
PATH="$PWD/.venv/bin:$PATH" npm run build:data
npm run dev
```

Open the local URL printed by Vite. This mode uses the deliberate public snapshot and does not offer simulated editorial writes. `PATH="$PWD/.venv/bin:$PATH" npm run build` creates `web/dist`; `npm run preview` serves that production artifact. GitHub Pages sets `VITE_BASE_PATH=/WorldWar/`.

## Run the full editorial workspace

The API is a real FastAPI/SQLAlchemy service with SQLite for a single local owner and PostgreSQL for service deployments. It stores typed records, immutable revisions, evidence links, source candidates, publication state, coverage and run health. The public revision remains stable while an editor prepares a correction. All writes require authentication, a reason and a current revision. Source-backed publication, merge and retraction are transactional.

From the repository root, after installing the dependencies above:

```sh
mkdir -p runtime
export PYTHONPATH=backend
export WORLDWAR_DATABASE_URL=sqlite:///./runtime/research.db
export WORLDWAR_SEED_DIRECTORY="$PWD/data"
.venv/bin/python scripts/bootstrap_store.py
export WORLDWAR_EDITOR_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'Local editor token: %s\n' "$WORLDWAR_EDITOR_TOKEN"
.venv/bin/uvicorn worldwar.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```sh
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

Open Editorial and enter the local token. It remains in browser memory and clears when leaving the editor. Keep the database and private backups outside Git. Bootstrap initializes an empty store only; it never overwrites an existing owner's edits. API documentation is at `http://127.0.0.1:8000/docs`. The complete command, data, recovery and migration reference is in [backend/README.md](backend/README.md).

For a complete containerized workspace with PostgreSQL, the API and same-origin web proxy:

```sh
export WORLDWAR_DATABASE_PASSWORD="$(openssl rand -hex 32)"
export WORLDWAR_EDITOR_TOKEN="$(openssl rand -hex 32)"
docker compose up --build -d
```

Open `http://127.0.0.1:8080`. Only the web proxy binds a host port, on loopback. Database storage persists in a named volume. `docker compose down` stops services without deleting the volume. The separate `backend/compose.yaml` is a minimal API-only development alternative. An internet-facing service requires an operator-managed HTTPS endpoint and exact allowed origins; the public Pages site itself does not host a database or editor API.

## Research and publication

- Conflicts preserves inherited editorial content and adds dated, source-backed chronology. Automatic article tagging is discovery metadata, not evidence that an actor participated in an event.
- Protests begins September 1, 2026. Inclusion depends on documented action and contextual significance, with dates, location precision, demands, attribution, campaign links and a coverage ledger. Samples do not establish exhaustive worldwide observation.
- Elections separates contest identity, source reporting, winner basis and editorial review. The official Delaware adapter retains dated unofficial observations without declaring winners. Other collected results remain independently sourced. Unassessed races remain explicit.
- House geometry uses Census TIGER/Line 2026 CD120 for 49 states and the operative 2025 CD119 plan for Missouri, whose 2026 Census GIS is documented as stale. All 435 contest IDs and plan vintages must match before a shape is used. Geometry is simplified for national display, not address lookup or legal adjudication. [Provenance](web/public/geometry/districts-attribution.json) includes source URLs, retrieval times and hashes.
- Activity scorecards count documented, deduplicated occurrences and active dates. They return insufficient comparison data when coverage cannot support a trend. Political context remains dated and separate; there is no composite political temperature or inferred causal connection.

Reviewed source packets are versioned in `data/publication/seed.json`. Official adapter observations are isolated in `data/publication/official-results.json`. Discovery metadata and run history live in `data/discovery/`. `build_public.py` always creates a fresh temporary database from these explicit publication inputs; it never reads a private runtime database. Only `web/dist` is uploaded to Pages. The startup snapshot includes the newest 250 discovery articles; the full archive is separately downloadable, and the configured API searches/exports the full published database.

The schedules collect conflict discovery every six hours, Delaware official results twice daily, and protest article candidates daily. Protest candidates are private source-inbox material when imported into the service; they never automatically become occurrences. Failed collection retains earlier data and exposes run health. The historical protest window ledger records failed, capped and unattempted windows. The old LLM proposal workflow is manual and defaults to a dry run.

After reviewing and publishing local editorial work, export a reviewed seed with `python -m worldwar.cli export-seed --output PATH`, inspect the diff against the existing publication packet, commit the accepted changes and release through CI. Do not copy a private backup into public inputs. Updating a local database and deploying Pages are separate operations.

Exported seeds preserve source metadata at each claim's publication revision and carry explicit merge/retraction actions. A fresh public build applies those actions after all baseline imports, keeping retired stable URLs without restoring their records to active lists. The South Africa campaign reconciliation in this edition exercises that path: two overlapping source contexts become one canonical campaign with a merged alias, while occurrence counts remain unchanged.

## Validate and recover

```sh
PATH="$PWD/.venv/bin:$PATH" npm test
PATH="$PWD/.venv/bin:$PATH" npm run build
npm run check:public
```

CI also exercises real PostgreSQL transactions and a disposable complete container stack. The deployment check creates synthetic fixtures only in the explicitly disposable CI database. It checks public/private separation, authenticated publication, same-origin routing and the real registry. Tests do not establish factual completeness.

Create a private, mode-0600 all-table backup and prove restoration before changing a persistent deployment:

```sh
PYTHONPATH=backend .venv/bin/python -m worldwar.cli backup --output runtime/backups/research-private.json
PYTHONPATH=backend .venv/bin/python -m worldwar.cli verify-restore --output runtime/restore-proof.json
```

The commands use `WORLDWAR_DATABASE_URL`; set it to the intended store. Restore only into a fresh destination, verify the full table digest and public snapshot, then switch the service to the restored database. Keep the previous database until acceptance. Static rollback redeploys a prior verified release artifact. [Implementation decisions](docs/IMPLEMENTATION.md), [data contract](docs/contracts/snapshot-v1.md), and the preserved [October proposal](docs/2026-10-25-proposal.md) document scope and design. Research ledgers in `docs/research/` state provenance and remaining coverage limits.
