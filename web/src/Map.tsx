import { useEffect, useMemo, useState } from "react";
import { geoEqualEarth, geoAlbersUsa, geoPath, geoGraticule10 } from "d3-geo";
import { feature } from "topojson-client";
import type { FeatureCollection, Geometry, Feature } from "geojson";
import type {
  Domain,
  ResearchItem,
  Snapshot,
  Actor,
  Relationship,
} from "./types";
import { title, pretty } from "./data";
import { joinDistricts } from "./geography";
const stateFips: Record<string, string> = {
  "01": "AL",
  "02": "AK",
  "04": "AZ",
  "05": "AR",
  "06": "CA",
  "08": "CO",
  "09": "CT",
  "10": "DE",
  "11": "DC",
  "12": "FL",
  "13": "GA",
  "15": "HI",
  "16": "ID",
  "17": "IL",
  "18": "IN",
  "19": "IA",
  "20": "KS",
  "21": "KY",
  "22": "LA",
  "23": "ME",
  "24": "MD",
  "25": "MA",
  "26": "MI",
  "27": "MN",
  "28": "MS",
  "29": "MO",
  "30": "MT",
  "31": "NE",
  "32": "NV",
  "33": "NH",
  "34": "NJ",
  "35": "NM",
  "36": "NY",
  "37": "NC",
  "38": "ND",
  "39": "OH",
  "40": "OK",
  "41": "OR",
  "42": "PA",
  "44": "RI",
  "45": "SC",
  "46": "SD",
  "47": "TN",
  "48": "TX",
  "49": "UT",
  "50": "VT",
  "51": "VA",
  "53": "WA",
  "54": "WV",
  "55": "WI",
  "56": "WY",
  "72": "PR",
};
const colors: Record<string, string> = {
  reviewed: "#17615d",
  legacy_unverified: "#aa713b",
  unreviewed: "#6c7180",
  certified: "#17615d",
  reported_unofficial: "#7688a1",
  provider_called: "#698788",
  recount: "#b77845",
  contested: "#a35244",
  not_assessed: "url(#unassessed)",
  not_reported: "#d8d7c7",
};
interface Props {
  domain: Domain;
  items: ResearchItem[];
  data: Snapshot;
  selected: string;
  onSelect: (item: ResearchItem) => void;
  onGeo: (geo: string) => void;
  geo: string;
  layer?: string;
}
export function ResearchMap({
  domain,
  items,
  data,
  selected,
  onSelect,
  onGeo,
  geo,
  layer,
}: Props) {
  const [world, setWorld] = useState<FeatureCollection<Geometry> | null>(null),
    [us, setUs] = useState<FeatureCollection<Geometry> | null>(null),
    [error, setError] = useState(""),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState<[number, number]>([0, 0]);
  const [districts, setDistricts] =
      useState<FeatureCollection<Geometry> | null>(null),
    [districtState, setDistrictState] = useState<
      "idle" | "loading" | "ready" | "unavailable"
    >("idle");
  const houseLayer = domain === "elections" && layer === "house";
  useEffect(() => {
    if (!houseLayer || districts) return;
    let active = true;
    setDistrictState("loading");
    fetch(`${import.meta.env.BASE_URL}geometry/districts-2026.geojson`)
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const g = await response.json();
        if (g.type !== "FeatureCollection" || !Array.isArray(g.features))
          throw new Error();
        return g;
      })
      .then((g) => {
        if (active) {
          setDistricts(g);
          setDistrictState("ready");
        }
      })
      .catch(() => {
        if (active) setDistrictState("unavailable");
      });
    return () => {
      active = false;
    };
  }, [houseLayer, districts]);
  const districtJoins = useMemo(
    () => joinDistricts(districts, data.contests),
    [districts, data.contests],
  );
  const joinedIds = new Set(districtJoins.map((j) => j.item.record.id));
  const boundaryStates = new Set(
    districtJoins
      .map((j) => String(j.item.record.state_code))
      .filter((code) =>
        data.contests
          .filter(
            (c) =>
              c.office === "house" &&
              c.state_code === code &&
              c.publication_status === "published",
          )
          .every((c) => joinedIds.has(c.id)),
      ),
  );
  const visibleDistricts = houseLayer
    ? districtJoins.filter(
        (j) =>
          boundaryStates.has(String(j.item.record.state_code)) &&
          items.some(
            (i) => i.kind === "contests" && i.record.id === j.item.record.id,
          ),
      )
    : [];
  const visibleDistrictStates = new Set(
    visibleDistricts.map((j) => String(j.item.record.state_code)),
  );
  const fallbackHouse = houseLayer
    ? items.filter(
        (i) =>
          i.kind === "contests" &&
          i.record.office === "house" &&
          !visibleDistrictStates.has(String(i.record.state_code)),
      )
    : [];
  useEffect(() => {
    let active = true;
    Promise.all(
      ["countries-110m.json", "states-10m.json"].map((name) =>
        fetch(`${import.meta.env.BASE_URL}geometry/${name}`).then((r) => {
          if (!r.ok) throw new Error();
          return r.json();
        }),
      ),
    )
      .then(([w, u]) => {
        if (active) {
          setWorld(
            feature(
              w,
              w.objects.countries,
            ) as unknown as FeatureCollection<Geometry>,
          );
          setUs(
            feature(
              u,
              u.objects.states,
            ) as unknown as FeatureCollection<Geometry>,
          );
        }
      })
      .catch(
        () =>
          active &&
          setError(
            "Map geometry unavailable. All records remain accessible in the results list.",
          ),
      );
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    setZoom(1);
    setPan([0, 0]);
  }, [domain]);
  const projection = useMemo(
    () =>
      domain === "elections"
        ? geoAlbersUsa().translate([460, 240]).scale(1080)
        : geoEqualEarth().translate([460, 242]).scale(166),
    [domain],
  );
  const path = useMemo(() => geoPath(projection), [projection]);
  // Hundreds of district paths have stable projected coordinates. Selection,
  // scope and SVG zoom change their presentation, not their geometry.
  const districtPaths = useMemo(
    () =>
      domain === "elections"
        ? new Map(
            districtJoins.map((j) => [j.item.record.id, path(j.feature) || ""]),
          )
        : new Map<string, string>(),
    [districtJoins, path, domain],
  );
  const actors = new Map(data.actors.map((a) => [a.id, a]));
  const relationships =
    domain === "conflicts"
      ? data.relationships.filter(
          (r) =>
            r.publication_status === "published" &&
            (items.some((i) => i.record.id === r.from_actor_id) ||
              items.some((i) => i.record.id === r.to_actor_id) ||
              items.some((i) => i.record.id === r.id)),
        )
      : [];
  const point = (r: { longitude: unknown; latitude: unknown }) =>
    typeof r.longitude === "number" && typeof r.latitude === "number"
      ? projection([r.longitude, r.latitude])
      : null;
  const visiblePoints = items.filter(
    (i) => i.kind === "actors" || i.kind === "occurrences",
  );
  const national = items.filter((i) => i.record.geography_scope === "national");
  const mappedIds = new Set(
    visiblePoints
      .filter((i) => point(i.record as unknown as Actor))
      .map((i) => i.record.id),
  );
  const states = us?.features || [];
  const mapCountry = (f: Feature) => String(f.properties?.name || "");
  const countryRegions = new Map<
    string,
    { code: string; items: ResearchItem[] }
  >();
  const aliases: Record<string, string> = {
    "United States": "United States of America",
    Türkiye: "Turkey",
    Czechia: "Czech Republic",
    "Congo - Kinshasa": "Dem. Rep. Congo",
    "Congo - Brazzaville": "Congo",
    "South Sudan": "S. Sudan",
  };
  for (const item of items) {
    const codes = [
      ...(item.record.country_code ? [String(item.record.country_code)] : []),
      ...(Array.isArray(item.record.country_codes)
        ? (item.record.country_codes as string[])
        : []),
    ];
    for (const code of codes) {
      let name = String(item.record.country || "");
      try {
        if (!name)
          name =
            new Intl.DisplayNames(["en"], { type: "region" }).of(code) || code;
      } catch {
        name = code;
      }
      name = aliases[name] || name;
      const prior = countryRegions.get(name);
      countryRegions.set(name, {
        code,
        items: [...(prior?.items || []), item],
      });
    }
  }
  return (
    <section
      className={`atlas atlas-${domain}`}
      aria-label={`${domain} geographic view`}
    >
      <div className="atlas-top">
        <span className="eyebrow">
          {domain === "elections"
            ? houseLayer && visibleDistricts.length
              ? "United States / House districts"
              : "United States / state geography"
            : "World / geographic relationships"}
        </span>
        <span className="map-scale">
          {domain === "conflicts"
            ? "Network geography"
            : domain === "protests"
              ? "Documented locations"
              : "Contest reporting status"}
        </span>
      </div>
      <div className="map-controls" aria-label="Map controls">
        <button
          onClick={() => setZoom((z) => Math.min(4, z + 0.5))}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(1, z - 0.5))}
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          onClick={() => {
            setZoom(1);
            setPan([0, 0]);
          }}
          aria-label="Reset map"
        >
          ↺
        </button>
        {zoom > 1 && (
          <>
            <button
              onClick={() => setPan(([x, y]) => [x + 50, y])}
              aria-label="Pan west"
            >
              ←
            </button>
            <button
              onClick={() => setPan(([x, y]) => [x - 50, y])}
              aria-label="Pan east"
            >
              →
            </button>
            <button
              onClick={() => setPan(([x, y]) => [x, y + 50])}
              aria-label="Pan north"
            >
              ↑
            </button>
            <button
              onClick={() => setPan(([x, y]) => [x, y - 50])}
              aria-label="Pan south"
            >
              ↓
            </button>
          </>
        )}
      </div>
      {error ? (
        <div className="empty map-error" role="status">
          {error}
        </div>
      ) : (
        <svg
          viewBox="0 0 920 480"
          role="group"
          aria-label={
            domain === "elections"
              ? houseLayer && visibleDistricts.length
                ? `U.S. House map: ${visibleDistricts.length} version-matched districts, ${fallbackHouse.length} records using state fallback. Districts and states are keyboard selectable; results list provides the same records.`
                : "U.S. state overview. Select a state, or use the accessible results list."
              : "World map with research locations. Use the results list for keyboard selection."
          }
        >
          <defs>
            <pattern
              id="unassessed"
              patternUnits="userSpaceOnUse"
              width="7"
              height="7"
            >
              <rect width="7" height="7" fill="#d1d9cd" />
              <path d="M0,7 L7,0" stroke="#8b9c82" strokeWidth=".8" />
            </pattern>
          </defs>
          <g
            transform={`translate(${pan[0]},${pan[1]}) translate(460,240) scale(${zoom}) translate(-460,-240)`}
          >
            {domain !== "elections" && (
              <path className="graticule" d={path(geoGraticule10()) || ""} />
            )}
            {domain === "elections"
              ? states.map((f) => {
                  const code = stateFips[String(f.id).padStart(2, "0")];
                  const contests = items.filter(
                    (i) =>
                      i.kind === "contests" && i.record.state_code === code,
                  );
                  const actions = items.filter(
                    (i) =>
                      i.kind === "election_actions" &&
                      i.record.state_code === code,
                  );
                  const statuses = new Set(
                    contests.map((i) => String(i.record.status)),
                  );
                  const fill =
                    houseLayer && visibleDistrictStates.has(code)
                      ? "#f5f5e9"
                      : statuses.size === 1
                        ? colors[[...statuses][0]]
                        : statuses.size > 1
                          ? "#9cad9d"
                          : actions.length
                            ? "#a8bfba"
                            : "#f6f5e9";
                  return (
                    <path
                      key={String(f.id ?? f.properties?.name)}
                      className={`land state ${code === geo ? "geo-selected" : ""}`}
                      d={path(f) || ""}
                      style={{ fill }}
                      onClick={() => onGeo(geo === code ? "" : code)}
                      tabIndex={0}
                      role="button"
                      aria-label={`${f.properties?.name}: ${contests.length} included contests, ${actions.length} scoped actions. Select state.`}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onGeo(geo === code ? "" : code);
                        }
                      }}
                    >
                      <title>
                        {String(f.properties?.name)} ·{" "}
                        {contests.length
                          ? `${contests.length} included contests`
                          : "No included contest records; not a no-contest designation"}
                      </title>
                    </path>
                  );
                })
              : (world?.features || []).map((f) => {
                  const region = countryRegions.get(mapCountry(f));
                  const active = domain === "protests" && !!region;
                  return (
                    <path
                      className={`land ${active ? "observed-country" : ""} ${region?.code === geo ? "country-selected" : ""}`}
                      d={path(f) || ""}
                      key={String(f.id ?? f.properties?.name)}
                      onClick={
                        active
                          ? () => onGeo(geo === region.code ? "" : region.code)
                          : undefined
                      }
                      {...(active
                        ? {
                            tabIndex: 0,
                            role: "button",
                            "aria-label": `${mapCountry(f)}: ${region.items.length} included observations or campaigns. Country context only.`,
                            onKeyDown: (e: React.KeyboardEvent) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                onGeo(geo === region.code ? "" : region.code);
                              }
                            },
                          }
                        : {})}
                    >
                      <title>
                        {mapCountry(f)}
                        {active
                          ? ` · ${region.items.length} included records · country context, not precise locations`
                          : ""}
                      </title>
                    </path>
                  );
                })}
            {visibleDistricts.map(({ item }) => (
              <path
                key={item.record.id}
                className={`land district ${item.record.id === selected ? "district-selected" : ""}`}
                d={districtPaths.get(item.record.id) || ""}
                style={{
                  fill:
                    colors[String(item.record.status)] || "url(#unassessed)",
                }}
                onClick={() => onSelect(item)}
                role="button"
                tabIndex={0}
                aria-label={`${title(item.record)}: ${pretty(item.record.status)}. ${pretty(item.record.evidence_status)}. Select contest.`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(item);
                  }
                }}
              >
                <title>
                  {title(item.record)} · {pretty(item.record.status)} ·{" "}
                  {String(item.record.geography_version)}
                </title>
              </path>
            ))}
            {relationships.map((r: Relationship) => {
              const a = actors.get(r.from_actor_id),
                b = actors.get(r.to_actor_id);
              if (!a || !b) return null;
              const active =
                r.id === selected || a.id === selected || b.id === selected;
              return (
                <path
                  key={r.id}
                  className={`relationship ${active ? "active" : ""}`}
                  d={
                    path({
                      type: "LineString",
                      coordinates: [
                        [a.longitude, a.latitude],
                        [b.longitude, b.latitude],
                      ],
                    }) || ""
                  }
                  onClick={() =>
                    onSelect({
                      kind: "relationships",
                      domain: "conflicts",
                      record: r,
                    })
                  }
                >
                  <title>
                    {title(a)} → {title(b)} · {pretty(r.relationship_type)} ·{" "}
                    {pretty(r.evidence_status)}
                  </title>
                </path>
              );
            })}
            {visiblePoints.map((item) => {
              const p = point(item.record as unknown as Actor);
              if (!p) return null;
              const active = item.record.id === selected;
              return (
                <g
                  key={item.record.id}
                  className={`map-point ${active ? "selected" : ""}`}
                  transform={`translate(${p[0]},${p[1]})`}
                  onClick={() => onSelect(item)}
                >
                  <title>
                    {title(item.record)} · {pretty(item.record.evidence_status)}
                    {item.record.location_precision
                      ? ` · ${pretty(item.record.location_precision)} precision`
                      : ""}
                  </title>
                  {active && <circle r="14" className="selection-ring" />}
                  <circle
                    r={active ? 6 : 4.2}
                    fill={colors[item.record.evidence_status] || "#17615d"}
                  />
                  {active && (
                    <text x="10" y="-10">
                      {title(item.record)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      )}
      <div className="atlas-footer">
        <div className="map-legend">
          {domain === "elections" ? (
            <>
              <span>
                <i style={{ background: "#17615d" }} />
                Certified
              </span>
              <span>
                <i style={{ background: "#7688a1" }} />
                Unofficial
              </span>
              <span>
                <i style={{ background: "#9cad9d" }} />
                Mixed statuses
              </span>
              <span>
                <i className="hatch" />
                Not assessed
              </span>
              <span>
                <i style={{ background: "#d8d7c7" }} />
                Not reported
              </span>
              <span>
                <i
                  style={{ background: "#f6f5e9", border: "1px solid #bfc7ba" }}
                />
                No included record
              </span>
              {["provider_called", "recount", "contested"]
                .filter((status) =>
                  items.some((i) => i.record.status === status),
                )
                .map((status) => (
                  <span key={status}>
                    <i style={{ background: colors[status] }} />
                    {pretty(status)}
                  </span>
                ))}
            </>
          ) : (
            <>
              <span>
                <i style={{ background: "#17615d" }} />
                Reviewed
              </span>
              <span>
                <i style={{ background: "#aa713b" }} />
                Inherited / unverified
              </span>
              <span>
                <i style={{ background: "#6c7180" }} />
                Unreviewed
              </span>
            </>
          )}
        </div>
        <span>
          {domain === "elections"
            ? houseLayer && visibleDistricts.length
              ? `${visibleDistricts.length} version-matched House districts${fallbackHouse.length ? ` · ${fallbackHouse.length} state fallbacks` : ""}`
              : "State overview; district boundaries unavailable for this layer"
            : `${mappedIds.size} mapped ${domain === "conflicts" ? "actors" : "observations"}`}
        </span>
      </div>
      {domain === "elections" && (
        <p className="map-note">
          {houseLayer && visibleDistricts.length
            ? "House shapes use the official plan vintage matched to each contest. Records with unavailable or mismatched plans retain a state overview."
            : houseLayer && districtState === "loading"
              ? "Loading verified House geometry. State overview is shown until the plan match is checked."
              : "House records are grouped by state where a matching verified district plan is unavailable."}{" "}
          No included report ≠ no contest.{" "}
          {national.length > 0 &&
            `${national.length} nationwide actions remain in the chronology; they are not placed in Washington.`}
        </p>
      )}
      {domain === "protests" && (
        <div className="country-shading-note">
          Shading shows countries with included observations or campaigns.
          Points, when available, retain their stated precision.
        </div>
      )}
      {domain === "protests" &&
        items.some(
          (i) => i.kind === "occurrences" && !mappedIds.has(i.record.id),
        ) && (
          <p className="map-note">
            Observations without coordinates appear in the list. Country/region
            descriptions are not converted into precise locations.
          </p>
        )}
    </section>
  );
}
