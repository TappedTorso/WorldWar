import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { snapshot, actor } from "./fixtures";
vi.mock("../src/data", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/data")>()),
  apiBase: "http://localhost:9999",
}));
import { App } from "../src/App";
describe("public stable IDs outside bounded snapshot", () => {
  it("resolves a public tombstone and its pinned evidence through the API", async () => {
    window.location.hash = "#/conflicts/actors/retired-actor?view=detail";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url.endsWith("/snapshot") || url.includes("research.json"))
          return { ok: true, json: async () => snapshot };
        if (url.includes("/records/actors/retired-actor"))
          return {
            ok: true,
            json: async () => ({
              kind: "actors",
              record: {
                ...actor,
                id: "retired-actor",
                name: "Retired actor",
                publication_status: "merged",
                merged_into: "test-actor",
              },
              sources: [
                { ...snapshot.sources[0], title: "Pinned historical evidence" },
              ],
              revisions: [
                {
                  revision: 2,
                  action: "merge",
                  created_at: "2026-11-10T00:00:00Z",
                },
              ],
            }),
          };
        return { ok: false, status: 404 };
      }),
    );
    render(<App />);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Retired actor" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open surviving record →" }),
    ).toHaveAttribute("href", "#/conflicts/actors/test-actor");
    expect(
      screen.getByRole("link", { name: "Pinned historical evidence ↗" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Test source ↗" }),
    ).not.toBeInTheDocument();
    expect(JSON.stringify(vi.mocked(fetch).mock.calls)).not.toContain(
      "Authorization",
    );
  });
});

describe("full public archive discovery", () => {
  it("searches beyond the bundled snapshot without inventing evidence status", async () => {
    window.location.hash = "#/overview";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url.includes("research.json") || url.endsWith("/snapshot"))
          return { ok: true, json: async () => snapshot };
        if (url.includes("/api/v1/search?q=archive"))
          return {
            ok: true,
            json: async () => ({
              items: [
                {
                  id: "archive-only-record",
                  domain: "conflicts",
                  kind: "developments",
                  title: "Archived discovery test",
                  summary: "Synthetic search-only metadata",
                  route: "#/conflicts/developments/archive-only-record",
                },
              ],
            }),
          };
        return { ok: false, status: 404 };
      }),
    );
    render(<App />);
    await screen.findByText("Follow the threads.");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.change(screen.getByLabelText("Search the research archive"), {
      target: { value: "archive" },
    });
    const result = await screen.findByRole("link", {
      name: /Archived discovery test/,
    });
    expect(result).toHaveAttribute(
      "href",
      "#/conflicts/developments/archive-only-record",
    );
    expect(result).toHaveTextContent("Evidence state in record");
    expect(result).not.toHaveTextContent("reviewed");
  });
});
