import { useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Snapshot, BaseRecord, Source } from "./types";
import { recordKinds } from "./types";
import { apiBase, pretty, title } from "./data";
type EditorEntry = {
  kind: string;
  record: BaseRecord;
  editorial_status?: string;
};
const queueLimit = 50;
const templates: Record<string, Record<string, unknown>> = {
  actors: {
    name: "",
    actor_type: "organization",
    country_code: null,
    longitude: null,
    latitude: null,
    theaters: [],
    category: "",
  },
  relationships: {
    from_actor_id: "",
    to_actor_id: "",
    relationship_type: "",
    category: "",
    theaters: [],
    valid_from: null,
    valid_to: null,
  },
  developments: {
    actor_ids: [],
    occurred_start: null,
    occurred_end: null,
    date_precision: "unknown",
    development_type: "reported_development",
    url: null,
  },
  occurrences: {
    country_code: "",
    country: "",
    place_name: "",
    longitude: null,
    latitude: null,
    location_precision: "unknown",
    occurred_start: "",
    occurred_end: null,
    date_precision: "day",
    action_type: "demonstration",
    demands: [],
    targets: [],
    campaign_ids: [],
    inclusion_rationale: "",
    confidence_note: "",
  },
  campaigns: {
    country_codes: [],
    started_at: null,
    ended_at: null,
    demands: [],
    targets: [],
    occurrence_ids: [],
  },
  connections: {
    from_id: "",
    to_id: "",
    connection_type: "",
    evidence_note: "",
  },
  contests: {
    office: "house",
    cycle: 2026,
    state_code: "",
    jurisdiction: "",
    district: null,
    geography_version: "unavailable",
    boundary_status: "unavailable",
    status: "not_assessed",
    result_as_of: null,
    election_date: "2026-11-03",
    candidates: [],
    winner: null,
    winner_basis: null,
    total_votes: null,
    reporting_note: "",
    longitude: null,
    latitude: null,
  },
  election_actions: {
    action_type: "",
    actor: "",
    jurisdiction: "",
    state_code: null,
    geography_scope: "state",
    occurred_start: "",
    occurred_end: null,
    date_precision: "day",
    procedural_status: "",
    claim_status: "documented_action",
    effect_claim: null,
    effect_evidence: null,
    intent_claim: null,
    intent_evidence: null,
    related_contest_ids: [],
  },
  political_context: {
    domain: "elections",
    jurisdiction: "",
    country_code: null,
    state_code: null,
    as_of: "",
    context_type: "",
    related_ids: [],
  },
  sources: {
    url: "",
    publisher: "",
    source_type: "primary",
    published_at: null,
    retrieved_at: null,
    rights:
      "Metadata and original factual summary only; source rights retained.",
    note: "",
  },
  coverage: {
    domain: "protests",
    geography: "",
    country_code: null,
    state_code: null,
    period_start: "",
    period_end: "",
    status: "partial",
    note: "",
  },
};
const editableRecord = (record: Record<string, unknown>) => Object.fromEntries(Object.entries(record).filter(([key]) => key !== "source_snapshots"));
const labelFor = (key: string) =>
  pretty(key).replace(/^./, (c) => c.toUpperCase());
export function Editor({
  data,
  onRefresh,
}: {
  data: Snapshot;
  onRefresh: () => void;
}) {
  const [token, setToken] = useState(""),
    [credential, setCredential] = useState(""),
    [entries, setEntries] = useState<EditorEntry[]>([]),
    [total, setTotal] = useState<number | null>(null),
    [offset, setOffset] = useState(0),
    [hasMore, setHasMore] = useState(false),
    [search, setSearch] = useState(""),
    [appliedSearch, setAppliedSearch] = useState(""),
    [queueLoading, setQueueLoading] = useState(false),
    [status, setStatus] = useState("draft"),
    [kind, setKind] = useState("occurrences"),
    [record, setRecord] = useState<Record<string, unknown>>({}),
    [editing, setEditing] = useState(false),
    [existing, setExisting] = useState(false),
    [dirty, setDirty] = useState(false),
    [reason, setReason] = useState(""),
    [target, setTarget] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [advanced, setAdvanced] = useState(""),
    [revisions, setRevisions] = useState<unknown[]>([]),
    [privateSources, setPrivateSources] = useState<Source[]>([]);
  const queueVersion = useRef(0), sessionVersion = useRef(0);
  const endpoint = `${apiBase}/api/v1/editor/records`;
  async function request(
    path: string,
    method = "GET",
    body?: unknown,
    auth = token,
  ) {
    const response = await fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${auth}`,
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        response.status === 409
          ? "Revision conflict: another change was saved. Reload this record before applying your correction."
          : response.status === 401
            ? "Authentication failed. Check the editor token."
            : response.status === 503
              ? "Editorial service is unavailable or has no configured token."
              : typeof payload.detail === "string"
                ? payload.detail
                : JSON.stringify(
                    payload.detail ||
                      payload.error ||
                      `HTTP ${response.status}`,
                  ),
      );
    return payload;
  }
  async function load(
    auth = token,
    filter = status,
    recordKind = kind,
    query = appliedSearch,
    pageOffset = offset,
  ) {
    const version = ++queueVersion.current, session = sessionVersion.current;
    const current = () => version === queueVersion.current && session === sessionVersion.current;
    setQueueLoading(true);
    setEntries([]);
    setTotal(null);
    setHasMore(false);
    setOffset(pageOffset);
    const params = new URLSearchParams({
      status: filter,
      kind: recordKind,
      q: query,
      limit: String(queueLimit),
      offset: String(pageOffset),
    });
    try {
      const payload = await request(`${endpoint}?${params}`, "GET", undefined, auth);
      if (!current()) return false;
      if (
        !payload || !Array.isArray(payload.items) || payload.items.length > queueLimit ||
        !Number.isInteger(payload.total) || payload.total < 0 ||
        payload.limit !== queueLimit || payload.offset !== pageOffset ||
        typeof payload.has_more !== "boolean" ||
        payload.items.some((entry: EditorEntry) => entry?.kind !== recordKind || !entry.record?.id)
      )
        throw new Error("The editorial service returned an unsupported paginated queue response.");
      setEntries(payload.items);
      setTotal(payload.total);
      setHasMore(payload.has_more);
      return true;
    } catch (error) {
      if (current()) throw error;
      return false;
    } finally {
      if (current()) setQueueLoading(false);
    }
  }
  function refreshQueue(pageOffset = offset) {
    setNotice("");
    void load(token, status, kind, appliedSearch, pageOffset)
      .catch((error) => setNotice(error.message));
  }
  async function connect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    const session = ++sessionVersion.current;
    try {
      if (!await load(credential) || session !== sessionVersion.current) return;
      setToken(credential);
      setCredential("");
      setNotice(
        "Connected. Credentials are held only in memory for this editor session.",
      );
    } catch (e) {
      setNotice(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  function newRecord() {
    const r = {
      id: "",
      ...(kind === "sources"
        ? { title: "" }
        : kind === "coverage"
          ? { source_ids: [], reviewed_at: null }
          : {
              title: "",
              summary: "",
              source_ids: [],
              evidence_status: "unreviewed",
              reviewed_at: null,
            }),
      ...templates[kind],
    };
    setDirty(true);
    setRecord(r);
    setAdvanced(JSON.stringify(r, null, 2));
    setExisting(false);
    setEditing(true);
    setReason("");
    setRevisions([]);
    setPrivateSources([]);
    setTarget("");
  }
  async function open(entry: EditorEntry) {
    const session = sessionVersion.current;
    setBusy(true);
    setNotice("");
    try {
      const p = await request(
        `${endpoint}/${entry.kind}/${encodeURIComponent(entry.record.id)}`,
      );
      if (session !== sessionVersion.current) return;
      setKind(entry.kind);
      setRecord(editableRecord(p.record || p));
      setAdvanced(JSON.stringify(editableRecord(p.record || p), null, 2));
      setExisting(true);
      setDirty(false);
      setEditing(true);
      setReason("");
      setTarget("");
      setRevisions(p.revisions || []);
      setPrivateSources(p.sources || []);
    } catch (e) {
      if (session === sessionVersion.current) setNotice((e as Error).message);
    } finally {
      if (session === sessionVersion.current) setBusy(false);
    }
  }
  function field(key: string, value: unknown) {
    setDirty(true);
    setRecord((r) => {
      const next = { ...r, [key]: value };
      setAdvanced(JSON.stringify(next, null, 2));
      return next;
    });
  }
  async function action(actionName: "save" | "publish" | "retract" | "merge") {
    const session = sessionVersion.current;
    setBusy(true);
    setNotice("");
    try {
      if (!reason.trim())
        throw new Error("A revision reason is required for every change.");
      if (!record.id || !String(record.id).trim())
        throw new Error("A stable record ID is required.");
      if (actionName === "merge" && !target.trim())
        throw new Error("Enter the stable target ID before merging.");
      if (actionName === "publish" && dirty)
        throw new Error(
          "Save the draft before publishing. The form contains unsaved changes.",
        );
      const path = `${endpoint}/${kind}${existing ? "/" + encodeURIComponent(String(record.id)) : ""}`;
      const payload =
        actionName === "save"
          ? { record: editableRecord(record), reason, expected_revision: record.revision }
          : {
              expected_revision: record.revision,
              reason,
              ...(actionName === "merge" ? { target_id: target } : {}),
            };
      const result = await request(
        actionName === "save" ? path : `${path}/${actionName}`,
        actionName === "save" ? (existing ? "PUT" : "POST") : "POST",
        payload,
      );
      if (session !== sessionVersion.current) return;
      setRecord(editableRecord(result.record || result));
      setAdvanced(JSON.stringify(editableRecord(result.record || result), null, 2));
      setExisting(true);
      setDirty(false);
      setReason("");
      setNotice(
        actionName === "save"
          ? "Draft saved by the API. It remains private until explicit publication."
          : actionName === "publish"
            ? "Saved revision published by the API. The public snapshot is refreshing."
            : `${labelFor(actionName)} completed by the API. Public history is retained.`,
      );
      await load();
      if (session === sessionVersion.current) onRefresh();
    } catch (e) {
      if (session === sessionVersion.current) setNotice((e as Error).message);
    } finally {
      if (session === sessionVersion.current) setBusy(false);
    }
  }
  const availableSources = [...data.sources, ...privateSources].filter(
    (s, i, a) => a.findIndex((x) => x.id === s.id) === i,
  );
  if (!apiBase)
    return (
      <div className="reading editor-intro">
        <span className="eyebrow">Protected workspace</span>
        <h1>Editorial access</h1>
        <p className="lead">This edition is a public research snapshot.</p>
        <div className="notice">
          The editorial API is not configured. Drafts and publishing are
          unavailable in this static build.
        </div>
        <p>
          Run the local service and configure <code>VITE_API_BASE</code> to
          connect to persistent editorial records. Credentials are entered at
          runtime and are never included in a public snapshot or browser
          storage.
        </p>
        <a href="#/data" className="text-link">
          Read publication & evidence policy →
        </a>
      </div>
    );
  return (
    <section className="editor-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Protected workspace</span>
          <h1>Editorial desk</h1>
          <p>
            Source-linked candidates, deliberate publication, traceable
            corrections.
          </p>
        </div>
        {token && (
          <button
            onClick={() => {
              sessionVersion.current++;
              queueVersion.current++;
              setToken("");
              setCredential("");
              setEntries([]);
              setTotal(null);
              setOffset(0);
              setHasMore(false);
              setSearch("");
              setAppliedSearch("");
              setQueueLoading(false);
              setBusy(false);
              setStatus("draft");
              setKind("occurrences");
              setEditing(false);
              setRecord({});
              setAdvanced("");
              setReason("");
              setTarget("");
              setDirty(false);
              setExisting(false);
              setPrivateSources([]);
              setRevisions([]);
              setNotice(
                "Disconnected. Token and private records cleared from this screen.",
              );
            }}
          >
            Lock workspace
          </button>
        )}
      </div>
      {!token ? (
        <form onSubmit={connect} className="auth-form">
          <h2>Connect to the editorial service</h2>
          <p>
            The owner token grants access to private candidates. It is kept only
            in memory and cleared when this workspace closes.
          </p>
          <label>
            Editor token
            <input
              type="password"
              autoComplete="off"
              required
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || !credential}>
            Connect
          </button>
        </form>
      ) : (
        <div className="editor-layout">
          <aside className="editor-queue">
            <h2>Candidate queue</h2>
            <label>
              Queue status
              <select
                value={status}
                disabled={busy}
                onChange={async (e) => {
                  setStatus(e.target.value);
                  try {
                    setNotice("");
                    await load(token, e.target.value, kind, appliedSearch, 0);
                  } catch (err) {
                    setNotice((err as Error).message);
                  }
                }}
              >
                <option value="draft">Draft candidates</option>
                <option value="published">Published</option>
                <option value="retracted">Retracted</option>
                <option value="merged">Merged</option>
              </select>
            </label>
            <label>
              Record type
              <select
                value={kind}
                disabled={busy}
                onChange={async (e) => {
                  setKind(e.target.value);
                  setEditing(false);
                  setNotice("");
                  try {
                    await load(token, status, e.target.value, appliedSearch, 0);
                  } catch (err) {
                    setNotice((err as Error).message);
                  }
                }}
              >
                {[...recordKinds, "sources", "coverage"].map((k) => (
                  <option key={k} value={k}>
                    {pretty(k)}
                  </option>
                ))}
              </select>
            </label>
            <form onSubmit={async (e) => {
              e.preventDefault();
              const query = search.trim();
              setAppliedSearch(query);
              setNotice("");
              try { await load(token, status, kind, query, 0); }
              catch (err) { setNotice((err as Error).message); }
            }}>
              <label>
                Search queue
                <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Title, summary or stable ID" disabled={busy} />
              </label>
              <button type="submit" disabled={busy}>Search queue</button>
            </form>
            <button className="primary" onClick={newRecord} disabled={busy}>
              + New {pretty(kind)}
            </button>
            <button disabled={busy || queueLoading} onClick={() => refreshQueue()}>
              Refresh queue
            </button>
            <p role="status" aria-live="polite">
              {queueLoading ? "Loading candidate queue…" : total === null ? "Queue count unavailable." : entries.length ? `Showing ${offset + 1}–${offset + entries.length} of ${total} records` : `Showing 0 of ${total} records`}
            </p>
            <nav aria-label="Queue pages">
              <button
                disabled={busy || queueLoading || offset === 0}
                onClick={() => refreshQueue(Math.max(0, offset - queueLimit))}
              >Previous page</button>
              <button
                disabled={busy || queueLoading || !hasMore}
                onClick={() => refreshQueue(offset + queueLimit)}
              >Next page</button>
            </nav>
            <div className="queue-records">
              {entries.length ? (
                entries.map((entry, i) => (
                  <button
                    key={`${entry.kind}-${entry.record.id}-${i}`}
                    disabled={busy || queueLoading}
                    onClick={() => open(entry)}
                  >
                    <span className="eyebrow">
                      {pretty(entry.kind)} · {entry.editorial_status || status}
                    </span>
                    <strong>{title(entry.record)}</strong>
                    <small>Revision {entry.record.revision}</small>
                  </button>
                ))
              ) : (
                !queueLoading && <p className="muted">{total === null ? "The queue could not be loaded. Refresh to retry." : "No candidates match this queue."}</p>
              )}
            </div>
          </aside>
          <div className="editor-form">
            {editing ? (
              <>
                <div className="section-heading">
                  <h2>{existing ? "Review & correct" : "Create candidate"}</h2>
                  <span>
                    {pretty(kind)}{" "}
                    {record.revision ? `· revision ${record.revision}` : ""}
                  </span>
                </div>
                <div className="form-grid">
                  {Object.entries(record)
                    .filter(
                      ([k]) =>
                        ![
                          "source_ids",
                          "source_snapshots",
                          "revision",
                          "updated_at",
                          "publication_status",
                          "legacy_payload",
                        ].includes(k),
                    )
                    .map(([k, value]) => (
                      <label
                        key={k}
                        className={
                          [
                            "summary",
                            "inclusion_rationale",
                            "confidence_note",
                            "reporting_note",
                            "note",
                            "rights",
                          ].includes(k)
                            ? "wide"
                            : ""
                        }
                      >
                        {labelFor(k)}
                        {k === "evidence_status" ? (
                          <select
                            value={String(value)}
                            onChange={(e) => field(k, e.target.value)}
                          >
                            {[
                              "unreviewed",
                              "reviewed",
                              "legacy_unverified",
                            ].map((s) => (
                              <option key={s}>{s}</option>
                            ))}
                          </select>
                        ) : Array.isArray(value) ||
                          (typeof value === "object" && value !== null) ? (
                          <textarea
                            aria-label={labelFor(k)}
                            value={JSON.stringify(value)}
                            onChange={(e) => {
                              try {
                                field(k, JSON.parse(e.target.value));
                              } catch {
                                setNotice(
                                  `${labelFor(k)} must be valid JSON. Use the structured JSON editor for complex edits.`,
                                );
                              }
                            }}
                          />
                        ) : [
                            "summary",
                            "inclusion_rationale",
                            "confidence_note",
                            "reporting_note",
                            "note",
                            "rights",
                          ].includes(k) ? (
                          <textarea
                            value={String(value ?? "")}
                            onChange={(e) => field(k, e.target.value)}
                            rows={3}
                          />
                        ) : (
                          <input
                            disabled={existing && k === "id"}
                            value={String(value ?? "")}
                            placeholder={value === null ? "Unknown / null" : ""}
                            onChange={(e) =>
                              field(
                                k,
                                e.target.value === "" && value === null
                                  ? null
                                  : typeof value === "number" ||
                                      [
                                        "total_votes",
                                        "longitude",
                                        "latitude",
                                        "cycle",
                                      ].includes(k)
                                    ? Number(e.target.value)
                                    : e.target.value,
                              )
                            }
                          />
                        )}
                      </label>
                    ))}
                </div>
                {kind !== "sources" && (
                  <div className="review-attestation">
                    <p>
                      {dirty
                        ? "Unsaved form changes. Save the draft before publishing."
                        : "Publication applies to the saved revision."}
                    </p>
                    <button
                      onClick={() => {
                        const next = {
                          ...record,
                          reviewed_at: new Date().toISOString(),
                          ...(kind !== "coverage"
                            ? { evidence_status: "reviewed" }
                            : {}),
                        };
                        setRecord(next);
                        setAdvanced(JSON.stringify(next, null, 2));
                        setDirty(true);
                      }}
                    >
                      Record my review now
                    </button>
                    <small>
                      This records your deliberate review time. It does not
                      establish a source's allegations as fact.
                    </small>
                  </div>
                )}
                {kind !== "sources" && (
                  <fieldset className="source-picker">
                    <legend>Linked evidence</legend>
                    <p>
                      Publication requires eligible linked sources. Create a
                      source record first if it is not listed.
                    </p>
                    {availableSources.map((s) => (
                      <label key={s.id}>
                        <input
                          type="checkbox"
                          checked={(
                            (record.source_ids || []) as string[]
                          ).includes(s.id)}
                          onChange={(e) => {
                            const ids = (record.source_ids || []) as string[];
                            field(
                              "source_ids",
                              e.target.checked
                                ? [...ids, s.id]
                                : ids.filter((x) => x !== s.id),
                            );
                          }}
                        />
                        <span>
                          {s.title}
                          <small>
                            {s.publisher} · {s.source_type} · {s.id}
                          </small>
                        </span>
                      </label>
                    ))}
                    {!availableSources.length && (
                      <p>
                        No source records loaded. Add a source using Record type
                        → Sources.
                      </p>
                    )}
                  </fieldset>
                )}
                <details className="structured">
                  <summary>Structured JSON editor</summary>
                  <p>
                    For arrays, typed date precision, complex candidate results,
                    and additional contract fields. Apply JSON before saving.
                  </p>
                  <textarea
                    aria-label="Full candidate JSON"
                    spellCheck={false}
                    rows={18}
                    value={advanced}
                    onChange={(e) => setAdvanced(e.target.value)}
                  />
                  <button
                    onClick={() => {
                      try {
                        const parsed = JSON.parse(advanced);
                        if (
                          !parsed ||
                          Array.isArray(parsed) ||
                          typeof parsed !== "object"
                        )
                          throw new Error();
                        setRecord(editableRecord(parsed));
                        setDirty(true);
                        setNotice(
                          "JSON applied to the candidate form. Save draft to persist it.",
                        );
                      } catch {
                        setNotice(
                          "Invalid JSON object. No changes were applied.",
                        );
                      }
                    }}
                  >
                    Apply JSON to form
                  </button>
                </details>
                <label className="revision-reason">
                  Reason for this revision
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={2}
                    placeholder="What changed, and which evidence supports it?"
                  />
                </label>
                <div className="editor-actions">
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => action("save")}
                  >
                    Save draft
                  </button>
                  {existing && (
                    <>
                      <button
                        disabled={busy || dirty}
                        onClick={() => action("publish")}
                      >
                        Publish saved revision
                      </button>
                      <button
                        className="danger"
                        disabled={busy}
                        onClick={() => action("retract")}
                      >
                        Retract
                      </button>
                    </>
                  )}
                </div>
                {existing && (
                  <details className="structured">
                    <summary>Reconcile duplicate / merge</summary>
                    <p>
                      Merging records preserves a redirect to the surviving
                      record. The API records the reason and expected revision.
                    </p>
                    <label>
                      Surviving record ID
                      <input
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                      />
                    </label>
                    <button
                      disabled={busy || !target}
                      onClick={() => action("merge")}
                    >
                      Merge into target
                    </button>
                  </details>
                )}
                {revisions.length > 0 && (
                  <details className="structured">
                    <summary>Revision history ({revisions.length})</summary>
                    <pre>{JSON.stringify(revisions, null, 2)}</pre>
                  </details>
                )}
              </>
            ) : (
              <div className="empty">
                <h2>Select a record to review</h2>
                <p>
                  Open an existing candidate or create a typed record.
                  Publishing is an explicit API operation.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
      {notice && (
        <div role="status" className="editor-notice notice">
          {notice}
        </div>
      )}
      {busy && (
        <span className="sr-only" role="status">
          Working with editorial service…
        </span>
      )}
    </section>
  );
}
