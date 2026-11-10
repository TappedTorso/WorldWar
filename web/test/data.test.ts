import { describe, it, expect, vi } from "vitest";
import { date, filterItems, publishedItems, csvCell, exportCsv, exportPayload, fetchSnapshot, safeUrl, recordDate, researchTitle, cardDateLabel, findPublicRecord, recordSources } from "../src/data";
import { parseRoute, itemRoute, routeTo } from "../src/routes";
import { snapshot, actor, base, contest } from "./fixtures";
describe("stable routes and scope", () => {
  it("preserves legacy actor identifiers", () => expect(parseRoute("#node=test-actor")).toMatchObject({ section: "conflicts", kind: "actors", id: "test-actor" }));
  it("roundtrips encoded identifiers and filter state", () => { const r = parseRoute(routeTo("protests", new URLSearchParams({ q: "a & b", geo: "FR", from: "2026-09-01" }), "occurrences", "with / spaces")); expect(r.id).toBe("with / spaces"); expect(r.params.get("q")).toBe("a & b"); expect(r.params.get("geo")).toBe("FR"); expect(r.params.get("from")).toBe("2026-09-01"); });
  it("routes typed records without guessing domain", () => expect(itemRoute({ kind: "actors", domain: "conflicts", record: actor })).toBe("#/conflicts/actors/test-actor"));
});
describe("research semantics", () => {
  it("keeps month-only and reported intervals in overlapping date filters without inventing an exact day", () => {
    const month = { kind: "occurrences" as const, domain: "protests" as const, record: { ...base, occurred_start: "2026-09-01", occurred_end: "2026-09-30", date_precision: "month" } };
    expect(filterItems([month], new URLSearchParams({ from: "2026-09-15", to: "2026-09-16" }))).toHaveLength(1);
    expect(filterItems([month], new URLSearchParams({ from: "2026-10-01" }))).toHaveLength(0);
    const span = { ...month, record: { ...month.record, occurred_start: "2026-09-10", occurred_end: "2026-09-20", date_precision: "range" } };
    expect(filterItems([span], new URLSearchParams({ from: "2026-09-15" }))).toHaveLength(1);
  });
  it("does not plot or date-filter an explicitly unknown date from a stored boundary", () => {
    const unknown = { ...base, occurred_start: "2026-09-01", date_precision: "unknown" };
    expect(recordDate(unknown)).toBeNull();
    expect(filterItems([{ kind: "occurrences", domain: "protests", record: unknown }], new URLSearchParams({ from: "2026-09-01" }))).toHaveLength(0);
  });
  it("preserves month and year date precision", () => { expect(date("2026-09-01", "month")).toBe("Sep 2026"); expect(date("2026-09")).toBe("Sep 2026"); expect(date("2026")).toBe("2026"); });
  it("keeps date-only values on the intended date", () => expect(date("2026-11-03")).toBe("Nov 3, 2026"));
  it("never substitutes review time for occurrence time", () => expect(recordDate({ ...base, reviewed_at: "2026-11-10T00:00:00Z" })).toBeNull());
  it("excludes private drafts and retains inherited status", () => { const data = { ...snapshot, actors: [actor, { ...actor, id: "draft", publication_status: "draft" as const }] }; expect(publishedItems(data).map(i => i.record.id)).not.toContain("draft"); expect(publishedItems(data)[0].record.evidence_status).toBe("legacy_unverified"); });
  it("excludes unknown occurrence dates from bounded date filters", () => expect(filterItems(publishedItems(snapshot), new URLSearchParams({ from: "2026-09-01" }))).toHaveLength(0));
  it("combines typed, geographic, evidence and text filters", () => { const r = filterItems(publishedItems(snapshot), new URLSearchParams({ geo: "FR", status: "legacy_unverified", q: "test actor" })); expect(r).toHaveLength(1); expect(r[0].kind).toBe("actors"); });
  it("rejects unsafe and credential-bearing source URLs", () => { expect(safeUrl("javascript:alert(1)")).toBeUndefined(); expect(safeUrl("https://user:secret@example.org")).toBeUndefined(); expect(safeUrl("https://example.org/\nsecret")).toBeUndefined(); expect(safeUrl("https://example.org")).toBe("https://example.org/"); });
  it("surfaces unsupported snapshots and fetch failures", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...snapshot, schema_version: "2.0" }) })); await expect(fetchSnapshot()).rejects.toThrow("schema"); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 })); await expect(fetchSnapshot()).rejects.toThrow("503"); });
});
describe("rights-aware exports", () => {
  it("includes linked source metadata only for exported records", () => { const p = exportPayload([{ kind: "actors", domain: "conflicts", record: actor }], { ...snapshot, sources: [...snapshot.sources, { ...snapshot.sources[0], id: "unlinked" }] }); expect(p.sources.map(s => s.id)).toEqual(["test-source"]); expect(p.records[0].kind).toBe("actors"); });
  it("neutralizes formulas and preserves CSV quoting", () => { expect(csvCell(" =SUM(A1)")).toBe('"\' =SUM(A1)"'); expect(csvCell('a,"b"')).toBe('"a,""b"""'); expect(exportCsv([{ kind: "actors", domain: "conflicts", record: actor }])).toContain("test-source"); });
});
it("distinguishes relationship endpoints while retaining the author title", () => { const record = { ...base, title: "Support Policy", from_actor_id: actor.id, to_actor_id: "other-actor" }; const data = { ...snapshot, actors: [actor, { ...actor, id: "other-actor", name: "Second test actor" }] }; expect(researchTitle({ kind: "relationships", domain: "conflicts", record }, data)).toBe("Test actor → Second test actor · Support Policy"); });
it("retains nationwide actions in state scope unless explicitly hidden", () => { const national = { kind: "election_actions" as const, domain: "elections" as const, record: { ...base, id: "national-test-action", geography_scope: "national", state_code: null } }; expect(filterItems([national], new URLSearchParams({ geo: "CA" }))).toHaveLength(1); expect(filterItems([national], new URLSearchParams({ geo: "CA", national: "hide" }))).toHaveLength(0); });
it("labels contest dates without turning election day into result time", () => { const item = { kind: "contests" as const, domain: "elections" as const, record: contest }; expect(cardDateLabel(item)).toBe("Election: Nov 3, 2026"); expect(recordDate(contest)).toBeNull(); expect(cardDateLabel({ ...item, record: { ...contest, result_as_of_raw: "November 9, 8:15 p.m.; timezone not stated" } })).toBe("Source as-of: November 9, 8:15 p.m.; timezone not stated"); expect(cardDateLabel({ ...item, record: { ...contest, result_as_of: "2026-11-09T20:15:00Z" } })).toBe("Reported as of Nov 9, 2026"); });
it("resolves static tombstones only in stable detail, not active results", () => { const retired = { ...actor, id: "retired-test-actor", publication_status: "merged" as const, merged_into: actor.id }; const data = { ...snapshot, tombstones: [{ kind: "actors", record: retired }] }; expect(findPublicRecord(data, "conflicts", "actors", retired.id)?.record).toEqual(retired); expect(findPublicRecord(data, "elections", "actors", retired.id)).toBeUndefined(); expect(publishedItems(data).some(i => i.record.id === retired.id)).toBe(false); });
it("prefers source pins by ID while preserving the current source register", () => { const pinned = { ...snapshot.sources[0], title: "Original evidence", url: "https://example.org/original" }; const current = { ...pinned, title: "Corrected catalog", url: "https://example.org/corrected" }; const data = { ...snapshot, sources: [current] }; expect(recordSources(data, { ...actor, source_snapshots: [pinned] })[0].url).toBe(pinned.url); expect(recordSources(data, actor)[0].url).toBe(current.url); expect(data.sources[0].url).toBe(current.url); });
