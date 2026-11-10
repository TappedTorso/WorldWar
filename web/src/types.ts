export type Domain = "conflicts" | "protests" | "elections";
export type EvidenceStatus = "reviewed" | "legacy_unverified" | "unreviewed";
export interface BaseRecord {
  source_snapshots?: Source[];
  id: string;
  title: string;
  summary: string;
  source_ids: string[];
  evidence_status: EvidenceStatus;
  publication_status: "published" | "retracted" | "merged" | "draft";
  revision: number;
  reviewed_at: string | null;
  updated_at: string | null;
  legacy_citation_text?: string[];
  legacy_updated_at?: string | null;
  legacy_confidence?: string | null;
  legacy_payload?: unknown;
  merged_into?: string;
  [key: string]: unknown;
}
export interface Actor extends BaseRecord {
  name: string;
  actor_type: string;
  country_code: string | null;
  longitude: number;
  latitude: number;
  theaters: string[];
  category: string;
}
export interface Relationship extends BaseRecord {
  from_actor_id: string;
  to_actor_id: string;
  relationship_type: string;
  category: string;
  theaters: string[];
  valid_from: string | null;
  valid_to: string | null;
}
export interface Development extends BaseRecord {
  actor_ids: string[];
  occurred_start: string | null;
  occurred_end: string | null;
  date_precision: string;
  development_type:
    | "reported_development"
    | "assessment_revision"
    | "discovery_article";
  url: string | null;
  discovered_at?: string | null;
}
export interface Occurrence extends BaseRecord {
  country_code: string;
  country: string;
  place_name: string;
  longitude: number | null;
  latitude: number | null;
  location_precision: string;
  occurred_start: string;
  occurred_end: string | null;
  date_precision: string;
  action_type: string;
  demands: string[];
  targets: string[];
  campaign_ids: string[];
  inclusion_rationale: string;
  confidence_note: string;
}
export interface Campaign extends BaseRecord {
  country_codes: string[];
  started_at: string | null;
  ended_at: string | null;
  demands: string[];
  targets: string[];
  occurrence_ids: string[];
}
export interface Connection extends BaseRecord {
  from_id: string;
  to_id: string;
  connection_type: string;
  evidence_note: string;
}
export interface Contest extends BaseRecord {
  office: "house" | "senate";
  cycle: number;
  state_code: string;
  jurisdiction: string;
  district: string | null;
  geography_version: string | null;
  boundary_status: string;
  status:
    | "not_assessed"
    | "not_reported"
    | "reported_unofficial"
    | "provider_called"
    | "certified"
    | "recount"
    | "contested";
  result_as_of: string | null;
  election_date: string;
  candidates: {
    name: string;
    party: string;
    votes: number | null;
    percentage: number | null;
  }[];
  winner: string | null;
  winner_basis: string | null;
  total_votes: number | null;
  reporting_note: string;
  longitude: number | null;
  latitude: number | null;
}
export interface ElectionAction extends BaseRecord {
  action_type: string;
  actor: string;
  jurisdiction: string;
  state_code: string | null;
  geography_scope: "national" | "state" | "district";
  occurred_start: string;
  occurred_end: string | null;
  date_precision: string;
  procedural_status: string;
  claim_status: string;
  effect_claim: string | null;
  effect_evidence: string | null;
  intent_claim: string | null;
  intent_evidence: string | null;
  related_contest_ids: string[];
}
export interface PoliticalContext extends BaseRecord {
  domain: Domain;
  jurisdiction: string;
  country_code: string | null;
  state_code: string | null;
  as_of: string;
  context_type: string;
  related_ids: string[];
}
export interface Source {
  withdrawn_status?: "retracted" | "merged";
  publication_status?: "published" | "retracted" | "merged";
  merged_into?: string;
  revision?: number;
  id: string;
  title: string;
  url: string | null;
  publisher: string;
  source_type: string;
  published_at: string | null;
  retrieved_at: string | null;
  published_date?: string | null;
  retrieved_date?: string | null;
  retrieval_date?: string | null;
  publication_precision?: string;
  retrieval_precision?: string;
  published_precision?: string;
  retrieved_precision?: string;
  rights: string;
  note: string;
  source_updated_at?: string;
  language?: string;
}
export interface Coverage {
  id: string;
  domain: Domain;
  geography: string;
  country_code: string | null;
  state_code: string | null;
  period_start: string;
  period_end: string;
  status: "reviewed" | "partial" | "not_assessed" | "unavailable";
  source_ids: string[];
  note: string;
  reviewed_at: string | null;
}
export interface Job {
  id: string;
  adapter: string;
  domain: Domain;
  started_at: string;
  completed_at: string | null;
  status: "ok" | "partial" | "error";
  fetched_count: number;
  accepted_count: number;
  error: string | null;
}
export interface Scorecard {
  id: string;
  geography: string;
  country_code: string;
  period_start: string;
  period_end: string;
  occurrence_count: number;
  active_days: number;
  location_count: number;
  campaign_count: number;
  comparison_start: string;
  comparison_end: string;
  previous_occurrence_count: number | null;
  momentum: "insufficient_data" | "increased" | "decreased" | "unchanged";
  coverage_status: string;
  method_version: string;
  calculated_at: string;
  input_ids: string[];
  note: string;
}
export interface Snapshot {
  tombstones?: Array<{ kind: string; record: BaseRecord | Source }>;
  schema_version: string;
  meta: {
    generated_at: string | null;
    data_version: string;
    legacy_reviewed_at: string | null;
    coverage_summary: string;
    publication_mode: string;
    discovery_total?: number;
    discovery_visible?: number;
  };
  actors: Actor[];
  relationships: Relationship[];
  developments: Development[];
  occurrences: Occurrence[];
  campaigns: Campaign[];
  connections: Connection[];
  contests: Contest[];
  election_actions: ElectionAction[];
  political_context: PoliticalContext[];
  sources: Source[];
  coverage: Coverage[];
  jobs: Job[];
  scorecards: Scorecard[];
}
export const recordKinds = [
  "actors",
  "relationships",
  "developments",
  "occurrences",
  "campaigns",
  "connections",
  "contests",
  "election_actions",
  "political_context",
] as const;
export type RecordKind = (typeof recordKinds)[number];
export interface ResearchItem {
  kind: RecordKind;
  domain: Domain;
  record: BaseRecord;
}
