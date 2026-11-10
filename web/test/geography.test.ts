import { describe, it, expect } from "vitest";
import type { FeatureCollection, Geometry } from "geojson";
import { joinDistricts, worldGeometryName } from "../src/geography";
import { geoArea } from "d3-geo";
import { contest } from "./fixtures";
const record = {
  ...contest,
  geography_version: "census-current-test-plan",
  boundary_status: "verified_current_plan",
};
const geometry: FeatureCollection<Geometry> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: record.id,
      properties: {
        contest_id: record.id,
        state_code: "CA",
        district: "01",
        geography_version: "census-current-test-plan",
        boundary_status: "verified_current_plan",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-123, 38],
            [-122, 38],
            [-122, 39],
            [-123, 38],
          ],
        ],
      },
    },
  ],
};
describe("House boundary validation", () => {
  it("renders small districts rather than their spherical complement regardless of source ring winding", () => {
    expect(geoArea(joinDistricts(geometry, [record])[0].feature)).toBeLessThan(
      0.01,
    );
  });
  it("joins a verified matching contest and normalizes district numbering", () =>
    expect(
      joinDistricts(geometry, [record]).map((d) => d.item.record.id),
    ).toEqual([contest.id]));
  it("rejects mismatched vintage, state, district, or unavailable status", () => {
    for (const change of [
      { geography_version: "older-plan" },
      { state_code: "NY" },
      { district: "2" },
      { boundary_status: "unavailable" },
      { geography_version: null },
    ])
      expect(
        joinDistricts(geometry, [{ ...record, ...change } as typeof record]),
      ).toHaveLength(0);
  });
  it("never substitutes geography when no verified collection is available", () =>
    expect(joinDistricts(null, [record])).toEqual([]));
});

import { readFileSync } from "node:fs";
import { geoPath, geoAlbersUsa } from "d3-geo";
it("joins reporting codes to the actual bundled world shapes despite source naming differences", () => {
  const topology = JSON.parse(readFileSync("public/geometry/countries-110m.json", "utf8"));
  const names = topology.objects.countries.geometries.map((g: { properties: { name: string } }) => g.properties.name);
  for (const code of ["CZ", "CI", "SZ", "MK", "CD", "CG", "MM", "TR", "PS", "EH", "SB", "BA", "DO", "US"])
    expect(names.filter((name: string) => name === worldGeometryName(code))).toHaveLength(1);
  expect(worldGeometryName("CY")).not.toBe("N. Cyprus");
});
describe("bundled official House display baseline", () => {
  it("contains435unique voting seats,50states and the explicit Missouri source exception", () => {
    const asset = JSON.parse(
      readFileSync("public/geometry/districts-2026.geojson", "utf8"),
    ) as FeatureCollection<Geometry>;
    expect(asset.features).toHaveLength(435);
    expect(new Set(asset.features.map((f) => f.id)).size).toBe(435);
    expect(
      new Set(asset.features.map((f) => f.properties?.state_code)).size,
    ).toBe(50);
    const mo = asset.features.filter((f) => f.properties?.state_code === "MO");
    expect(mo).toHaveLength(8);
    expect(
      mo.every(
        (f) => f.properties?.geography_version === "census_tiger_2025_cd119",
      ),
    ).toBe(true);
    expect(
      asset.features
        .filter((f) => f.properties?.state_code !== "MO")
        .every(
          (f) => f.properties?.geography_version === "census_tiger_2026_cd120",
        ),
    ).toBe(true);
  });
  it("normalizes all official polygons to finite small shapes without mutating canonical RFC7946 coordinates", () => {
    const asset = JSON.parse(
      readFileSync("public/geometry/districts-2026.geojson", "utf8"),
    ) as FeatureCollection<Geometry>;
    const before = JSON.stringify(asset);
    const records = asset.features.map((f) => ({
      ...contest,
      id: String(f.id),
      state_code: f.properties?.state_code,
      district: f.properties?.district,
      geography_version: f.properties?.geography_version,
      boundary_status: f.properties?.boundary_status,
    }));
    const joined = joinDistricts(asset, records);
    expect(joined).toHaveLength(435);
    const path = geoPath(geoAlbersUsa());
    for (const j of joined) {
      expect(geoArea(j.feature)).toBeLessThan(2 * Math.PI);
      const d = path(j.feature);
      expect(d).toBeTruthy();
      expect(d).not.toContain("NaN");
    }
    expect(JSON.stringify(asset)).toBe(before);
  });
});
