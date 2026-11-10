import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { snapshot, base } from "./fixtures";
vi.mock("../src/data", async importOriginal => ({ ...await importOriginal<typeof import("../src/data")>(), apiBase: "http://localhost:9999" }));
import { Editor } from "../src/Editor";
const endpoint = "http://localhost:9999/api/v1/editor/records";
const page = (items: { kind: string; record: typeof base }[] = [], total = items.length, offset = 0) => ({ items, total, limit: 50, offset, has_more: offset + items.length < total });
const response = (payload: unknown) => ({ ok: true, json: async () => payload }) as Response;
const queueUrl = (kind = "occurrences", status = "draft", q = "", offset = 0) => `${endpoint}?${new URLSearchParams({ status, kind, q, limit: "50", offset: String(offset) })}`;
const entry = (id: string, kind = "occurrences") => ({ kind, record: { ...base, id, title: id } });
beforeEach(() => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(page()))); });
async function connect() { fireEvent.change(screen.getByLabelText("Editor token"), { target: { value: "test-runtime-token" } }); fireEvent.click(screen.getByRole("button", { name: "Connect" })); await screen.findByRole("heading", { name: "Candidate queue" }); }
async function openActor(extra: Record<string, unknown> = {}) {
  const refresh = vi.fn();
  render(<Editor data={snapshot} onRefresh={refresh} />);
  await connect();
  vi.mocked(fetch).mockResolvedValueOnce(response(page([{ kind: "actors", record: base }])));
  fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "actors" } });
  const button = await screen.findByRole("button", { name: /actors.*Test actor/i });
  vi.mocked(fetch).mockResolvedValueOnce(response({ kind: "actors", record: { ...base, ...extra }, revisions: [] }));
  fireEvent.click(button);
  await screen.findByRole("heading", { name: "Review & correct" });
  return refresh;
}
describe("authenticated editorial contract", () => {
  it("sends runtime auth without persisting credentials and clears on lock", async () => { const storage = vi.spyOn(Storage.prototype, "setItem"); render(<Editor data={snapshot} onRefresh={() => {}} />); await connect(); expect(fetch).toHaveBeenCalledWith(queueUrl(), expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer test-runtime-token" }) })); expect(storage).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Lock workspace" })); expect(screen.getByLabelText("Editor token")).toHaveValue(""); expect(screen.queryByRole("heading", { name: "Candidate queue" })).not.toBeInTheDocument(); });
  it("requires a reason and saves a source-linked typed draft through POST", async () => { const refresh = vi.fn(); render(<Editor data={snapshot} onRefresh={refresh} />); await connect(); fireEvent.click(screen.getByRole("button", { name: "+ New occurrences" })); fireEvent.click(screen.getByRole("button", { name: "Save draft" })); expect(await screen.findByText("A revision reason is required for every change.")).toBeInTheDocument(); fireEvent.change(screen.getByLabelText("Id"), { target: { value: "test-new-occurrence" } }); fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Test candidate only" } }); fireEvent.change(screen.getByLabelText("Reason for this revision"), { target: { value: "Test evidence review" } }); fireEvent.click(screen.getByRole("checkbox")); vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ ...base, id: "test-new-occurrence", publication_status: "published", revision: 1 }) } as Response); fireEvent.click(screen.getByRole("button", { name: "Save draft" })); await waitFor(() => expect(fetch).toHaveBeenCalledWith("http://localhost:9999/api/v1/editor/records/occurrences", expect.objectContaining({ method: "POST", body: expect.stringContaining("test-source") }))); await waitFor(() => expect(refresh).toHaveBeenCalled()); expect(screen.getByRole("button", { name: "Publish saved revision" })).toBeInTheDocument(); });
  it("does not reveal the private queue after authentication rejection", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "Unauthorized" }) })); render(<Editor data={snapshot} onRefresh={() => {}} />); fireEvent.change(screen.getByLabelText("Editor token"), { target: { value: "invalid" } }); fireEvent.click(screen.getByRole("button", { name: "Connect" })); expect(await screen.findByText("Authentication failed. Check the editor token.")).toBeInTheDocument(); expect(screen.queryByRole("heading", { name: "Candidate queue" })).not.toBeInTheDocument(); });
  it("surfaces revision conflicts and uses the expected revision in publication", async () => { await openActor(); fireEvent.change(screen.getByLabelText("Reason for this revision"), { target: { value: "Publication test" } }); vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: "conflict" }) } as Response); fireEvent.click(screen.getByRole("button", { name: "Publish saved revision" })); expect(await screen.findByText(/Revision conflict/)).toBeInTheDocument(); expect(fetch).toHaveBeenLastCalledWith("http://localhost:9999/api/v1/editor/records/actors/test-actor/publish", expect.objectContaining({ method: "POST", body: JSON.stringify({ expected_revision: 1, reason: "Publication test" }) })); });
  it("creates strict source records without forbidden shared fields", async () => { render(<Editor data={snapshot} onRefresh={() => {}} />); await connect(); fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "sources" } }); fireEvent.click(screen.getByRole("button", { name: "+ New sources" })); for (const [label, value] of [["Id", "new-source"], ["Title", "Synthetic source"], ["Url", "https://example.org/test"], ["Publisher", "Synthetic publisher"], ["Reason for this revision", "Add synthetic source for test"]]) fireEvent.change(screen.getByLabelText(label), { target: { value } }); vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ id: "new-source", title: "Synthetic source", revision: 1, publication_status: "published" }) } as Response); fireEvent.click(screen.getByRole("button", { name: "Save draft" })); await waitFor(() => expect(fetch).toHaveBeenCalledWith("http://localhost:9999/api/v1/editor/records/sources", expect.objectContaining({ method: "POST" }))); const call = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith("/sources") && init?.method === "POST"); const body = JSON.parse(call?.[1]?.body as string); for (const key of ["summary", "evidence_status", "source_ids", "reviewed_at"]) expect(body.record).not.toHaveProperty(key); });
  it("blocks publication of unsaved edits and records deliberate review time", async () => { await openActor(); fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Unsaved correction" } }); expect(screen.getByRole("button", { name: "Publish saved revision" })).toBeDisabled(); expect(screen.getByText("Unsaved form changes. Save the draft before publishing.")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Record my review now" })); expect((screen.getByLabelText("Reviewed at") as HTMLInputElement).value).toMatch(/^2026-/); });
  it("keeps read-only public source snapshots out of editable forms and writes", async () => { await openActor({ source_snapshots: snapshot.sources }); expect(screen.queryByLabelText("Source snapshots")).not.toBeInTheDocument(); const json = screen.getByLabelText("Full candidate JSON") as HTMLTextAreaElement; expect(JSON.parse(json.value)).not.toHaveProperty("source_snapshots"); fireEvent.change(screen.getByLabelText("Reason for this revision"), { target: { value: "Test read-only pin handling" } }); vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ ...base, revision: 2 }) } as Response); fireEvent.click(screen.getByRole("button", { name: "Save draft" })); await waitFor(() => expect(fetch).toHaveBeenCalledWith("http://localhost:9999/api/v1/editor/records/actors/test-actor", expect.objectContaining({ method: "PUT" }))); const call = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith("/actors/test-actor") && init?.method === "PUT"); expect(JSON.parse(call?.[1]?.body as string).record).not.toHaveProperty("source_snapshots"); });
});

describe("bounded editorial queues", () => {
  it("renders one 50-record page from a large store and replaces it on next/previous", async () => {
    const first = Array.from({ length: 50 }, (_, i) => entry(`first-${i}`));
    const second = Array.from({ length: 50 }, (_, i) => entry(`second-${i}`));
    vi.mocked(fetch).mockResolvedValueOnce(response(page(first, 33000)));
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    expect(screen.getByText("Showing 1–50 of 33000 records")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    expect(screen.getAllByText(/^first-\d+$/)).toHaveLength(50);
    vi.mocked(fetch).mockResolvedValueOnce(response(page(second, 33000, 50)));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Showing 51–100 of 33000 records");
    expect(fetch).toHaveBeenLastCalledWith(queueUrl("occurrences", "draft", "", 50), expect.anything());
    expect(screen.queryByText("first-0")).not.toBeInTheDocument();
    expect(screen.getAllByText(/^second-\d+$/)).toHaveLength(50);
    vi.mocked(fetch).mockResolvedValueOnce(response(page(first, 33000)));
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await screen.findByText("Showing 1–50 of 33000 records");
    expect(fetch).toHaveBeenLastCalledWith(queueUrl(), expect.anything());
  });

  it("submits literal search explicitly, resets pagination and preserves search across type/status", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("initial")], 51)));
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("last")], 51, 50)));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Showing 51–51 of 51 records");
    const previousCalls = vi.mocked(fetch).mock.calls.length;
    fireEvent.change(screen.getByLabelText("Search queue"), { target: { value: "  title & stable/id  " } });
    expect(fetch).toHaveBeenCalledTimes(previousCalls);
    fireEvent.click(screen.getByRole("button", { name: "Search queue" }));
    await screen.findByText("Showing 0 of 0 records");
    expect(fetch).toHaveBeenLastCalledWith(queueUrl("occurrences", "draft", "title & stable/id"), expect.anything());
    fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "sources" } });
    await waitFor(() => expect(screen.queryByText("Loading candidate queue…")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenLastCalledWith(queueUrl("sources", "draft", "title & stable/id"), expect.anything());
    expect(screen.getByRole("button", { name: "+ New sources" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Queue status"), { target: { value: "published" } });
    await waitFor(() => expect(screen.queryByText("Loading candidate queue…")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenLastCalledWith(queueUrl("sources", "published", "title & stable/id"), expect.anything());
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("shows a final partial page and does not request beyond has_more", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("first")], 51)));
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("last")], 51, 50)));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Showing 51–51 of 51 records");
    const calls = vi.mocked(fetch).mock.calls.length;
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(fetch).toHaveBeenCalledTimes(calls);
  });

  it("ignores an older queue response after changing record type", async () => {
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    let resolve!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((r) => { resolve = r; }));
    fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "sources" } });
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("current-actor", "actors")])));
    fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "actors" } });
    await screen.findByText("current-actor");
    await act(async () => resolve(response(page([entry("stale-source", "sources")]))));
    expect(screen.queryByText("stale-source")).not.toBeInTheDocument();
    expect(screen.getByText("current-actor")).toBeInTheDocument();
    expect(screen.getByLabelText("Record type")).toHaveValue("actors");
    expect(screen.getByText("Showing 1–1 of 1 records")).toBeInTheDocument();
  });

  it("clears count/search/page on lock and discards a late private queue response", async () => {
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("private-source", "sources")], 51)));
    fireEvent.change(screen.getByLabelText("Record type"), { target: { value: "sources" } });
    await screen.findByText("private-source");
    fireEvent.change(screen.getByLabelText("Search queue"), { target: { value: "private needle" } });
    let resolve!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((r) => { resolve = r; }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Lock workspace" }));
    await act(async () => resolve(response(page([entry("late-private-source", "sources")], 51, 50))));
    expect(screen.getByLabelText("Editor token")).toHaveValue("");
    expect(screen.queryByText("late-private-source")).not.toBeInTheDocument();
    await connect();
    expect(fetch).toHaveBeenLastCalledWith(queueUrl(), expect.anything());
    expect(screen.getByLabelText("Search queue")).toHaveValue("");
    expect(screen.getByLabelText("Record type")).toHaveValue("occurrences");
    expect(screen.getByLabelText("Queue status")).toHaveValue("draft");
    expect(screen.getByText("Showing 0 of 0 records")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("clears old entries and counts after a queue error and allows refresh recovery", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(page([entry("old-private-entry")], 1)));
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    await connect();
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: "sensitive server configuration" }) } as Response);
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));
    await screen.findByText("Editorial service is unavailable or has no configured token.");
    expect(screen.queryByText("old-private-entry")).not.toBeInTheDocument();
    expect(screen.queryByText("Showing 1–1 of 1 records")).not.toBeInTheDocument();
    expect(screen.queryByText("sensitive server configuration")).not.toBeInTheDocument();
    expect(screen.getByText("Queue count unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue" }));
    await screen.findByText("Showing 0 of 0 records");
  });

  it("rejects an unbounded response rather than rendering the entire store", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response(page(Array.from({ length: 51 }, (_, i) => entry(`overflow-${i}`)))));
    render(<Editor data={snapshot} onRefresh={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Editor token"), { target: { value: "test-runtime-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    await screen.findByText("The editorial service returned an unsupported paginated queue response.");
    expect(screen.queryByRole("heading", { name: "Candidate queue" })).not.toBeInTheDocument();
    expect(screen.queryByText("overflow-0")).not.toBeInTheDocument();
  });

  it.each(["publish", "retract", "merge"] as const)("preserves %s revision semantics and reloads the selected typed queue", async (operation) => {
    const refresh = await openActor();
    fireEvent.change(screen.getByLabelText("Reason for this revision"), { target: { value: `Test ${operation}` } });
    if (operation === "merge") { fireEvent.click(screen.getByText("Reconcile duplicate / merge")); fireEvent.change(screen.getByLabelText("Surviving record ID"), { target: { value: "surviving-test-actor" } }); }
    vi.mocked(fetch).mockResolvedValueOnce(response({ ...base, revision: 2 }));
    fireEvent.click(screen.getByRole("button", { name: operation === "publish" ? "Publish saved revision" : operation === "retract" ? "Retract" : "Merge into target" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(fetch).toHaveBeenCalledWith(`${endpoint}/actors/test-actor/${operation}`, expect.objectContaining({ method: "POST", body: JSON.stringify({ expected_revision: 1, reason: `Test ${operation}`, ...(operation === "merge" ? { target_id: "surviving-test-actor" } : {}) }) }));
    expect(fetch).toHaveBeenLastCalledWith(queueUrl("actors"), expect.anything());
  });
});
