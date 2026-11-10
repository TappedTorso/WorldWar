import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import type {
  BaseRecord,
  Domain,
  ResearchItem,
  Snapshot,
  Source,
  RecordKind,
  Contest,
} from "./types";
import {
  allItems,
  cardDateLabel,
  apiBase,
  date,
  downloadExport,
  fetchSnapshot,
  filterItems,
  findPublicRecord,
  pretty,
  publishedItems,
  recordDate,
  recordInterval,
  recordSources,
  researchTitle,
  safeUrl,
  title,
} from "./data";
import {
  domainLabel,
  itemRoute,
  routeTo,
  updateFilter,
  useRoute,
} from "./routes";
import { ResearchMap } from "./Map";
import { Editor } from "./Editor";
import { recordKinds } from "./types";
type SearchHit = {
  id: string;
  domain: Domain;
  kind: RecordKind;
  title: string;
  summary: string;
  record?: BaseRecord;
};
const nav = [
  ["overview", "Overview"],
  ["conflicts", "Conflicts"],
  ["protests", "Protests"],
  ["elections", "U.S. Elections"],
  ["data", "Data & Methodology"],
] as const;
const descriptions: Record<
  Domain,
  { eyebrow: string; heading: string; description: string }
> = {
  conflicts: {
    eyebrow: "01 / Conflict systems",
    heading: "Actors, interests & connections",
    description:
      "Explore the geography of conflict actors and their documented relationships. Inherited assessments remain visibly unverified.",
  },
  protests: {
    eyebrow: "02 / Collective action",
    heading: "Where collective action takes shape",
    description:
      "Significant demonstrations, strikes, occupations and blockades, from September 2026. Observations are evidence; missing coverage is not zero activity.",
  },
  elections: {
    eyebrow: "03 / United States · 2026 midterms",
    heading: "The count. The process. The evidence.",
    description:
      "House and Senate reporting, certification and documented institutional actions after November 3. Every result retains its reporting basis and date.",
  },
};
export function EvidenceBadge({ record }: { record: BaseRecord }) {
  return (
    <span className={`badge evidence-${record.evidence_status}`}>
      {record.evidence_status === "legacy_unverified"
        ? "Inherited · unverified"
        : pretty(record.evidence_status)}
    </span>
  );
}
export function App() {
  const [data, setData] = useState<Snapshot | null>(null),
    [error, setError] = useState(""),
    [refreshing, setRefreshing] = useState(false),
    [search, setSearch] = useState(""),
    [searchOpen, setSearchOpen] = useState(false);
  const [archiveHits, setArchiveHits] = useState<{
      query: string;
      hits: SearchHit[];
    } | null>(null),
    [searchBusy, setSearchBusy] = useState(false),
    [searchError, setSearchError] = useState("");
  const route = useRoute();
  const main = useRef<HTMLElement>(null);
  const previousSection = useRef(route.section);
  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      setData(await fetchSnapshot());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  useEffect(() => {
    if (previousSection.current !== route.section) {
      main.current?.focus();
      previousSection.current = route.section;
    }
    setSearchOpen(false);
  }, [route.section, route.id]);
  const items = useMemo(() => (data ? publishedItems(data) : []), [data]);
  const localFound = search.trim()
    ? items
        .filter((i) =>
          [
            researchTitle(i, data),
            i.record.summary,
            i.record.id,
            i.kind,
            i.domain,
          ]
            .join(" ")
            .toLowerCase()
            .includes(search.toLowerCase()),
        )
        .slice(0, 12)
    : [];
  useEffect(() => {
    let active = true;
    setSearchError("");
    if (!apiBase || !searchOpen || search.trim().length < 2) {
      setArchiveHits(null);
      setSearchBusy(false);
      return;
    }
    setSearchBusy(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(`${apiBase}/api/v1/search?q=${encodeURIComponent(search.trim())}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      })
        .then(async (response) => {
          if (!response.ok) throw new Error();
          return response.json();
        })
        .then((payload) => {
          if (!active) return;
          const hits = (Array.isArray(payload.items) ? payload.items : [])
            .filter(
              (hit: SearchHit) =>
                recordKinds.includes(hit.kind) &&
                ["conflicts", "protests", "elections"].includes(hit.domain) &&
                typeof hit.id === "string",
            )
            .slice(0, 12)
            .map((hit: SearchHit) => {
              const known = items.find(
                (i) => i.kind === hit.kind && i.record.id === hit.id,
              );
              return {
                ...hit,
                title: known ? researchTitle(known, data) : hit.title,
                record: known?.record,
              };
            });
          setArchiveHits({ query: search.trim(), hits });
        })
        .catch(() => {
          if (active)
            setSearchError(
              "Archive search is unavailable. Snapshot matches are shown.",
            );
        })
        .finally(() => {
          if (active) setSearchBusy(false);
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [search, searchOpen, items, data]);
  const found: SearchHit[] =
    archiveHits?.query === search.trim()
      ? archiveHits.hits
      : localFound.map((i) => ({
          id: i.record.id,
          kind: i.kind,
          domain: i.domain,
          title: researchTitle(i, data),
          summary: i.record.summary,
          record: i.record,
        }));
  function submitSearch(e: FormEvent) {
    e.preventDefault();
    setSearchOpen(true);
  }
  return (
    <>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to research
      </a>
      <header className="app-header">
        <a
          className="brand"
          href="#/overview"
          aria-label="WorldWar research atlas home"
        >
          <span className="brand-symbol" aria-hidden="true">
            ◎
          </span>
          <span>
            WORLDWAR<small>RESEARCH ATLAS</small>
          </span>
        </a>
        <nav aria-label="Primary">
          {nav.map(([key, label]) => (
            <a
              key={key}
              className={route.section === key ? "current" : ""}
              aria-current={route.section === key ? "page" : undefined}
              href={routeTo(key)}
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="header-tools">
          <button
            className="search-toggle"
            aria-label="Search"
            onClick={() => {
              setSearchOpen((v) => !v);
              setTimeout(
                () => document.getElementById("global-search")?.focus(),
                0,
              );
            }}
            aria-expanded={searchOpen}
            aria-controls="search-panel"
          >
            <span aria-hidden="true">⌕</span>
            <span>Search</span>
          </button>
          <a
            href="#/editor"
            className={`editor-link ${route.section === "editor" ? "current" : ""}`}
            aria-label="Protected editorial workspace"
          >
            Editor <span aria-hidden="true">↗</span>
          </a>
        </div>
      </header>
      {searchOpen && (
        <section
          className="search-panel"
          id="search-panel"
          aria-label="Search published research"
          onKeyDown={(event) => {
            if (event.key === "Escape") setSearchOpen(false);
          }}
        >
          <form onSubmit={submitSearch}>
            <label htmlFor="global-search">Search the research archive</label>
            <div className="search-input-row">
              <input
                autoFocus
                id="global-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Actor, place, campaign, election action…"
              />
              <button
                onClick={() => setSearchOpen(false)}
                type="button"
                aria-label="Close search"
              >
                ×
              </button>
            </div>
          </form>
          <p className="muted">
            {apiBase
              ? "Searches the public archive, including records beyond the bounded snapshot. Type at least two characters for archive search."
              : "Searches this published snapshot. The discovery archive can contain additional records; see Data & Methodology."}{" "}
            Evidence state is shown where available.
          </p>
          {searchBusy && (
            <p className="small" role="status">
              Searching public archive…
            </p>
          )}
          {searchError && (
            <p className="small" role="status">
              {searchError}
            </p>
          )}
          {search.trim() && (
            <div className="search-results">
              {found.length ? (
                found.map((i) => (
                  <a
                    key={`${i.kind}-${i.id}`}
                    href={routeTo(
                      i.domain,
                      new URLSearchParams(),
                      i.kind,
                      i.id,
                    )}
                    onClick={() => setSearchOpen(false)}
                  >
                    <span className="eyebrow">
                      {domainLabel(i.domain)} / {pretty(i.kind)}
                    </span>
                    <strong>{i.title}</strong>
                    {i.record ? (
                      <EvidenceBadge record={i.record} />
                    ) : (
                      <span className="badge">Evidence state in record</span>
                    )}
                  </a>
                ))
              ) : (
                <p>No published records match “{search}”.</p>
              )}
            </div>
          )}
        </section>
      )}
      <main id="main-content" ref={main} tabIndex={-1}>
        {!data ? (
          <div className="loading-page">
            {error ? (
              <>
                <span className="eyebrow">Snapshot unavailable</span>
                <h1>The research could not be loaded.</h1>
                <p role="alert">{error}</p>
                <button onClick={refresh}>Try again</button>
                <p>
                  Public records are loaded from{" "}
                  {apiBase
                    ? "the configured research API"
                    : "the bundled versioned snapshot"}
                  . No empty dataset has been substituted for this failure.
                </p>
              </>
            ) : (
              <>
                <span className="loading-dot" />
                <h1>Opening the research atlas…</h1>
                <p>Loading the published snapshot and evidence ledger.</p>
              </>
            )}
          </div>
        ) : (
          <>
            {error && (
              <div className="refresh-warning" role="alert">
                Refresh failed. Showing snapshot {data.meta.data_version} from{" "}
                {date(data.meta.generated_at)}. {error}{" "}
                <button onClick={refresh}>Retry</button>
              </div>
            )}
            {route.section === "overview" ? (
              <Overview data={data} items={items} />
            ) : route.section === "data" ? (
              <DataPage
                data={data}
                onRefresh={refresh}
                refreshing={refreshing}
              />
            ) : route.section === "editor" ? (
              <Editor data={data} onRefresh={refresh} />
            ) : (
              <Workspace domain={route.section as Domain} data={data} />
            )}
          </>
        )}
      </main>
      <footer className="app-footer">
        <span>
          WORLDWAR <span className="footer-divider">/</span> An independent
          research atlas
        </span>
        <span>
          {data
            ? `Snapshot ${data.meta.data_version} · ${date(data.meta.generated_at)}`
            : "Versioned, source-led research"}{" "}
          <a href="#/data">Evidence & methods ↗</a>
        </span>
      </footer>
    </>
  );
}
function Overview({ data, items }: { data: Snapshot; items: ResearchItem[] }) {
  const reviewed = items.filter(
    (i) => i.record.evidence_status === "reviewed" && i.kind !== "contests",
  ).length;
  const unverified = items.filter(
    (i) => i.record.evidence_status === "legacy_unverified",
  ).length;
  const developments = items
    .filter(
      (i) =>
        ["developments", "occurrences", "election_actions"].includes(i.kind) &&
        recordDate(i.record),
    )
    .sort((a, b) =>
      String(recordDate(b.record)).localeCompare(String(recordDate(a.record))),
    )
    .slice(0, 5);
  return (
    <div className="overview">
      <section className="overview-hero">
        <div className="hero-copy">
          <span className="eyebrow">The world, with its sources attached</span>
          <h1>
            Follow the threads.
            <br />
            <em>Examine the evidence.</em>
          </h1>
          <p className="lead">
            A shared atlas for conflict systems, collective action and U.S.
            elections. Explore what is documented, how it connects, and where
            the record remains incomplete.
          </p>
          <a className="primary button" href="#/conflicts">
            Enter the atlas <span>→</span>
          </a>
          <a className="hero-method" href="#/data">
            How this research works ↗
          </a>
        </div>
        <div className="hero-cartography" aria-hidden="true">
          <svg viewBox="0 0 500 400">
            <defs>
              <pattern
                id="hero-grid"
                width="35"
                height="35"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M35 0H0V35"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth=".4"
                />
              </pattern>
            </defs>
            <circle cx="260" cy="200" r="165" fill="url(#hero-grid)" />
            <ellipse cx="260" cy="200" rx="165" ry="70" />
            <ellipse cx="260" cy="200" rx="80" ry="165" />
            <circle cx="260" cy="200" r="165" />
            <path d="M95 200H425M260 35V365M130 95L385 305M130 305L385 95" />
            <path
              className="hero-orbit"
              d="M122 268Q260 38 408 175M129 124Q220 320 380 298M187 50Q420 180 160 325"
            />
            <g className="hero-dots">
              <circle cx="122" cy="268" r="5" />
              <circle cx="408" cy="175" r="5" />
              <circle cx="187" cy="50" r="5" />
              <circle cx="160" cy="325" r="5" />
              <circle cx="380" cy="298" r="5" />
              <circle cx="129" cy="124" r="5" />
            </g>
          </svg>
          <div className="hero-map-caption">
            CONNECTIONS NEED EVIDENCE
            <br />
            <span>Geography is a starting point.</span>
          </div>
        </div>
      </section>
      <div className="edition-line">
        <span>
          <i className="status-dot" /> Reviewed snapshot ·{" "}
          {date(data.meta.generated_at)}
        </span>
        <span>
          {reviewed} reviewed research records /{" "}
          {
            data.contests.filter((c) => c.publication_status === "published")
              .length
          }{" "}
          registered contests / {unverified} inherited assessments
        </span>
        <a href="#/data">Inspect the coverage ledger →</a>
      </div>
      <section className="domain-index" aria-label="Research domains">
        {(["conflicts", "protests", "elections"] as Domain[]).map(
          (d, index) => {
            const relevant = items.filter((i) => i.domain === d);
            const primary =
              d === "conflicts"
                ? "actors"
                : d === "protests"
                  ? "occurrences"
                  : "contests";
            const count = relevant.filter((i) => i.kind === primary).length;
            return (
              <a className="domain-entry" href={routeTo(d)} key={d}>
                <span className="index-number">0{index + 1}</span>
                <div>
                  <span className="eyebrow">
                    {d === "conflicts"
                      ? "Systems & relationships"
                      : d === "protests"
                        ? "Collective mobilization"
                        : "2026 / Post-election"}
                  </span>
                  <h2>
                    {domainLabel(d)} <span>↗</span>
                  </h2>
                  <p>
                    {d === "conflicts"
                      ? "Actors, theaters and the relationships that shape conflict."
                      : d === "protests"
                        ? "Documented observations, campaign histories and coverage."
                        : "House, Senate and the institutions behind the process."}
                  </p>
                  <small>
                    {count}{" "}
                    {primary === "contests"
                      ? "included contests"
                      : primary === "occurrences"
                        ? "observations"
                        : pretty(primary)}{" "}
                    · {data.coverage.filter((c) => c.domain === d).length}{" "}
                    coverage entries
                  </small>
                </div>
              </a>
            );
          },
        )}
      </section>
      <section className="overview-bottom">
        <div>
          <div className="section-heading">
            <div>
              <span className="eyebrow">Chronology</span>
              <h2>In the documented record</h2>
            </div>
            <span>Occurrence dates, where known</span>
          </div>
          {developments.length ? (
            <div className="overview-chronology">
              {developments.map((i) => (
                <a key={i.record.id} href={itemRoute(i)}>
                  <time>
                    {date(recordDate(i.record), i.record.date_precision)}
                  </time>
                  <div>
                    <span className="eyebrow">
                      {domainLabel(i.domain)} /{" "}
                      {pretty(
                        i.record.action_type ||
                          i.record.development_type ||
                          i.kind,
                      )}
                    </span>
                    <h3>{researchTitle(i, data)}</h3>
                    <EvidenceBadge record={i.record} />
                  </div>
                  <span>↗</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="empty">
              <h3>No dated published developments yet.</h3>
              <p>
                The actor network remains available. Source discovery is kept
                separate from a verified chronology.
              </p>
            </div>
          )}
        </div>
        <aside className="research-note">
          <span className="eyebrow">A note on the record</span>
          <h2>Coverage has boundaries.</h2>
          <p>{data.meta.coverage_summary}</p>
          <p>
            Counts describe the material included in this edition. They do not
            measure all conflict, all protests or every electoral development.
          </p>
          <a href="#/data" className="text-link">
            Sources, limitations & corrections →
          </a>
        </aside>
      </section>
    </div>
  );
}
function Workspace({ domain, data }: { domain: Domain; data: Snapshot }) {
  const route = useRoute();
  const { params } = route;
  useEffect(() => {
    if (route.id && window.matchMedia?.("(max-width: 680px)").matches)
      document.getElementById("selected-record-heading")?.focus();
  }, [route.id]);
  const [filterOpen, setFilterOpen] = useState(false);
  const p = params.toString();
  const all = useMemo(
    () => publishedItems(data).filter((i) => i.domain === domain),
    [domain, data],
  );
  const filtered = useMemo(() => filterItems(all, params, data), [all, p]);
  const selectedLocal = findPublicRecord(data, domain, route.kind, route.id);
  const [remoteSelection, setRemoteSelection] = useState<{
    item: ResearchItem;
    sources: Source[];
    revisions: unknown[];
  } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false),
    [detailError, setDetailError] = useState("");
  useEffect(() => {
    let active = true;
    setRemoteSelection(null);
    setDetailError("");
    if (
      !apiBase ||
      !route.id ||
      !recordKinds.includes(route.kind as RecordKind)
    ) {
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    fetch(
      `${apiBase}/api/v1/records/${route.kind}/${encodeURIComponent(route.id)}`,
    )
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "No public revision is available for this stable ID."
              : `Public detail request failed (HTTP ${response.status}).`,
          );
        return response.json();
      })
      .then((payload) => {
        if (active) {
          setRemoteSelection({
            item: {
              kind: route.kind as RecordKind,
              domain,
              record: payload.record,
            },
            sources: payload.sources || [],
            revisions: payload.revisions || [],
          });
        }
      })
      .catch((error) => {
        if (active) setDetailError(error.message);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [route.kind, route.id, domain, data.meta.data_version]);
  const remote =
    remoteSelection?.item.record.id === route.id ? remoteSelection : null;
  const selected = remote?.item || selectedLocal;
  const mode = params.get("view") || "list";
  const layer =
    params.get("layer") || (domain === "conflicts" ? "actors" : "all");
  let visible = filtered.filter(
    (i) => i.kind !== "political_context" && i.kind !== "connections",
  );
  if (domain === "elections" && layer !== "all")
    visible = visible.filter((i) =>
      layer === "actions"
        ? i.kind === "election_actions"
        : i.kind === "contests" && i.record.office === layer,
    );
  if (domain === "conflicts" && layer !== "all")
    visible = visible.filter((i) =>
      layer === "chronology"
        ? i.kind === "developments" &&
          i.record.development_type !== "discovery_article"
        : layer === "reporting"
          ? i.kind === "developments" &&
            i.record.development_type === "discovery_article"
          : layer === "relationships"
            ? i.kind === "relationships"
            : i.kind === "actors",
    );
  if (domain === "protests" && layer === "campaigns")
    visible = visible.filter((i) => i.kind === "campaigns");
  if (domain === "protests" && layer === "observations")
    visible = visible.filter((i) => i.kind === "occurrences");
  const sort = params.get("sort") || "date";
  visible = [...visible].sort((a, b) =>
    sort === "name"
      ? title(a.record).localeCompare(title(b.record))
      : String(recordDate(b.record) || "").localeCompare(
          String(recordDate(a.record) || ""),
        ) || title(a.record).localeCompare(title(b.record)),
  );
  const geography = Array.from(
    new Set(
      [
        ...all.flatMap((i) => [
          String(i.record.country_code || i.record.state_code || ""),
          ...(Array.isArray(i.record.country_codes)
            ? (i.record.country_codes as string[])
            : []),
        ]),
        ...data.coverage
          .filter((c) => c.domain === domain)
          .map((c) => String(c.country_code || c.state_code || "")),
      ],
    ).values(),
  )
    .filter(Boolean)
    .filter(code => domain !== "elections" || stateName(code) !== code)
    .sort();
  const types = Array.from(
    new Set(
      all
        .map((i) =>
          String(
            i.record.action_type ||
              i.record.development_type ||
              i.record.relationship_type ||
              i.record.actor_type ||
              "",
          ),
        )
        .filter(Boolean),
    ),
  ).sort();
  const context = data.political_context.filter(
    (c) =>
      c.publication_status === "published" &&
      c.domain === domain &&
      (!params.get("geo") ||
        c.country_code === params.get("geo") ||
        c.state_code === params.get("geo")),
  );
  const coverage = data.coverage.filter(
    (c) =>
      c.domain === domain &&
      (!params.get("geo") ||
        c.country_code === params.get("geo") ||
        c.state_code === params.get("geo")),
  );
  function filter(k: string, v: string) {
    updateFilter(domain, params, k, v);
  }
  function select(item: ResearchItem) {
    const next = new URLSearchParams(params);
    next.set("view", "detail");
    window.location.hash = itemRoute(item, next);
  }
  const info = descriptions[domain];
  if (params.get("read") === "1" && selected)
    return (
      <div className="full-reading">
        <a
          className="back-link"
          href={itemRoute(
            selected,
            new URLSearchParams([...params].filter(([k]) => k !== "read")),
          )}
        >
          ← Return to atlas and retained filters
        </a>
        <Detail
          key={`${selected.record.id}-${selected.record.revision}`}
          item={selected}
          data={data}
          sources={remote?.sources}
          publicHistory={remote?.revisions}
          full
        />
      </div>
    );
  return (
    <div className={`workspace workspace-${domain}`} data-mode={mode}>
      <section className="workspace-heading">
        <div>
          <span className="eyebrow">{info.eyebrow}</span>
          <h1>{info.heading}</h1>
          <p>{info.description}</p>
        </div>
        <div className="export-buttons">
          <span>Export this scope</span>
          <button onClick={() => downloadExport("csv", visible, data)}>
            CSV ↓
          </button>
          <button onClick={() => downloadExport("json", visible, data)}>
            JSON ↓
          </button>
        </div>
      </section>
      <div className="layer-bar">
        <div className="segmented" aria-label="Research layer">
          {(domain === "elections"
            ? [
                ["all", "All research"],
                ["house", "House"],
                ["senate", "Senate"],
                ["actions", "Election actions"],
              ]
            : domain === "conflicts"
              ? [
                  ["all", "Network & record"],
                  ["actors", "Actors"],
                  ["relationships", "Relationships"],
                  ["chronology", "Chronology"],
                  ["reporting", "Discovered reporting"],
                ]
              : [
                  ["all", "Observations & campaigns"],
                  ["observations", "Observations"],
                  ["campaigns", "Campaigns"],
                ]
          ).map(([key, label]) => (
            <button
              key={key}
              className={layer === key ? "active" : ""}
              onClick={() => filter("layer", key)}
              aria-pressed={layer === key}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="mobile-filter-toggle"
          onClick={() => setFilterOpen((v) => !v)}
          aria-expanded={filterOpen}
        >
          Filters {filterOpen ? "−" : "+"}
        </button>
        <span className="layer-total">{visible.length} records in scope</span>
      </div>
      <form
        className={`scope-bar ${filterOpen ? "open" : ""}`}
        onSubmit={(e) => e.preventDefault()}
      >
        <label className="scope-search">
          Find in {domainLabel(domain)}
          <input
            type="search"
            value={params.get("q") || ""}
            onChange={(e) => filter("q", e.target.value)}
            placeholder={
              domain === "conflicts"
                ? "Actor, theater, relationship…"
                : "Place, title, demand…"
            }
          />
        </label>
        <label>
          {domain === "elections" ? "State" : "Country"}
          <select
            value={params.get("geo") || ""}
            onChange={(e) => filter("geo", e.target.value)}
          >
            <option value="">
              All {domain === "elections" ? "states" : "countries"}
            </option>
            {geography.map((g) => (
              <option key={g} value={g}>
                {domain === "elections" ? stateName(g) : regionName(g)} ({g})
              </option>
            ))}
          </select>
        </label>
        <label>
          Evidence
          <select
            value={params.get("status") || ""}
            onChange={(e) => filter("status", e.target.value)}
          >
            <option value="">All evidence states</option>
            <option value="reviewed">Reviewed</option>
            <option value="legacy_unverified">Inherited / unverified</option>
            <option value="unreviewed">Unreviewed</option>
            {domain === "elections" &&
              [
                "not_assessed",
                "not_reported",
                "reported_unofficial",
                "provider_called",
                "certified",
                "recount",
                "contested",
              ].map((s) => (
                <option key={s} value={s}>
                  {pretty(s)}
                </option>
              ))}
          </select>
        </label>
        <label>
          From
          <input
            type="date"
            value={params.get("from") || ""}
            onChange={(e) => filter("from", e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={params.get("to") || ""}
            onChange={(e) => filter("to", e.target.value)}
          />
        </label>
        <details className="more-filters">
          <summary>More filters</summary>
          <div>
            <label>
              Record type
              <select
                value={params.get("kind") || ""}
                onChange={(e) => filter("kind", e.target.value)}
              >
                <option value="">All types</option>
                {Array.from(new Set(all.map((i) => i.kind))).map((k) => (
                  <option value={k} key={k}>
                    {pretty(k)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Action / relationship
              <select
                value={params.get("type") || ""}
                onChange={(e) => filter("type", e.target.value)}
              >
                <option value="">All</option>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {pretty(t)}
                  </option>
                ))}
              </select>
            </label>
            {domain === "elections" && (
              <label className="national-toggle">
                <input
                  type="checkbox"
                  checked={params.get("national") !== "hide"}
                  onChange={(e) =>
                    filter("national", e.target.checked ? "" : "hide")
                  }
                />
                Include nationwide actions when a state is selected
              </label>
            )}
            {domain === "elections" && (
              <label>
                Institutional actor
                <input
                  value={params.get("actor") || ""}
                  onChange={(e) => filter("actor", e.target.value)}
                />
              </label>
            )}
          </div>
        </details>
        <a className="reset" href={routeTo(domain)}>
          Reset scope ↺
        </a>
      </form>
      <div className="mobile-modes" aria-label="Workspace view">
        {["map", "list", "detail"].map((v) => (
          <button
            key={v}
            className={mode === v ? "active" : ""}
            onClick={() => filter("view", v)}
            aria-pressed={mode === v}
          >
            {v === "map" ? "Map" : v === "list" ? "Results" : "Detail"}
          </button>
        ))}
      </div>
      <div className="exploration">
        <div className="map-column">
          <ResearchMap
            domain={domain}
            layer={layer}
            items={visible}
            data={data}
            selected={route.id}
            onSelect={select}
            onGeo={(g) => filter("geo", g)}
            geo={params.get("geo") || ""}
          />
          <Chronology
            items={visible}
            data={data}
            selected={route.id}
            onSelect={select}
          />
          <CoverageStrip coverage={coverage} />
          {domain === "protests" && (
            <Scorecards data={data} geo={params.get("geo") || ""} />
          )}
        </div>
        <div className="results-column">
          <div className="section-heading results-heading">
            <div>
              <span className="eyebrow">Accessible research index</span>
              <h2>
                {domain === "elections" && layer === "actions"
                  ? "Actions chronology"
                  : domain === "conflicts" && layer === "relationships"
                    ? "Relationships"
                    : "In this scope"}{" "}
                <small>{visible.length}</small>
              </h2>
            </div>
            <label className="sort-label">
              Sort
              <select
                value={sort}
                onChange={(e) => filter("sort", e.target.value)}
              >
                <option value="date">Newest occurrence</option>
                <option value="name">A–Z</option>
              </select>
            </label>
          </div>
          <ol className="record-list">
            {visible.map((i) => (
              <li
                key={`${i.kind}-${i.record.id}`}
                className={route.id === i.record.id ? "selected" : ""}
              >
                <a
                  href={itemRoute(
                    i,
                    new URLSearchParams({
                      ...Object.fromEntries(params),
                      view: "detail",
                    }),
                  )}
                  aria-current={route.id === i.record.id ? "true" : undefined}
                >
                  <span className="record-meta">
                    <span>
                      {pretty(
                        i.record.action_type ||
                          i.record.development_type ||
                          i.kind,
                      )}
                    </span>
                    <time>
                      {cardDateLabel(i)}
                    </time>
                  </span>
                  <h3>{researchTitle(i, data)}</h3>
                  <p>{i.record.summary}</p>
                  <div className="record-bottom">
                    <EvidenceBadge record={i.record} />
                    <span>
                      {i.record.source_ids?.length || 0} linked sources{" "}
                      <span aria-hidden="true">↗</span>
                    </span>
                  </div>
                  {i.kind === "contests" && (
                    <div className="contest-status">
                      {pretty(i.record.status)} ·{" "}
                      {i.record.winner
                        ? `Winner: ${String(i.record.winner)}`
                        : "No supported winner recorded"}
                    </div>
                  )}
                </a>
              </li>
            ))}
          </ol>
          {!visible.length && (
            <div className="empty">
              <span className="empty-symbol" aria-hidden="true">
                ∅
              </span>
              <h3>
                {all.length
                  ? "No records match this scope."
                  : "No published records in this domain."}
              </h3>
              <p>
                {all.length
                  ? "Try another country, date range or evidence state. Records with unknown occurrence dates are excluded by date filters."
                  : "The coverage ledger describes the work reviewed so far. This absence does not establish that no activity occurred."}
              </p>
              {all.length > 0 && (
                <a href={routeTo(domain)} className="text-link">
                  Clear filters →
                </a>
              )}
            </div>
          )}
          {context.length > 0 && (
            <details className="context-panel">
              <summary>Dated institutional context ({context.length})</summary>
              {context.map((c) => (
                <div key={c.id}>
                  <time>{date(c.as_of)}</time>
                  <h3>
                    <a
                      href={itemRoute(
                        { domain, kind: "political_context", record: c },
                        params,
                      )}
                    >
                      {title(c)}
                    </a>
                  </h3>
                  <p>{c.summary}</p>
                  <EvidenceBadge record={c} />
                </div>
              ))}
            </details>
          )}
        </div>
        <aside className="detail-column" aria-label="Selected record">
          {selected ? (
            <>
              <div className="detail-toolbar">
                <span className="eyebrow">Selected research</span>
                <a
                  href={routeTo(domain, params)}
                  aria-label="Close selected record"
                >
                  ×
                </a>
              </div>
              {filterItems([selected], params, data).length === 0 && (
                <div className="notice">
                  This selected record is outside the current filters.{' '}
                  <a href={itemRoute(selected)}>Open it without filters →</a>
                </div>
              )}
              <Detail
                key={`${selected.record.id}-${selected.record.revision}`}
                item={selected}
                data={data}
                sources={remote?.sources}
                publicHistory={remote?.revisions}
              />
              <a
                className="full-record-link"
                href={itemRoute(
                  selected,
                  new URLSearchParams({
                    ...Object.fromEntries(params),
                    read: "1",
                  }),
                )}
              >
                Open reading view ↗
              </a>
            </>
          ) : route.id ? (
            <div className="empty">
              <h2>
                {detailLoading
                  ? "Loading public record…"
                  : "Record unavailable"}
              </h2>
              <p>
                This stable ID is not included in the current public snapshot.
                It may be private, removed, or from another edition.
              </p>
              {detailError && <p role="status">{detailError}</p>}
              <code>{route.id}</code>
              <a href={routeTo(domain, params)}>Return to this scope</a>
            </div>
          ) : (
            <div className="selection-empty">
              <span aria-hidden="true">↖</span>
              <span className="eyebrow">Follow a thread</span>
              <h2>Begin with a record.</h2>
              <p>
                Select an actor, observation or contest to read its evidence,
                dates and relationships.
              </p>
              <p className="muted">
                The map and results list open the same records. Every item has a
                stable link.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
function regionName(code: string) {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) || code;
  } catch {
    return code;
  }
}
function CoverageStrip({ coverage }: { coverage: Snapshot["coverage"] }) {
  const counts = coverage.reduce(
    (a, c) => ((a[c.status] = (a[c.status] || 0) + 1), a),
    {} as Record<string, number>,
  );
  return (
    <div className="coverage-strip">
      <strong>Coverage in scope</strong>
      <p>
        {coverage.length
          ? Object.entries(counts)
              .map(([k, v]) => `${v} ${pretty(k)}`)
              .join(" · ")
          : "No coverage assessment recorded for this scope."}
      </p>
      <a href="#/data">Review periods & limitations ↗</a>
    </div>
  );
}
function Scorecards({ data, geo }: { data: Snapshot; geo: string }) {
  const cards = data.scorecards.filter((s) => !geo || s.country_code === geo);
  if (!cards.length)
    return (
      <div className="activity-panel">
        <span className="eyebrow">Observed activity</span>
        <h3>No eligible comparison yet.</h3>
        <p>
          Momentum requires comparable covered periods. Missing observations
          cannot produce a zero or a trend.
        </p>
      </div>
    );
  return (
    <section className="activity-panel">
      <span className="eyebrow">Observed activity / not a composite score</span>
      <details key={geo || "all"} open={Boolean(geo)}>
        <summary>
          {geo
            ? `${regionName(geo)} activity and coverage`
            : `Explore activity and coverage for ${cards.length} jurisdictions`}
        </summary>
        <p>
          Choose a country above to inspect its observations, recorded search
          coverage and comparison eligibility. A source search does not establish
          complete event coverage.
        </p>
      {cards.map((s) => (
        <details key={s.id}>
          <summary>
            {s.geography === s.country_code
              ? regionName(s.country_code)
              : s.geography} ·{" "}
            {s.momentum === "insufficient_data"
              ? "Insufficient comparison data"
              : pretty(s.momentum)}
          </summary>
          <p>
            {date(s.period_start)} – {date(s.period_end)}
          </p>
          <dl className="activity-numbers">
            <div>
              <dt>Occurrences</dt>
              <dd>{s.occurrence_count}</dd>
            </div>
            <div>
              <dt>Active days</dt>
              <dd>{s.active_days}</dd>
            </div>
            <div>
              <dt>Locations</dt>
              <dd>{s.location_count}</dd>
            </div>
            <div>
              <dt>Campaigns</dt>
              <dd>{s.campaign_count}</dd>
            </div>
          </dl>
          <p>{s.note}</p>
          <p>
            Coverage: {pretty(s.coverage_status)} · Method {s.method_version} ·
            Calculated {date(s.calculated_at)}
          </p>
          <p>
            Comparison: {date(s.comparison_start)} – {date(s.comparison_end)}.
            Previous occurrence count:{" "}
            {s.previous_occurrence_count ?? "Unavailable"}.
          </p>
          <details>
            <summary>Reproducible input IDs ({s.input_ids.length})</summary>
            <code>{s.input_ids.join(", ") || "None recorded"}</code>
          </details>
        </details>
      ))}
      </details>
    </section>
  );
}
function Detail({
  item,
  data,
  full = false,
  sources,
  publicHistory,
}: {
  item: ResearchItem;
  data: Snapshot;
  full?: boolean;
  sources?: Source[];
  publicHistory?: unknown[];
}) {
  const r = item.record;
  const [history, setHistory] = useState<unknown[] | null>(
      publicHistory || null,
    ),
    [historyError, setHistoryError] = useState("");
  useEffect(() => {
    if (publicHistory) setHistory(publicHistory);
  }, [publicHistory]);
  const sourceList = sources || recordSources(data, r);
  const related: ResearchItem[] = publishedItems(data).filter(
    (i) =>
      i.record.id !== r.id &&
      ((item.kind === "actors" &&
        (i.record.from_actor_id === r.id ||
          i.record.to_actor_id === r.id ||
          (Array.isArray(i.record.actor_ids) &&
            i.record.actor_ids.includes(r.id)))) ||
        (item.kind === "campaigns" &&
          Array.isArray(r.occurrence_ids) &&
          r.occurrence_ids.includes(i.record.id)) ||
        (item.kind === "occurrences" &&
          Array.isArray(r.campaign_ids) &&
          r.campaign_ids.includes(i.record.id)) ||
        (Array.isArray(i.record.related_contest_ids) &&
          i.record.related_contest_ids.includes(r.id)) ||
        (Array.isArray(r.related_contest_ids) &&
          r.related_contest_ids.includes(i.record.id)) ||
        (i.kind === "connections" &&
          (i.record.from_id === r.id || i.record.to_id === r.id))),
  );
  const updated = r.reviewed_at || null;
  const stale =
    !!updated && Date.now() - new Date(updated).getTime() > 90 * 86400000;
  async function getHistory() {
    if (!apiBase) {
      setHistoryError(
        "Revision history is available through the research API. This snapshot retains the public revision number and review date.",
      );
      return;
    }
    try {
      const res = await fetch(
        `${apiBase}/api/v1/records/${item.kind}/${encodeURIComponent(r.id)}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setHistory(d.revisions || []);
    } catch (e) {
      setHistoryError(`History could not be loaded: ${(e as Error).message}`);
    }
  }
  return (
    <article
      className={`record-detail ${full ? "reading-detail" : ""}`}
      key={r.id}
    >
      <span className="eyebrow">
        {domainLabel(item.domain)} / {pretty(item.kind)}
      </span>
      <h2 id="selected-record-heading" tabIndex={-1}>
        {researchTitle(item, data)}
      </h2>
      <div className="detail-badges">
        <EvidenceBadge record={r} />
        {r.publication_status !== "published" && (
          <span className="badge">{pretty(r.publication_status)}</span>
        )}
        {stale && (
          <span className="badge stale">Review older than 90 days</span>
        )}
      </div>
      {r.publication_status === "merged" && (
        <div className="notice">
          This record was merged.{" "}
          {r.merged_into && (
            <a
              href={`#/${item.domain}/${item.kind}/${encodeURIComponent(r.merged_into)}`}
            >
              Open surviving record →
            </a>
          )}
        </div>
      )}
      {r.publication_status === "retracted" && (
        <div className="notice">
          Retracted record. Retained for historical accountability; excluded
          from normal research results.
        </div>
      )}
      <p className="detail-summary">
        {r.summary || "No factual summary recorded."}
      </p>
      {r.evidence_status === "legacy_unverified" && (
        <details className="inherited-note">
          <summary>About this inherited assessment</summary>
          <p>
            This record preserves an earlier dataset. Its classifications,
            relationships and citation text have not been verified as current
            facts. Importing it did not constitute a new review.
          </p>
          {r.legacy_updated_at && (
            <small>Legacy update field: {r.legacy_updated_at}</small>
          )}
        </details>
      )}
      {item.kind === "developments" &&
        r.development_type === "discovery_article" && (
          <div className="notice">
            Discovered reporting. Article discovery is not a verified real-world
            occurrence or relationship update.
          </div>
        )}
      {item.kind === "actors" && (
        <dl className="facts">
          <Fact name="Actor type" value={pretty(r.actor_type)} />
          <Fact
            name="Country"
            value={
              r.country_code
                ? regionName(String(r.country_code))
                : "Not assigned"
            }
          />
          <Fact
            name="Theaters"
            value={
              Array.isArray(r.theaters)
                ? r.theaters.join(" · ")
                : "Not recorded"
            }
          />
          <Fact name="Inherited classification" value={pretty(r.category)} />
        </dl>
      )}
      {item.kind === "relationships" && (
        <>
          <dl className="facts">
            <Fact name="Relationship" value={pretty(r.relationship_type)} />
            <Fact name="Valid from" value={date(r.valid_from)} />
            <Fact name="Valid to" value={date(r.valid_to)} />
          </dl>
          <div className="relationship-endpoints">
            {["from_actor_id", "to_actor_id"].map((key, index) => {
              const actor = data.actors.find((a) => a.id === r[key]);
              return actor ? (
                <a
                  href={itemRoute({
                    kind: "actors",
                    domain: "conflicts",
                    record: actor,
                  })}
                  key={key}
                >
                  <small>{index ? "To" : "From"}</small>
                  {title(actor)} →
                </a>
              ) : (
                <p key={key}>
                  {pretty(key)}: {String(r[key])}
                </p>
              );
            })}
          </div>
        </>
      )}
      {["occurrences", "developments", "election_actions"].includes(
        item.kind,
      ) && (
        <dl className="facts">
          <Fact
            name={item.kind === "occurrences" ? "Reported action date" : "Occurred"}
            value={date(r.occurred_start, r.date_precision)}
          />
          {!!r.occurred_end && (
            <Fact
              name="Through"
              value={date(r.occurred_end, r.date_precision)}
            />
          )}
          <Fact name="Date precision" value={pretty(r.date_precision)} />
          {item.kind === "developments" && (
            <Fact name="Discovered" value={date(r.discovered_at)} />
          )}
        </dl>
      )}
      {item.kind === "occurrences" && (
        <>
          <dl className="facts">
            <Fact
              name="Location"
              value={[r.place_name, r.country].filter(Boolean).join(", ")}
            />
            <Fact
              name="Location precision"
              value={pretty(r.location_precision)}
            />
            <Fact name="Action" value={pretty(r.action_type)} />
            <Fact
              name="Occurrence totals"
              value={r.count_eligible === false
                ? "Excluded from occurrence totals"
                : r.date_precision === "unknown"
                  ? "Editorially eligible; occurrence date unresolved"
                  : "Eligible when its reported dates fit the count period"}
            />
            {Array.isArray(r.active_dates) && r.active_dates.length > 0 && (
              <Fact
                name="Documented active dates"
                value={r.active_dates.map((day) => date(day)).join(" · ")}
              />
            )}
          </dl>
          {(r.longitude === null || r.latitude === null) && (
            <p className="precision-note">
              Exact coordinates are unavailable. Geographic shading indicates
              the documented country; it does not assert a precise event
              location.
            </p>
          )}
          <TextField
            heading="Why this is included"
            value={r.inclusion_rationale}
          />
          <TextField heading="Confidence & limits" value={r.confidence_note} />
          {["participants", "response", "outcome"].map((k) => (
            <TextField key={k} heading={pretty(k)} value={r[k]} />
          ))}
        </>
      )}
      {item.kind === "campaigns" && (
        <>
          <dl className="facts">
            <Fact name="Campaign started" value={date(r.started_at, r.date_precision)} />
            <Fact
              name="Campaign ended"
              value={r.ended_at ? date(r.ended_at, r.date_precision) : "End not established"}
            />
            <Fact name="Date precision" value={pretty(r.date_precision)} />
            {!!r.reported_through && (
              <Fact name="Reported through" value={date(r.reported_through)} />
            )}
            <Fact
              name="Countries"
              value={
                Array.isArray(r.country_codes)
                  ? r.country_codes.map((c) => regionName(String(c))).join(", ")
                  : "Not recorded"
              }
            />
            <Fact
              name="Linked observations"
              value={String(
                Array.isArray(r.occurrence_ids) ? r.occurrence_ids.length : 0,
              )}
            />
          </dl>
          <p className="precision-note">
            Campaign context is not a count of separately verified occurrences.
            Aggregate reporting is not split into invented daily events.
          </p>
          <TextField heading="Date uncertainty" value={r.date_uncertainty} />
          <TextField heading="Coverage & limits" value={r.coverage_note} />
          {Array.isArray(r.places_reported) && r.places_reported.length > 0 && (
            <TextField heading="Reported places" value={r.places_reported.join(" · ")} />
          )}
        </>
      )}
      {["demands", "targets"].map((k) =>
        Array.isArray(r[k]) && r[k].length > 0 ? (
          <section className="detail-section" key={k}>
            <h3>{pretty(k)}</h3>
            <ul>
              {r[k].map((v: unknown, index: number) => (
                <li key={index}>{String(v)}</li>
              ))}
            </ul>
          </section>
        ) : null,
      )}
      {item.kind === "contests" && <ContestDetail contest={r as Contest} />}
      {item.kind === "election_actions" && (
        <>
          <dl className="facts">
            <Fact name="Actor" value={String(r.actor)} />
            <Fact name="Jurisdiction" value={String(r.jurisdiction)} />
            <Fact name="Scope" value={pretty(r.geography_scope)} />
            <Fact
              name="Procedural status"
              value={pretty(r.procedural_status)}
            />
            <Fact name="Claim status" value={pretty(r.claim_status)} />
            {!!r.status_as_of && <Fact name="Procedural status as of" value={date(r.status_as_of)} />}
            {!!r.legal_effective_date_as_stated && (
              <Fact name="Stated effective date" value={date(r.legal_effective_date_as_stated)} />
            )}
            {!!r.case_id && <Fact name="Case or document" value={r.case_id} />}
          </dl>
          <TextField heading="Case-status review" value={r.current_case_status ? pretty(r.current_case_status) : null} />
          <TextField heading="Operative-status evidence" value={r.current_operative_status ? pretty(r.current_operative_status) : null} />
          <TextField heading="Allegation limits" value={r.allegation_note} />
          <TextField heading="Claimed effect" value={r.effect_claim} />
          <TextField heading="Evidence of effect" value={r.effect_evidence} />
          <TextField heading="Claimed intent" value={r.intent_claim} />
          <TextField heading="Evidence of intent" value={r.intent_evidence} />
          <p className="precision-note">
            Documenting an action or reviewing its source does not establish an
            allegation, intent or electoral effect. Each claim retains its
            distinct basis.
          </p>
        </>
      )}
      {item.kind === "political_context" && (
        <dl className="facts">
          <Fact name="As of" value={date(r.as_of)} />
          <Fact name="Jurisdiction" value={String(r.jurisdiction)} />
          <Fact name="Context" value={pretty(r.context_type)} />
        </dl>
      )}
      {item.kind === "connections" && (
        <>
          <TextField
            heading="Documented connection"
            value={r.connection_type}
          />
          <TextField
            heading="Evidence for connection"
            value={r.evidence_note}
          />
          {["from_id", "to_id"].map((k) => {
            const target = publishedItems(data).find(
              (i) => i.record.id === r[k],
            );
            return target ? (
              <a key={k} className="related-link" href={itemRoute(target)}>
                {title(target.record)} ↗
              </a>
            ) : (
              <p key={k}>{String(r[k])}</p>
            );
          })}
        </>
      )}
      {related.length > 0 && (
        <section className="detail-section">
          <h3>
            {item.kind === "actors"
              ? "Relationships & chronology"
              : item.kind === "campaigns"
                ? "Campaign observations"
                : "Connected records"}{" "}
            <small>{related.length}</small>
          </h3>
          {related.map((i) => (
            <a className="related-link" key={i.record.id} href={itemRoute(i)}>
              <span className="eyebrow">{pretty(i.kind)}</span>
              <strong>{researchTitle(i, data)} ↗</strong>
              <EvidenceBadge record={i.record} />
            </a>
          ))}
        </section>
      )}
      <section className="detail-section evidence-section">
        <div className="section-heading">
          <h3>Sources & evidence</h3>
          <span>{sourceList.length} linked</span>
        </div>
        <TextField heading="Attribution" value={r.attribution} />
        <TextField heading="Attribution limits" value={r.attribution_note} />
        <TextField heading="Evidence location" value={r.evidence_locator} />
        {sourceList.length ? (
          sourceList.map((s) => <SourceCard source={s} key={s.id} />)
        ) : (
          <p className="muted">
            No eligible linked source metadata is attached to this record.
            Legacy citation text, when available, is preserved below.
          </p>
        )}
        {Array.isArray(r.legacy_citation_text) &&
          r.legacy_citation_text.length > 0 && (
            <details>
              <summary>
                Inherited citation text ({r.legacy_citation_text.length})
              </summary>
              <p>
                Preserved as text from the legacy record. This is not recovered
                or verified evidence.
              </p>
              <ul>
                {r.legacy_citation_text.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </details>
          )}
      </section>
      <section className="record-provenance">
        <h3>Record & review history</h3>
        <dl className="facts">
          <Fact name="Stable ID" value={r.id} />
          <Fact name="Public revision" value={String(r.revision)} />
          <Fact
            name="Reviewed"
            value={updated ? date(updated) : "No review recorded"}
          />
          <Fact
            name="Record updated"
            value={r.updated_at ? date(r.updated_at) : "Not recorded"}
          />
          <Fact
            name="Review method"
            value={r.review_method === "research_agent_source_review"
              ? "Research agent source review"
              : r.review_method === "validated_official_adapter"
                ? "Validated official data adapter"
                : r.review_method === "human_review"
                  ? "Human review"
                  : "Not recorded"}
          />
        </dl>
        <p>
          Record review, occurrence time, source publication and retrieval are
          separate dates.
        </p>
        <button onClick={getHistory}>Inspect public revision history</button>
        {historyError && <p role="status">{historyError}</p>}
        {history && (
          <pre className="history-json">{JSON.stringify(history, null, 2)}</pre>
        )}
      </section>
    </article>
  );
}
function Fact({ name, value }: { name: string; value: unknown }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{String(value ?? "Not recorded")}</dd>
    </div>
  );
}
function TextField({ heading, value }: { heading: string; value: unknown }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <section className="detail-section">
      <h3>{heading}</h3>
      <p>{typeof value === "object" ? JSON.stringify(value) : String(value)}</p>
    </section>
  );
}
export function ContestDetail({ contest: r }: { contest: Contest }) {
  return (
    <section className="contest-detail">
      <div className={`contest-result result-${r.status}`}>
        <span className="eyebrow">Reporting status / {pretty(r.office)}</span>
        <h3>{pretty(r.status)}</h3>
        <p>
          {r.winner ? (
            <>
              <strong>{r.winner}</strong>
              <br />
              Basis: {r.winner_basis || "Not recorded"}
            </>
          ) : (
            "No supported winner is recorded."
          )}
        </p>
        <small>
          Result as of{" "}
          {r.result_as_of
            ? date(r.result_as_of)
            : String(r.result_as_of_raw || "not recorded")}
        </small>
      </div>
      <dl className="facts">
        <Fact name="Jurisdiction" value={r.jurisdiction} />
        <Fact
          name="District"
          value={
            r.office === "house"
              ? (r.district ?? "Not recorded")
              : "Statewide Senate contest"
          }
        />
        <Fact name="Election date" value={date(r.election_date)} />
        <Fact name="Geography version" value={r.geography_version} />
        <Fact name="Boundary status" value={pretty(r.boundary_status)} />
        <Fact
          name="Total votes"
          value={
            r.total_votes === null
              ? "Not reported"
              : r.total_votes.toLocaleString()
          }
        />
      </dl>
      <TextField
        heading="Reporting basis & limitations"
        value={r.reporting_note}
      />
      {r.candidates.length > 0 ? (
        <div className="candidate-table">
          <table>
            <caption>Included candidates / reported figures</caption>
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Votes</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {r.candidates.map((c, i) => (
                <tr key={i}>
                  <th scope="row">
                    {c.name}
                    <small>{c.party || "Party not recorded"}</small>
                  </th>
                  <td>
                    {c.votes === null
                      ? "Not reported"
                      : c.votes.toLocaleString()}
                  </td>
                  <td>{c.percentage === null ? "—" : `${c.percentage}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="precision-note">
          Candidate figures have not been recorded. No votes, leader or result
          is inferred.
        </p>
      )}
      <p className="precision-note">
        Provider calls, unofficial reports and certified results are distinct.
        An included House record does not establish that current district
        boundaries are available.
      </p>
    </section>
  );
}
function SourceCard({ source: s }: { source: Source }) {
  const url = safeUrl(s.url);
  const withdrawn = s.withdrawn_status || (s.publication_status === "retracted" || s.publication_status === "merged" ? s.publication_status : undefined);
  return (
    <div className="source-card">
      {withdrawn && <span className="badge stale">Withdrawn source · {pretty(withdrawn)}</span>}
      <span className="eyebrow">
        {s.source_type} / {s.publisher || "Publisher not recorded"}
      </span>
      <h4>
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer">
            {s.title} ↗
          </a>
        ) : (
          s.title
        )}
      </h4>
      <p className="source-dates">
        Published {date(s.published_at || s.published_date)} · Retrieved{" "}
        {date(s.retrieved_at || s.retrieval_date || s.retrieved_date)}
      </p>
      {s.note && <p>{s.note}</p>}
      {s.evidence_locator && <p><strong>Evidence location:</strong> {s.evidence_locator}</p>}
      <details>
        <summary>Source metadata & rights</summary>
        <dl className="facts">
          <Fact name="Source ID" value={s.id} />
          <Fact
            name="Rights"
            value={s.rights || "Rights not specified; source rights retained"}
          />
          {s.language && <Fact name="Language" value={s.language} />}
          {s.source_tier && <Fact name="Source basis" value={pretty(s.source_tier)} />}
          {s.document_date && <Fact name="Document date" value={date(s.document_date)} />}
          {s.source_updated_date && <Fact name="Source updated" value={date(s.source_updated_date)} />}
          {s.access_status && <Fact name="Access & review basis" value={pretty(s.access_status)} />}
          {s.content_sha256 && <Fact name="Captured-content SHA-256" value={s.content_sha256} />}
        </dl>
        {!url && (
          <p>
            No retrievable URL was preserved. This is not a clickable source
            document.
          </p>
        )}
      </details>
    </div>
  );
}
function DataPage({
  data,
  onRefresh,
  refreshing,
}: {
  data: Snapshot;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [domain, setDomain] = useState("all");
  const items = publishedItems(data);
  const coverage = data.coverage.filter(
    (c) => domain === "all" || c.domain === domain,
  );
  return (
    <div className="data-page">
      <section className="page-heading">
        <div>
          <span className="eyebrow">The research behind the atlas</span>
          <h1>Data, evidence & limitations.</h1>
          <p>
            Inspect what is included, when it was reviewed, and how public
            observations become structured research.
          </p>
        </div>
        <button onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Checking snapshot…" : "Refresh snapshot ↻"}
        </button>
      </section>
      <div className="data-layout">
        <aside className="contents">
          <span className="eyebrow">On this page</span>
          {[
            ["publication", "This edition"],
            ["methods", "Evidence & methods"],
            ["coverage", "Coverage ledger"],
            ["health", "Collection runs"],
            ["sources", "Source register"],
            ["export", "Research exports"],
          ].map(([id, label]) => (
            <a
              key={id}
              href={`#data-${id}`}
              onClick={(e) => {
                e.preventDefault();
                document
                  .getElementById(`data-${id}`)
                  ?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              {label}
            </a>
          ))}
        </aside>
        <div className="data-content">
          <section id="data-publication">
            <span className="eyebrow">01 / Publication</span>
            <h2>This is a reviewed snapshot.</h2>
            <p className="lead">{data.meta.coverage_summary}</p>
            <dl className="publication-facts">
              <Fact
                name="Publication data through"
                value={date(data.meta.generated_at)}
              />
              <Fact name="Data version" value={data.meta.data_version} />
              <Fact name="Schema" value={data.schema_version} />
              <Fact name="Mode" value={pretty(data.meta.publication_mode)} />
              <Fact
                name="Delivery"
                value={
                  apiBase
                    ? "Configured research API"
                    : "Bundled static snapshot"
                }
              />
              <Fact
                name="Inherited review marker"
                value={
                  data.meta.legacy_reviewed_at
                    ? date(data.meta.legacy_reviewed_at)
                    : "Not recorded"
                }
              />
            </dl>
            {typeof data.meta.discovery_total === "number" && (
              <p className="notice">
                Discovery archive: {data.meta.discovery_total.toLocaleString()}{" "}
                article records recovered. This public snapshot includes{" "}
                {data.meta.discovery_visible ??
                  data.developments.filter(
                    (d) => d.development_type === "discovery_article",
                  ).length}{" "}
                discovered articles. Article records are not verified events or
                protest observations.
              </p>
            )}
            <p>
              The publication timestamp is the latest public record or collection-run
              time in this edition. It does not refresh the underlying evidence. Each record and source retains
              its own dates. This application does not promise nationwide
              real-time election results or a complete global event census.
            </p>
          </section>
          <section id="data-methods">
            <span className="eyebrow">02 / How to read the record</span>
            <h2>Facts before connections.</h2>
            <div className="method-grid">
              <div>
                <h3>Distinct research objects</h3>
                <p>
                  Conflict actors and relationships, protest occurrences and
                  campaigns, and election contests and actions keep separate
                  meanings. A discovered article is a candidate for research,
                  never automatically a verified occurrence.
                </p>
              </div>
              <div>
                <h3>Evidence has a state</h3>
                <p>
                  <strong>Reviewed</strong> indicates an editorial review of the
                  cited claim. <strong>Inherited / unverified</strong> preserves
                  legacy assessments without recasting them as current facts.{" "}
                  <strong>Unreviewed</strong> material remains labeled
                  reporting.
                </p>
              </div>
              <div>
                <h3>Four clocks, no substitutions</h3>
                <p>
                  Occurrence or validity time, source publication,
                  retrieval/discovery, and editorial review are separate.
                  Unknown dates remain unknown; ranges and precision remain
                  visible. Reviews older than 90 days receive a freshness label,
                  not an automatic factual rejection.
                </p>
              </div>
              <div>
                <h3>Observed activity, explicit limits</h3>
                <p>
                  Scorecards count deduplicated observations, active dates,
                  locations and campaigns in a named period. Momentum requires
                  comparable coverage. There is no global 0–100 temperature or
                  combined political/conflict score.
                </p>
              </div>
              <div>
                <h3>Election reporting is specific</h3>
                <p>
                  Not assessed, not reported, unofficial, provider called,
                  certified, recount and contested are distinct states. No
                  contest is not inferred from no included record. Intent,
                  electoral effect, allegations and court findings require their
                  own attributed evidence.
                </p>
              </div>
              <div>
                <h3>Corrections preserve the record</h3>
                <p>
                  Authenticated editors save candidates before deliberately
                  publishing source-linked revisions. Revision conflicts are
                  rejected. Retractions retain tombstones; merges preserve
                  stable identifiers and the surviving record. Private drafts
                  and notes do not enter this public build.
                </p>
              </div>
            </div>
            <div className="notice">
              Geography: locally bundled Natural Earth country outlines and U.S.
              Census-derived state outlines are contextual reference geometry.
              Borders do not imply endorsement. House districts use official
              Census geometry only when stable contest ID, state, district and
              verified plan vintage agree. Unavailable or mismatched plans
              retain state context. Missouri uses the operative unchanged CD119
              plan under Census's published exception. These simplified display
              shapes are not an address lookup or a legal boundary
              determination.
            </div>
            <p className="small">
              Geometry:{" "}
              <a
                href="https://github.com/topojson/world-atlas"
                target="_blank"
                rel="noreferrer"
              >
                world-atlas / Natural Earth
              </a>{" "}
              ·{" "}
              <a
                href="https://github.com/topojson/us-atlas"
                target="_blank"
                rel="noreferrer"
              >
                us-atlas / U.S. Census
              </a>{" "}
              ·{" "}
              <a href={`${import.meta.env.BASE_URL}geometry/README.txt`}>
                Bundled attribution & licenses
              </a>{" "}
              ·{" "}
              <a
                href={`${import.meta.env.BASE_URL}geometry/districts-attribution.json`}
              >
                Official House geometry provenance & source hashes
              </a>
            </p>
          </section>
          <section id="data-coverage">
            <div className="section-heading">
              <div>
                <span className="eyebrow">03 / Scope of observation</span>
                <h2>Coverage ledger</h2>
              </div>
              <label>
                Domain
                <select
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                >
                  <option value="all">All domains</option>
                  {(["conflicts", "protests", "elections"] as Domain[]).map(
                    (d) => (
                      <option key={d} value={d}>
                        {domainLabel(d)}
                      </option>
                    ),
                  )}
                </select>
              </label>
            </div>
            <p>
              Reviewed coverage applies only to its described geography, dates
              and source scope. Partial, unavailable and not assessed are
              retained as separate states.
            </p>
            <p>
              <a href={`${import.meta.env.BASE_URL}data/research-audit.json`} download="worldwar-research-audit-20261110.json">
                Download the November 10 research audit: queries, source review and lead dispositions ↓
              </a>
            </p>
            <div className="table-scroll">
              <table>
                <caption className="sr-only">
                  Coverage by domain, geography and review period
                </caption>
                <thead>
                  <tr>
                    <th>Geography / domain</th>
                    <th>Period</th>
                    <th>Status</th>
                    <th>Scope & limitation</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.map((c) => (
                    <tr key={c.id}>
                      <th scope="row">
                        {c.country_code && c.geography === c.country_code
                          ? regionName(c.country_code)
                          : c.geography}
                        <small>{domainLabel(c.domain)}</small>
                      </th>
                      <td>
                        {date(c.period_start)}
                        <br />– {date(c.period_end)}
                      </td>
                      <td>
                        <span className={`badge coverage-${c.status}`}>
                          {pretty(c.status)}
                        </span>
                      </td>
                      <td>
                        {c.note}
                        <small>
                          Reviewed:{" "}
                          {c.reviewed_at ? date(c.reviewed_at) : "Not recorded"}
                        </small>
                        {c.source_ids.length > 0 && (
                          <small>
                            Sources:{" "}
                            {c.source_ids.map((id) => {
                              const s = data.sources.find((s) => s.id === id);
                              return s && safeUrl(s.url) ? (
                                <a
                                  key={id}
                                  href={safeUrl(s.url)}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {s.publisher || s.id} ↗{" "}
                                </a>
                              ) : (
                                id + " "
                              );
                            })}
                          </small>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!coverage.length && (
              <div className="empty">
                No coverage assessment recorded for this domain.
              </div>
            )}
          </section>
          <section id="data-health">
            <span className="eyebrow">04 / Discovery health</span>
            <h2>Collection runs</h2>
            <p>
              Fetched material is discovery input. Accepted counts are not a
              count of real-world events. A partial or failed run does not mean
              no activity occurred.
            </p>
            {data.jobs.length ? (
              <div className="job-list">
                {data.jobs.map((j) => (
                  <div key={j.id}>
                    <span className={`badge job-${j.status}`}>
                      {j.status === "ok" ? "Completed" : pretty(j.status)}
                    </span>
                    <div>
                      <h3>
                        {pretty(j.adapter)}{" "}
                        <small>{domainLabel(j.domain)}</small>
                      </h3>
                      <p>
                        {date(j.started_at)} · {j.fetched_count} fetched /{" "}
                        {j.accepted_count} accepted
                      </p>
                      {j.error && <p className="error-text">{j.error}</p>}
                      {!j.completed_at && <p>Completion not recorded.</p>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">
                No collection run history is included in this edition.
              </div>
            )}
          </section>
          <section id="data-sources">
            <span className="eyebrow">05 / Provenance</span>
            <h2>
              Source register <small>{data.sources.length}</small>
            </h2>
            <p>
              Links, metadata and original factual summaries are retained. Full
              copyrighted source text is not redistributed. Access does not
              imply an unrestricted reuse license.
            </p>
            <details className="source-register">
              <summary>
                Inspect the source register ({data.sources.length})
              </summary>
              {data.sources.map((s) => (
                <SourceCard key={s.id} source={s} />
              ))}
            </details>
          </section>
          <section id="data-export">
            <span className="eyebrow">06 / Reusable structured research</span>
            <h2>Export this edition.</h2>
            <p>
              Public exports contain published factual records and linked source
              metadata. Snapshot JSON retains the included typed fields and
              inherited provenance. Full archive JSON, including original legacy
              payloads, is available through the configured research API. CSV is
              a compact record index with source IDs; spreadsheet formula
              prefixes are neutralized. Filter a domain to export a narrower
              scope. Refer to source rights before reuse.
            </p>
            <div className="export-actions">
              {apiBase && (
                <a
                  className="primary button"
                  href={`${apiBase}/api/v1/export?format=json`}
                >
                  Download full archive JSON ↓
                </a>
              )}
              <button
                className="primary"
                onClick={() => downloadExport("json", items, data)}
              >
                Download snapshot JSON ↓
              </button>
              <button onClick={() => downloadExport("csv", items, data)}>
                Download CSV index ↓
              </button>
            </div>
            <p className="small">
              Version {data.meta.data_version} · {items.length} published
              records. Private drafts, credentials, private editorial notes and
              source bodies are excluded.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function Chronology({
  items,
  data,
  selected,
  onSelect,
}: {
  items: ResearchItem[];
  data: Snapshot;
  selected: string;
  onSelect: (i: ResearchItem) => void;
}) {
  const dated = items
    .filter((i) => recordDate(i.record))
    .sort((a, b) =>
      String(recordDate(a.record)).localeCompare(String(recordDate(b.record))),
    );
  if (!dated.length)
    return (
      <div className="chronology-empty">
        <span className="eyebrow">Chronology</span>
        <p>
          No occurrence or validity dates in this scope. Discovery and review
          dates are retained separately.
        </p>
      </div>
    );
  const intervals = new Map(dated.map((item) => [item.record.id, recordInterval(item.record)!]));
  const min = Math.min(...dated.map((item) => new Date(intervals.get(item.record.id)!.start).getTime())),
    max = Math.max(...dated.map((item) => new Date(intervals.get(item.record.id)!.end).getTime()));
  const ranges = dated.some((item) => {
    const interval = intervals.get(item.record.id)!;
    return interval.end > interval.start;
  });
  return (
    <section className="chronology-strip" aria-label="Dated record timeline">
      <div className="section-heading">
        <span className="eyebrow">Occurrence / validity chronology</span>
        <span>{dated.length} dated records</span>
      </div>
      <div className="chronology-track">
        {dated.map((i, index) => {
          const interval = intervals.get(i.record.id)!;
          const start = new Date(interval.start).getTime(), end = new Date(interval.end).getTime();
          const ranged = end > start;
          const label = i.record.date_precision === "month"
            ? `${date(interval.start, "month")} · day not established`
            : ranged ? `${date(interval.start)}–${date(interval.end)} · reported interval` : date(interval.start);
          return (
          <button
            key={i.record.id}
            className={`${selected === i.record.id ? "selected" : ""} ${ranged ? "date-interval" : ""}`}
            style={{
              left: `${max > min ? 3 + (94 * (start - min)) / (max - min) : 50}%`,
              ...(ranged && max > min ? { width: `${94 * (end - start) / (max - min)}%` } : {}),
              top: index % 3 === 0 ? "9px" : index % 3 === 1 ? "18px" : "27px",
            }}
            title={`${label} · ${researchTitle(i, data)}`}
            aria-label={`${label}: ${researchTitle(i, data)}`}
            onClick={() => onSelect(i)}
          />
        );})}
      </div>
      <div className="chronology-dates">
        <time>
          {date(new Date(min).toISOString())}
        </time>
        <time>
          {date(new Date(max).toISOString())}
        </time>
      </div>
      {ranges && <p className="small">Bars show the reported interval or possible month, not proof of activity on every day.</p>}
    </section>
  );
}

function stateName(code: string) {
  const states: Record<string, string> = {
    AL: "Alabama",
    AK: "Alaska",
    AZ: "Arizona",
    AR: "Arkansas",
    CA: "California",
    CO: "Colorado",
    CT: "Connecticut",
    DE: "Delaware",
    DC: "District of Columbia",
    FL: "Florida",
    GA: "Georgia",
    HI: "Hawaii",
    ID: "Idaho",
    IL: "Illinois",
    IN: "Indiana",
    IA: "Iowa",
    KS: "Kansas",
    KY: "Kentucky",
    LA: "Louisiana",
    ME: "Maine",
    MD: "Maryland",
    MA: "Massachusetts",
    MI: "Michigan",
    MN: "Minnesota",
    MS: "Mississippi",
    MO: "Missouri",
    MT: "Montana",
    NE: "Nebraska",
    NV: "Nevada",
    NH: "New Hampshire",
    NJ: "New Jersey",
    NM: "New Mexico",
    NY: "New York",
    NC: "North Carolina",
    ND: "North Dakota",
    OH: "Ohio",
    OK: "Oklahoma",
    OR: "Oregon",
    PA: "Pennsylvania",
    RI: "Rhode Island",
    SC: "South Carolina",
    SD: "South Dakota",
    TN: "Tennessee",
    TX: "Texas",
    UT: "Utah",
    VT: "Vermont",
    VA: "Virginia",
    WA: "Washington",
    WV: "West Virginia",
    WI: "Wisconsin",
    WY: "Wyoming",
    PR: "Puerto Rico",
  };
  return states[code] || code;
}
