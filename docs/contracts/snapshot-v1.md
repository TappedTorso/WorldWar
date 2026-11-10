# Public snapshot and API contract v1

Contract owner: coordinator. The executable strict schemas are in `backend/worldwar/schemas.py`; new fields must be added there deliberately and checked across import, API, export and UI. All JSON uses snake_case. Empty arrays are valid; never substitute fabricated records. Timestamp fields require timezone-aware ISO 8601 values. Day-only dates and source-provided times without a timezone remain in their explicit date/raw fields; unknown dates are null, not retrieval time. IDs are stable strings. Sources and coverage have separate schemas rather than inheriting every domain field below.

## Snapshot

`GET /api/v1/snapshot` and `public/data/research.json` return the same shape:

```json
{
  "schema_version": "1.0",
  "meta": {"generated_at":"2026-11-10T00:00:00Z", "data_version":"sha256-prefix", "legacy_reviewed_at":"2026-03-15T00:00:00Z", "coverage_summary":"Reviewed observations with explicit coverage gaps", "publication_mode":"reviewed_snapshot"},
  "actors": [], "relationships": [], "developments": [],
  "occurrences": [], "campaigns": [], "connections": [],
  "contests": [], "election_actions": [], "political_context": [],
  "sources": [], "coverage": [], "jobs": [], "scorecards": [], "tombstones": []
}
```

## Shared public fields

Domain records carry `id`, `title` (actors also `name`), `summary`, `source_ids: string[]`, `evidence_status: reviewed | legacy_unverified | unreviewed`, `publication_status: published | retracted | merged`, `revision: number`, `reviewed_at: datetime|null`, `updated_at: datetime|null`. Only published records enter normal result lists. A redirect/tombstone is permitted for merged/retracted detail history. Legacy records may expose `legacy_citation_text: string[]`, `legacy_confidence: string|null`, `legacy_updated_at: string|null` and `legacy_payload` in research exports, never recast as current verification.

`meta.generated_at` is a deterministic publication watermark: the latest public record or public collection-run timestamp in the edition, not the wall-clock time of rebuilding unchanged inputs and not renewed evidence review. The data-version hash changes when public content changes.

Public claims may carry read-only `source_snapshots`: linked source metadata pinned to the claiming publication revision. Consumers resolve evidence from those pins before the current catalog. A later source correction does not silently rewrite the earlier claim's evidence. Current withdrawal state remains separately visible. Editor writes do not accept these derived pins; trusted seed import preserves exported pins after strict source/link validation.

`tombstones` contains `{kind, record}` for merged or retracted public identities. These records remain reachable by stable detail URLs and are excluded from active lists and activity calculations. A merged record identifies `merged_into`. Public tombstones and pins contain no private correction text, editorial reasons or raw source bodies.

Reviewed publication packets can include `publication_actions: [{kind, id, action, target_id?, published_at?, record?}]`. Actions are explicit merge/retraction instructions, applied after legacy, reviewed and discovery baseline imports. Exported public tombstone payloads allow retired editor-created records to survive rebuilding even when absent from the baseline. Private revision history is never a publication packet. The CLI validates merge chains, rejects cycles, and applies the overlay transactionally and idempotently.

Source: `id, title, url, publisher, source_type` (official, primary, reporting, legacy_reference, discovery), `published_at|null, retrieved_at|null, rights, note`. Dates may instead use `published_date` and `retrieval_date`, with explicit `publication_precision` and `retrieval_precision`. URLs must be http/https. Legacy references without URL use null and are not clickable evidence. Optional source-update dates/raw times, evidence locators, access notes, language and content hashes preserve their actual precision. No full copyrighted source text.

## Typed domain fields

- **actors:** `name, actor_type, country_code|null, longitude, latitude, theaters:string[], category, legacy_citation_text`.
- **relationships:** `from_actor_id, to_actor_id, relationship_type, category, theaters:string[], valid_from|null, valid_to|null`.
- **developments:** conflict chronology, `actor_ids:string[], occurred_start|null, occurred_end|null, date_precision, development_type` (reported_development, assessment_revision, discovery_article), `url|null`. Discovery time is `discovered_at`; publication time stays null unless known. Discovery articles must visibly remain unreviewed reporting.
- **occurrences:** `country_code, country, place_name, longitude|null, latitude|null, location_precision` (point, city, region, country, unknown), `occurred_start, occurred_end|null, date_precision` (day, range, month, unknown), `action_type, demands:string[], targets:string[], campaign_ids:string[], inclusion_rationale, confidence_note`. Optional `participants`, `response`, `outcome` must be attributed. Month precision means one calendar month; a cross-month interval must use range. The canonical month bounds determine filtering/count windows, without inventing active dates.
- **campaigns:** `country_codes:string[], started_at|null, ended_at|null, demands:string[], targets:string[], occurrence_ids:string[]`.
- **connections:** `from_id, to_id, connection_type, evidence_note`; only documented relationships are published, no temporal/similarity inference.
- **contests:** `office` (house, senate), `cycle:2026, state_code, jurisdiction, district|null, geography_version, boundary_status, status` (not_assessed, not_reported, reported_unofficial, provider_called, certified, recount, contested), `result_as_of|null, election_date, candidates:[{name,party,votes:null|number,percentage:null|number}], winner|null, winner_basis|null, total_votes|null, reporting_note, longitude|null, latitude|null`. Winner is null unless its distinct basis is supported. No contest/no report/no assessment are not zero results.
- **election_actions:** `action_type, actor, jurisdiction, state_code|null, geography_scope` (national, state, district), `occurred_start, occurred_end|null, date_precision, procedural_status, claim_status` (documented_action, attributed_allegation, analysis, court_finding), `effect_claim|null, effect_evidence|null, intent_claim|null, intent_evidence|null, related_contest_ids:string[]`.
- **political_context:** `domain, jurisdiction, country_code|null, state_code|null, as_of, context_type, related_ids:string[]`; dated factual institutional context, no inferred ideology.
- **coverage:** `id, domain` (conflicts, protests, elections), `geography, country_code|null, state_code|null, period_start, period_end, status` (reviewed, partial, not_assessed, unavailable), `source_ids:string[], note, reviewed_at|null`. Reviewed means the described bounded observation scope, never a census without evidence.
- **jobs:** public-safe `id, adapter, domain, started_at, completed_at|null, status` (ok, partial, error), `fetched_count, accepted_count, error|null`. Sanitize URLs and errors; no secrets.
- **scorecards:** `id, geography, country_code, period_start, period_end, occurrence_count, active_days, location_count, campaign_count, comparison_start, comparison_end, previous_occurrence_count|null, momentum` (insufficient_data, increased, decreased, unchanged), `coverage_status, method_version, calculated_at, input_ids:string[], note`. Distinct occurrences/active dates, not articles. Momentum unavailable absent comparable complete coverage. Numeric components describe documented observations only.

## API and editorial contract

- `GET /api/v1/health` returns status/schema.
- `GET /api/v1/search?q=...&domain=...` returns `items:[{id,domain,kind,title,summary,route}]`.
- `GET /api/v1/records/{kind}/{id}` returns record and referenced sources/revision history; published access only. Kinds are snapshot array names.
- `GET /api/v1/export?format=json|csv&kind=...` provides published records; CSV neutralizes spreadsheet formulas.
- `GET /api/v1/methodology` returns transparent methods/coverage notes.
- Editor uses `Authorization: Bearer <WORLDWAR_EDITOR_TOKEN>`, kept only in browser memory. Missing configured token disables writes and private reads. No token is committed to the repository or included in a public build. The local owner launcher stores its generated key only in the separate private runtime directory with mode 0600.
- `GET /api/v1/editor/records?status=draft&kind=occurrences&q=&limit=50&offset=0` returns `{items,total,limit,offset,has_more}` for current private/editor revisions. `kind` is optional, `q` is literal case-insensitive stable-ID/title/summary search, and ordering is kind then ID. Default limit is100, maximum200; the UI requests50. `GET /api/v1/editor/records/{kind}/{id}` reads full editor version. `POST /api/v1/editor/records/{kind}` creates a draft from `{record,reason}`. `PUT /api/v1/editor/records/{kind}/{id}` updates from `{record,expected_revision,reason}`. `POST .../{id}/publish`, `/retract` accept `{expected_revision,reason}`. `POST .../{id}/merge` accepts `{target_id,expected_revision,reason}`. Return updated record; stale revision returns 409; invalid publication 422; unauthenticated 401/503.
- All changes are transactional revisions with reasons. Publication requires a valid typed record and linked eligible sources, except explicit legacy-import workflow preserving inherited status. Draft content cannot replace published revision until publication.
- Adapter CLI ingestion, migration/seed, snapshot/export, backup/restore commands are owned/documented by backend worker. Parent supplies reviewed seed JSON matching these arrays. Do not auto-publish arbitrary discovered content.

## UI data acquisition and routes

Frontend attempts configured `VITE_API_BASE` when present; otherwise loads `${BASE_URL}data/research.json`. Editor must identify missing API as unavailable, never simulate a saved write. Root module API is `fetchSnapshot(): Promise<Snapshot>`; contracts/types remain in `web/src/types.ts` (frontend owner).

Hash routes: `#/overview`, `#/conflicts`, `#/protests`, `#/elections`, `#/data`, `#/editor`, and `#/{domain}/{kind}/{id}`. Query/filter state is URL-encoded and survives back/forward. Preserve legacy `#node=ID` actor deep links. Map/list/timeline selection must coordinate; accessible list is always available.
