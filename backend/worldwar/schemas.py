"""Version 1 typed research records. Unknown input keys fail closed."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=20000)]
Domain = Literal['conflicts', 'protests', 'elections']


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def valid_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('source URL must be HTTP(S), without embedded credentials')
    if any(k.lower() in ('token', 'access_token', 'api_key', 'apikey', 'password', 'secret', 'authorization') for k, _ in parse_qsl(parsed.query)):
        raise ValueError('source URL must not contain credential query parameters')
    if any(ord(c) < 32 for c in value) or any(c.isspace() for c in parsed.netloc):
        raise ValueError('control characters are not valid in URLs')
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='after')
    def time_order(self):
        for name in type(self).model_fields:
            value = getattr(self, name, None)
            if name.endswith('_ids') and isinstance(value, list) and len(value) != len(set(value)):
                raise ValueError(f'duplicate IDs in {name}')
        for start, end in [('occurred_start', 'occurred_end'), ('period_start', 'period_end'),
                           ('valid_from', 'valid_to'), ('started_at', 'ended_at')]:
            a, b = getattr(self, start, None), getattr(self, end, None)
            if a is not None and b is not None and a > b:
                raise ValueError(f'{end} precedes {start}')
        return self

    @field_validator('*', mode='after')
    @classmethod
    def normalize_time(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError('datetime must include a timezone')
            return value.astimezone(timezone.utc)
        return value


class Shared(StrictModel):
    id: ID
    title: Text
    summary: str = Field(default='', max_length=20000)
    source_ids: list[ID] = Field(default_factory=list)
    evidence_status: Literal['reviewed', 'legacy_unverified', 'unreviewed'] = 'unreviewed'
    review_method: Literal['human_review', 'validated_official_adapter', 'research_agent_source_review'] | None = None
    publication_status: Literal['published', 'retracted', 'merged'] = 'published'
    revision: int = Field(default=0, ge=0)
    reviewed_at: datetime | None = None
    updated_at: datetime | None = None
    legacy_citation_text: list[str] = Field(default_factory=list)
    legacy_confidence: str | None = None
    legacy_updated_at: str | None = None
    legacy_payload: dict[str, Any] | None = None
    merged_into: ID | None = None
    publication_changed_at: datetime | None = None

    @field_validator('source_ids')
    @classmethod
    def unique_sources(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate source IDs')
        return value


class Actor(Shared):
    name: Text
    actor_type: str
    country_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    theaters: list[str] = Field(default_factory=list)
    category: str


class Relationship(Shared):
    from_actor_id: ID
    to_actor_id: ID
    relationship_type: str
    category: str
    theaters: list[str] = Field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None


class Development(Shared):
    actor_link_note: str | None = None
    attribution: str | None = None
    causal_connections: list[ID] = Field(default_factory=list)
    evidence_locator: str | None = None
    development_subtype: str | None = None
    legacy_assertion_reverified: bool = False
    actor_ids: list[ID] = Field(default_factory=list)
    occurred_start: date | None = None
    occurred_end: date | None = None
    date_precision: Literal['day', 'range', 'month', 'unknown'] = 'unknown'
    development_type: Literal['reported_development', 'assessment_revision', 'discovery_article']
    url: str | None = None
    discovered_at: datetime | None = None
    published_at: datetime | None = None
    provider_seen_raw: str | None = None
    _url = field_validator('url')(valid_url)

    @model_validator(mode='after')
    def discovery_status(self):
        if self.development_type == 'discovery_article' and self.evidence_status != 'unreviewed':
            raise ValueError('discovery articles must remain unreviewed; create a reviewed development separately')
        return self


class CrowdEstimate(StrictModel):
    value: int = Field(ge=0)
    qualifier: Literal['more_than', 'less_than', 'approximately', 'reported']
    attribution: Text
    source_id: ID


class Occurrence(Shared):
    evidence_locator: str | None = None
    causal_connections: list[ID] = Field(default_factory=list)
    time_local_raw: str | None = None
    purpose: str | None = None
    event_scope: str | None = None
    reported_ongoing_as_of: date | None = None
    country_code: str = Field(pattern=r'^[A-Z]{2}$')
    country: Text
    place_name: Text
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    location_precision: Literal['point', 'city', 'region', 'country', 'unknown']
    occurred_start: date
    occurred_end: date | None = None
    date_precision: Literal['day', 'range', 'month', 'unknown']
    action_type: Text
    demands: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    campaign_ids: list[ID] = Field(default_factory=list)
    inclusion_rationale: Text
    confidence_note: str = ''
    count_eligible: bool = True
    active_dates: list[date] = Field(default_factory=list)
    attribution: str | None = None
    attribution_note: str | None = None
    organisers: list[str] | None = None
    location_note: str | None = None
    crowd_estimates: list[CrowdEstimate] = Field(default_factory=list)
    participants: str | None = None
    response: str | None = None
    outcome: str | None = None

    @model_validator(mode='after')
    def location_and_start(self):
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError('coordinates must be supplied as a pair')
        if self.location_precision == 'point' and self.longitude is None:
            raise ValueError('point precision requires coordinates')
        if self.date_precision == 'day' and self.occurred_end not in (None, self.occurred_start):
            raise ValueError('day precision cannot describe a multi-day interval')
        if len(set(self.active_dates)) != len(self.active_dates):
            raise ValueError('duplicate documented active dates')
        if any(d < self.occurred_start or d > (self.occurred_end or self.occurred_start) for d in self.active_dates):
            raise ValueError('documented active dates must fall within the observation interval')
        if self.occurred_start < date(2026, 9, 1):
            raise ValueError('protest observation scope starts September 1, 2026')
        return self


class Campaign(Shared):
    count_eligible: bool = False
    causal_connections: list[ID] = Field(default_factory=list)
    inclusion_rationale: str | None = None
    evidence_locator: str | None = None
    places_reported: list[str] = Field(default_factory=list)
    date_uncertainty: str | None = None
    campaign_scope: str | None = None
    action_mix: list[str] = Field(default_factory=list)
    reported_through: date | None = None
    date_precision: Literal['day', 'range', 'month', 'unknown'] = 'unknown'
    coverage_note: str = ''
    country_codes: list[str] = Field(default_factory=list)
    started_at: date | None = None
    ended_at: date | None = None
    demands: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    occurrence_ids: list[ID] = Field(default_factory=list)


class Connection(Shared):
    from_id: ID
    to_id: ID
    connection_type: Text
    evidence_note: Text


class Candidate(StrictModel):
    name: Text
    party: str | None = None
    votes: int | None = Field(default=None, ge=0, strict=True)
    percentage: float | None = Field(default=None, ge=0, le=100)


class Contest(Shared):
    office: Literal['house', 'senate']
    cycle: Literal[2026] = 2026
    election_stage: Literal['general', 'primary', 'runoff', 'special'] = 'general'
    state_code: str = Field(pattern=r'^[A-Z]{2}$')
    jurisdiction: Text
    district: str | None = None
    geography_version: Text | None = None
    boundary_status: Text
    status: Literal['not_assessed', 'not_reported', 'reported_unofficial', 'provider_called', 'certified', 'recount', 'contested']
    result_as_of: datetime | None = None
    result_as_of_raw: str | None = None
    election_date: date
    candidates: list[Candidate] = Field(default_factory=list)
    winner: str | None = None
    winner_basis: str | None = None
    total_votes: int | None = Field(default=None, ge=0, strict=True)
    reporting_note: str = ''
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)

    @model_validator(mode='after')
    def result_semantics(self):
        if self.winner is not None and (not self.winner_basis or not self.source_ids):
            raise ValueError('winner requires a distinct sourced winner_basis')
        if self.winner is not None and self.status in ('not_assessed', 'not_reported', 'reported_unofficial'):
            raise ValueError('unassessed/unreported/unofficial tallies do not establish a winner')
        if self.status in ('not_assessed', 'not_reported'):
            if self.total_votes is not None or any(c.votes is not None for c in self.candidates):
                raise ValueError('missing reports are not zero results')
        if any(c.votes is not None for c in self.candidates) or self.total_votes is not None:
            if self.result_as_of is None and not self.result_as_of_raw:
                raise ValueError('reported vote totals require result_as_of or explicitly unresolved raw source date')
        if self.winner and self.winner not in {c.name for c in self.candidates}:
            raise ValueError('winner must identify a listed candidate')
        if len({c.name for c in self.candidates}) != len(self.candidates):
            raise ValueError('duplicate candidate names')
        if self.total_votes is not None and sum(c.votes or 0 for c in self.candidates) > self.total_votes:
            raise ValueError('candidate votes exceed contest total')
        return self


class ElectionAction(Shared):
    allegation_note: str | None = None
    boundary_plan: str | None = None
    case_id: str | None = None
    causal_connections: list[ID] = Field(default_factory=list)
    current_case_status: str | None = None
    evidence_locator: str | None = None
    legal_effective_date_as_stated: date | None = None
    status_as_of: date | None = None
    current_operative_status: str | None = None
    action_type: Text
    actor: Text
    jurisdiction: Text
    state_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    geography_scope: Literal['national', 'state', 'district']
    occurred_start: date
    occurred_end: date | None = None
    date_precision: Literal['day', 'range', 'month', 'unknown']
    procedural_status: Text
    claim_status: Literal['documented_action', 'attributed_allegation', 'analysis', 'court_finding']
    effect_claim: str | None = None
    effect_evidence: str | None = None
    intent_claim: str | None = None
    intent_evidence: str | None = None
    related_contest_ids: list[ID] = Field(default_factory=list)

    @model_validator(mode='after')
    def attributed_claims(self):
        if self.effect_claim and not self.effect_evidence:
            raise ValueError('effect claims need attributed evidence')
        if self.intent_claim and not self.intent_evidence:
            raise ValueError('intent claims need attributed evidence')
        return self


class PoliticalContext(Shared):
    domain: Domain
    jurisdiction: Text
    country_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    state_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    as_of: date
    context_type: Text
    related_ids: list[ID] = Field(default_factory=list)


class Source(StrictModel):
    source_updated_date: date | None = None
    published_time_raw: str | None = None
    access_status: str | None = None
    document_date: date | None = None
    evidence_locator: str | None = None
    source_date_not_occurrence_date: bool = True
    reviewed_at: datetime | None = None
    id: ID
    title: Text
    url: str | None
    publisher: Text
    source_type: Literal['official', 'primary', 'reporting', 'legacy_reference', 'discovery']
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    published_date: date | None = None
    retrieval_date: date | None = None
    publication_precision: Literal['timestamp', 'microsecond', 'second', 'day', 'unknown'] = 'unknown'
    retrieval_precision: Literal['timestamp', 'microsecond', 'second', 'day', 'unknown'] = 'unknown'
    source_tier: str | None = None
    source_updated_at_raw: str | None = None
    rights: Text
    note: str = ''
    source_updated_at: datetime | None = None
    language: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    revision: int = Field(default=0, ge=0)
    publication_status: Literal['published', 'retracted', 'merged'] = 'published'
    merged_into: ID | None = None
    publication_changed_at: datetime | None = None
    _url = field_validator('url')(valid_url)

    @model_validator(mode='after')
    def source_url(self):
        if self.url is None and self.source_type != 'legacy_reference':
            raise ValueError('nonlegacy sources require a URL')
        for timestamp, day, precision_name in [('published_at', 'published_date', 'publication_precision'), ('retrieved_at', 'retrieval_date', 'retrieval_precision')]:
            instant, calendar = getattr(self, timestamp), getattr(self, day)
            precision = getattr(self, precision_name)
            if instant is not None:
                if precision == 'day':
                    raise ValueError('day precision must preserve a calendar date without a fabricated timestamp')
                if precision == 'unknown':
                    setattr(self, precision_name, 'timestamp')
                if calendar is not None and instant.date() != calendar:
                    raise ValueError('source timestamp and calendar date disagree')
            elif calendar is not None:
                if precision not in ('day', 'unknown'):
                    raise ValueError('calendar-only date cannot claim timestamp precision')
                setattr(self, precision_name, 'day')
            elif precision != 'unknown':
                raise ValueError('unknown date cannot claim known precision')
        return self


class Coverage(StrictModel):
    assessment_method: str | None = None
    search_audit_key: str | None = None
    id: ID
    domain: Domain
    geography: Text
    country_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    state_code: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    period_start: date
    period_end: date
    status: Literal['reviewed', 'partial', 'not_assessed', 'unavailable']
    source_ids: list[ID] = Field(default_factory=list)
    note: Text
    reviewed_at: datetime | None = None
    revision: int = Field(default=0, ge=0)
    publication_status: Literal['published', 'retracted', 'merged'] = 'published'
    merged_into: ID | None = None
    publication_changed_at: datetime | None = None


KINDS = {
    'actors': Actor, 'relationships': Relationship, 'developments': Development,
    'occurrences': Occurrence, 'campaigns': Campaign, 'connections': Connection,
    'contests': Contest, 'election_actions': ElectionAction, 'political_context': PoliticalContext,
    'sources': Source, 'coverage': Coverage,
}
DOMAINS = {'actors': 'conflicts', 'relationships': 'conflicts', 'developments': 'conflicts',
           'occurrences': 'protests', 'campaigns': 'protests', 'connections': 'protests',
           'contests': 'elections', 'election_actions': 'elections'}


def validate_record(kind: str, payload: dict) -> dict:
    if kind not in KINDS:
        raise ValueError('unknown editable record kind')
    return KINDS[kind].model_validate(payload).model_dump(mode='json')


class CreateCommand(StrictModel):
    record: dict[str, Any]
    reason: Annotated[str, Field(min_length=3, max_length=2000)]


class UpdateCommand(CreateCommand):
    expected_revision: int = Field(ge=1)


class TransitionCommand(StrictModel):
    expected_revision: int = Field(ge=1)
    reason: Annotated[str, Field(min_length=3, max_length=2000)]


class MergeCommand(TransitionCommand):
    target_id: ID
