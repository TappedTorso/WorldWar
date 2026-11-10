import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { Contest, ResearchItem } from "./types";
import { geoArea } from "d3-geo";
export interface JoinedDistrict {
  feature: Feature<Geometry>;
  item: ResearchItem;
}
// Matching a stable contest ID is necessary but insufficient: the state, district
// and explicitly verified plan vintage must agree before a result colors a shape.
export function joinDistricts(
  geometry: FeatureCollection<Geometry> | null,
  contests: Contest[],
): JoinedDistrict[] {
  if (!geometry) return [];
  const records = new Map(
    contests
      .filter(
        (c) => c.publication_status === "published" && c.office === "house",
      )
      .map((c) => [c.id, c]),
  );
  return geometry.features.flatMap((feature) => {
    const p = feature.properties || {},
      r = records.get(String(p.contest_id || feature.id || ""));
    if (
      !r ||
      !r.geography_version ||
      !p.geography_version ||
      r.geography_version !== p.geography_version ||
      r.state_code !== p.state_code ||
      r.district === null ||
      String(Number(r.district)) !== String(Number(p.district))
    )
      return [];
    if (
      !r.boundary_status ||
      !p.boundary_status ||
      /(unavailable|unverified|not_yet|mismatch|pending|unknown)/i.test(
        `${r.boundary_status} ${p.boundary_status}`,
      )
    )
      return [];
    if (!["Polygon", "MultiPolygon"].includes(feature.geometry.type)) return [];
    return [
      {
        feature: orientDistrict(feature),
        item: {
          kind: "contests" as const,
          domain: "elections" as const,
          record: r,
        },
      },
    ];
  });
}

// GeoJSON sources may use either exterior-ring winding convention. D3 spherical
// paths expect clockwise small polygons; otherwise a district can paint the
// globe's complement. Preserve the geometry, normalize only render winding.
function orientDistrict(feature: Feature<Geometry>): Feature<Geometry> {
  const g = feature.geometry;
  if (g.type !== "Polygon" && g.type !== "MultiPolygon") return feature;
  const polygons = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  const normalized = polygons.map((p) =>
    geoArea({ type: "Polygon", coordinates: [p[0]] }) > 2 * Math.PI
      ? p.map((r) => [...r].reverse())
      : p,
  );
  return {
    ...feature,
    geometry:
      g.type === "Polygon"
        ? { type: "Polygon", coordinates: normalized[0] }
        : { type: "MultiPolygon", coordinates: normalized },
  };
}
