import type {
  BaseRecord,
  Domain,
  RecordKind,
  ResearchItem,
  Snapshot,
  Source,
} from "./types";
import { recordKinds } from "./types";
export const apiBase =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "";
export async function fetchSnapshot(): Promise<Snapshot> {
  const response = await fetch(
    apiBase
      ? `${apiBase}/api/v1/snapshot`
      : `${import.meta.env.BASE_URL}data/research.json`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok)
    throw new Error(
      `Research snapshot could not be loaded (HTTP ${response.status}).`,
    );
  const data = await response.json();
  if (
    data.schema_version !== "1.0" ||
    !data.meta ||
    recordKinds.some((k) => !Array.isArray(data[k])) ||
    !Array.isArray(data.sources) ||
    !Array.isArray(data.coverage) ||
    !Array.isArray(data.jobs) ||
    !Array.isArray(data.scorecards) ||
    (data.tombstones !== undefined && !Array.isArray(data.tombstones))
  )
    throw new Error(
      "This snapshot does not match the supported research schema (1.0).",
    );
  return data;
}
export const kindDomain: Record<RecordKind, Domain> = {
  actors: "conflicts",
  relationships: "conflicts",
  developments: "conflicts",
  occurrences: "protests",
  campaigns: "protests",
  connections: "protests",
  contests: "elections",
  election_actions: "elections",
  political_context: "elections",
};
export function allItems(data: Snapshot): ResearchItem[] {
  return recordKinds.flatMap((kind) =>
    data[kind].map((record) => ({
      kind,
      domain:
        kind === "political_context"
          ? (record.domain as Domain) || "elections"
          : kindDomain[kind],
      record,
    })),
  );
}
export function publishedItems(data: Snapshot) {
  return allItems(data).filter(
    (i) => i.record.publication_status === "published",
  );
}
export function title(record: BaseRecord) {
  return String(record.name || record.title || record.id);
}
export function pretty(value: unknown): string {
  return String(value ?? "Not recorded").replaceAll("_", " ");
}
export function date(value: unknown, precision?: unknown) {
  if (!value) return "Date unknown";
  if (precision === "unknown") return "Date unknown";
  if (/^\d{4}$/.test(String(value))) return String(value);
  const monthOnly =
    precision === "month" || /^\d{4}-\d{2}$/.test(String(value));
  const d = new Date(String(value));
  return Number.isNaN(d.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("en", {
        year: "numeric",
        month: "short",
        ...(monthOnly ? {} : { day: "numeric" as const }),
        timeZone: "UTC",
      }).format(d);
}
export function recordDate(record: BaseRecord): string | null {
  return (record.occurred_start ||
    record.started_at ||
    record.result_as_of ||
    record.as_of ||
    record.valid_from ||
    null) as string | null;
}
export function filterItems(
  items: ResearchItem[],
  params: URLSearchParams,
  data?: Snapshot,
): ResearchItem[] {
  const q = (params.get("q") || "").trim().toLowerCase(),
    geo = params.get("geo") || "",
    kind = params.get("kind") || "",
    status = params.get("status") || "",
    from = params.get("from") || "",
    to = params.get("to") || "",
    type = params.get("type") || "",
    actor = params.get("actor") || "";
  return items.filter(({ record: r, kind: k }) => {
    const d = recordDate(r);
    const countries = Array.isArray(r.country_codes) ? r.country_codes : [];
    return (
      (!q ||
        [
          researchTitle({ record: r, kind: k, domain: kindDomain[k] }, data),
          r.summary,
          r.id,
          r.country,
          r.place_name,
          r.actor,
          r.category,
          ...(Array.isArray(r.theaters) ? r.theaters : []),
        ]
          .join(" ")
          .toLowerCase()
          .includes(q)) &&
      (!kind || kind === k) &&
      (!status || r.evidence_status === status || r.status === status) &&
      (!geo ||
        r.state_code === geo ||
        r.country_code === geo ||
        countries.includes(geo) ||
        r.jurisdiction === geo ||
        (k === "election_actions" &&
          r.geography_scope === "national" &&
          params.get("national") !== "hide")) &&
      (!type ||
        [
          r.action_type,
          r.development_type,
          r.relationship_type,
          r.office,
          r.actor_type,
        ].includes(type)) &&
      (!actor ||
        String(r.actor || "")
          .toLowerCase()
          .includes(actor.toLowerCase())) &&
      (!from || (!!d && d.slice(0, 10) >= from)) &&
      (!to || (!!d && d.slice(0, 10) <= to))
    );
  });
}
export function safeUrl(url: string | null | undefined): string | undefined {
  try {
    const u = new URL(url || "");
    return ["https:", "http:"].includes(u.protocol) &&
      !u.username &&
      !u.password &&
      !/[\x00-\x1F]/.test(url || "")
      ? u.href
      : undefined;
  } catch {
    return undefined;
  }
}
// Public payloads contain factual structured summaries and metadata; source bodies and private notes never enter exports.
export function exportPayload(items: ResearchItem[], data: Snapshot) {
  const ids = new Set(items.flatMap((i) => i.record.source_ids || []));
  return {
    schema_version: data.schema_version,
    meta: data.meta,
    scope:
      "Filtered published records; original factual summaries and linked source metadata only.",
    records: items.map(({ kind, domain, record }) => ({
      kind,
      domain,
      ...record,
    })),
    sources: data.sources.filter((s) => ids.has(s.id)),
  };
}
export function csvCell(value: unknown) {
  let s =
    typeof value === "object" ? JSON.stringify(value) : String(value ?? "");
  if (/^[\s]*[=+@\-]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
export function exportCsv(items: ResearchItem[]) {
  const fields = [
    "kind",
    "domain",
    "id",
    "title",
    "summary",
    "evidence_status",
    "revision",
    "reviewed_at",
    "source_ids",
  ];
  return [
    fields.join(","),
    ...items.map((i) =>
      [
        i.kind,
        i.domain,
        i.record.id,
        title(i.record),
        i.record.summary,
        i.record.evidence_status,
        i.record.revision,
        i.record.reviewed_at,
        i.record.source_ids,
      ]
        .map(csvCell)
        .join(","),
    ),
  ].join("\r\n");
}
export function downloadExport(
  format: "csv" | "json",
  items: ResearchItem[],
  data: Snapshot,
) {
  const text =
    format === "csv"
      ? exportCsv(items)
      : JSON.stringify(exportPayload(items, data), null, 2);
  const url = URL.createObjectURL(
    new Blob([text], {
      type: format === "csv" ? "text/csv;charset=utf-8" : "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `worldwar-${data.meta.data_version}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function researchTitle(item: ResearchItem, data?: Snapshot | null) {
  if (item.kind !== "relationships") return title(item.record);
  const r = item.record;
  const from = data?.actors.find((a) => a.id === r.from_actor_id),
    to = data?.actors.find((a) => a.id === r.to_actor_id);
  const fromName = from ? title(from) : String(r.from_actor_id),
    toName = to ? title(to) : String(r.to_actor_id);
  const original = title(r);
  return original.includes(fromName) && original.includes(toName)
    ? original
    : `${fromName} → ${toName} · ${original}`;
}

export function cardDateLabel(item: ResearchItem): string {
  const r = item.record;
  if (item.kind === "contests") {
    if (r.result_as_of) return `Reported as of ${date(r.result_as_of)}`;
    if (r.result_as_of_raw) return `Source as-of: ${String(r.result_as_of_raw)}`;
    return r.election_date ? `Election: ${date(r.election_date)}` : "Election date not recorded";
  }
  const occurred = recordDate(r);
  return occurred ? date(occurred, r.date_precision) : item.kind === "actors" ? "Inherited assessment" : "Date not recorded";
}

// Tombstones are available only to stable-detail lookup. Normal lists, search,
// maps, metrics and scoped exports continue to use the active domain arrays.
export function findPublicRecord(data: Snapshot, domain: Domain, kind: string, id: string): ResearchItem | undefined {
  const active = allItems(data).find(i => i.kind === kind && i.record.id === id && i.domain === domain);
  if (active) return active;
  const retired = data.tombstones?.find(t => t.kind === kind && t.record.id === id && recordKinds.includes(t.kind as RecordKind) && ["retracted", "merged"].includes(t.record.publication_status || ""));
  if (!retired) return undefined;
  const record = retired.record as BaseRecord;
  const recordDomain = retired.kind === "political_context" ? (record.domain as Domain) || "elections" : kindDomain[retired.kind as RecordKind];
  return recordDomain === domain ? { kind: retired.kind as RecordKind, domain, record } : undefined;
}

// Published claim pins take precedence over later catalog corrections. Current
// source withdrawal is annotated without modifying the historical citation URL.
export function recordSources(data: Snapshot, record: BaseRecord): Source[] {
  const retiredClaim = ["retracted", "merged"].includes(record.publication_status);
  return (record.source_ids || []).flatMap(id => {
    const pinned = record.source_snapshots?.find(source => source.id === id);
    const active = data.sources.find(source => source.id === id);
    const retired = data.tombstones?.find(t => t.kind === "sources" && t.record.id === id && ["retracted", "merged"].includes(t.record.publication_status || ""));
    const selected = pinned || active || (retiredClaim ? retired?.record as Source | undefined : undefined);
    if (!selected) return [];
    return [{ ...selected, ...(retired ? { withdrawn_status: retired.record.publication_status as "retracted" | "merged" } : {}) }];
  });
}
