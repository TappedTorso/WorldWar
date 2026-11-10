# WorldWar research application

React + TypeScript + Vite public research atlas and authenticated editorial client. Runtime dependencies, map geometry, styles and system fonts are local. No map provider, CDN or analytics request is required.

## Run and verify

From the repository root:

```sh
npm ci --prefix web
npm run dev --prefix web
npm test --prefix web
npm run build --prefix web
npm run preview --prefix web
```

The public edition loads the generated contract-v1 snapshot at `web/public/data/research.json`. Synthetic fixtures stay under `web/test/` and never substitute for production records. Failed loads retain their failure state.

Configure `VITE_API_BASE=http://127.0.0.1:8000` at build/dev startup to use the persistent API. This is the service origin without `/api/v1`, not a credential. Never place the owner token in a Vite environment variable. Editors enter the runtime token, which remains only in React memory and clears on locking or leaving the workspace. Static builds without an API explicitly disable private reads and editorial writes.

Relative asset URLs support a GitHub Pages subdirectory. `VITE_BASE_PATH=/WorldWar/` sets an explicit base. Hash routes preserve browser history and legacy `#node=ID` actor links.

## Interaction and evidence semantics

Desktop presents coordinated map/network geography, accessible result lists, chronology and selected source evidence; a reading view expands long records. Narrow screens use deliberate map/results/detail modes and expandable filters. Selecting a mobile record moves focus to its detail heading. Search retains an explicit accessible name even when its text is visually hidden.

URL parameters retain text, geography, evidence/reporting state, time interval, record/action type, actor, layer, sort, display mode and reading state. Unknown occurrence dates do not pass bounded occurrence-date filters. Election date is labeled separately and never becomes a result-as-of date. Unresolved raw source timestamps remain text without invented timezones.

Conflicts default to actors, with separate relationships, chronology and discovered reporting. Relationship display includes endpoints and preserves authored classifications. Inherited assessments remain visibly unverified. Discovery time never becomes occurrence time.

Protests show country context for observations and campaigns; points require coordinates. Aggregate campaign reports are not split into invented daily occurrences. Counts and momentum retain coverage and method qualifications, never a global composite score.

House maps join official locally bundled 2026 display geometry only when contest ID, state, district and verified plan vintage agree. Unavailable or mismatched plans retain state fallback. The Census Missouri exception is explicit. Canonical RFC 7946 coordinates remain unchanged; D3 winding normalization occurs on an in-memory render copy. Projected paths are cached. Senate remains statewide. Geometry is simplified display context, not address assignment or legal boundary adjudication; see `public/geometry/README.txt` and `districts-attribution.json` for sources, licenses, hashes and limitations.

Election map colors encode named reporting states, not an inferred leader/winner. Not assessed, not reported, no included record, unofficial, provider called, certified, recount and contested remain distinct. Nationwide actions remain in local scope unless explicitly hidden and are not placed in Washington.

Configured-API global search queries the full public archive beyond the bounded static snapshot. Static search identifies snapshot scope. CSV/JSON scope downloads contain the same visible published records; formula prefixes are neutralized in CSV. The Data page separately exposes full public archive JSON when an API is configured. Private drafts, credentials, private revision reasons and source bodies never enter public builds.

Public record `source_snapshots` preserves the metadata attached to its published revision. Detail evidence prefers these by linked ID, then the current source catalog, then retired-source tombstones for retired claims. Current withdrawal is labeled without overwriting pinned URLs/titles/dates. API-returned pinned sources remain authoritative. Source snapshots are read-only and stripped from editorial POST/PUT. The source register shows the current catalog only.

Snapshot tombstones resolve stable and legacy retired detail links and merge targets without entering normal maps, lists, counts or search. Public history is separate from private revision reasons. Authenticated editor forms create typed candidates, attach sources and require reasons. Publication is explicit and blocked while form edits are unsaved. Retraction/merge preserve public history. Authentication, validation, unavailable-service and revision-conflict errors remain actual failures rather than simulated saves. Complex arrays remain editable through explicit structured JSON.

## Test coverage

Vitest and Testing Library cover stable/legacy routes, persistent filters, date precision, publication visibility, source URL safety, CSV injection defense, source-scoped export, failed loads, unknown election outcomes, static editor unavailability, runtime auth and credential non-persistence, strict source forms, draft writes, review attestation, stale revisions, read-only source pins, archive search, public tombstones, retired citations and active/retired source-version preservation. Geometry checks cover actual bundled identity, 435 seats/50 states/Missouri exception, plan mismatch rejection and finite spherical rendering without canonical mutation. Real browser and backend end-to-end checks are separate integration evidence.

## Recovery note

The local release workspace was restored after iCloud offloaded the earlier checkout. Missing configuration, README and test files were reconstructed from the task's known source/tool trace; the dependency lock was regenerated from the preserved package manifest and registry. Existing recovered source files were preserved except the explicit source-pin changes above. World/state outlines and licenses were copied byte-for-byte from the recovered public build; canonical district geometry and provenance were preserved.
