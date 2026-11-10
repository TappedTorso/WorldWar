import { useSyncExternalStore } from "react";
import type { Domain, ResearchItem } from "./types";
export const sections = [
  "overview",
  "conflicts",
  "protests",
  "elections",
  "data",
  "editor",
] as const;
export type Section = (typeof sections)[number];
const decode = (value: string) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};
export function parseRoute(hash: string) {
  if (hash.startsWith("#node="))
    return {
      section: "conflicts" as Section,
      kind: "actors",
      id: decode(hash.slice(6)),
      params: new URLSearchParams(),
    };
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const [raw, kind, id] = path.split("/");
  return {
    section: (sections.includes(raw as Section) ? raw : "overview") as Section,
    kind: kind || "",
    id: id ? decode(id) : "",
    params: new URLSearchParams(query),
  };
}
const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};
export function useRoute() {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => "#/overview",
  );
  return parseRoute(hash);
}
export function routeTo(
  section: Section,
  params = new URLSearchParams(),
  kind = "",
  id = "",
) {
  const query = params.toString();
  return `#/${section}${kind ? "/" + kind : ""}${id ? "/" + encodeURIComponent(id) : ""}${query ? "?" + query : ""}`;
}
export function itemRoute(item: ResearchItem, params = new URLSearchParams()) {
  return routeTo(item.domain, params, item.kind, item.record.id);
}
export function updateFilter(
  section: Section,
  params: URLSearchParams,
  key: string,
  value: string,
) {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  const current = parseRoute(window.location.hash);
  window.location.hash = routeTo(
    section,
    next,
    current.section === section ? current.kind : "",
    current.section === section ? current.id : "",
  );
}
export function domainLabel(domain: Domain) {
  return domain === "elections"
    ? "U.S. Elections"
    : domain[0].toUpperCase() + domain.slice(1);
}
