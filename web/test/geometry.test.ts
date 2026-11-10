import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";
import { feature } from "topojson-client";
import type { FeatureCollection } from "geojson";
describe("locally bundled map identity", () => {
  it("provides unique identities for country features without numeric ids", () => {
    const topology = JSON.parse(readFileSync("public/geometry/countries-110m.json", "utf8"));
    const countries = feature(topology, topology.objects.countries) as unknown as FeatureCollection;
    const keys = countries.features.map(f => String(f.id ?? f.properties?.name));
    expect(new Set(keys).size).toBe(countries.features.length);
    expect(keys).not.toContain("undefined");
    expect(countries.features.some(f => !f.id)).toBe(true);
  });
});
