"""Relational identities, immutable revisions and typed per-revision projections.

JSON is limited to audit snapshots, arrays and original legacy provenance. Every
published pointer targets one immutable revision; drafts never mutate that row.
"""
from __future__ import annotations

from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, Date, DateTime, Float,
                        ForeignKey, ForeignKeyConstraint, Integer, String, Table,
                        Text, UniqueConstraint, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = 'schema_versions'
    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)


class Record(Base):
    __tablename__ = 'records'
    key: Mapped[str] = mapped_column(String(330), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    stable_id: Mapped[str] = mapped_column(String(160), index=True)
    current_revision: Mapped[int] = mapped_column(Integer, default=0)
    public_revision: Mapped[int | None] = mapped_column(Integer)
    editorial_status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint('kind', 'stable_id'),)


class Revision(Base):
    __tablename__ = 'revisions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_key: Mapped[str] = mapped_column(ForeignKey('records.key'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    public_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('record_key', 'number'),)


@event.listens_for(Revision, 'before_update')
def immutable_revision(mapper, connection, target):
    raise ValueError('revisions are immutable; append a new revision')


@event.listens_for(Revision, 'before_delete')
def prevent_revision_deletion(mapper, connection, target):
    raise ValueError('revision deletion is forbidden')


class EvidenceLink(Base):
    __tablename__ = 'evidence_links'
    revision_id: Mapped[int] = mapped_column(ForeignKey('revisions.id'), primary_key=True)
    source_key: Mapped[str] = mapped_column(ForeignKey('records.key'), primary_key=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    source_snapshot: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (ForeignKeyConstraint(['source_key', 'source_revision'], ['revisions.record_key', 'revisions.number']),)


class RecordReference(Base):
    __tablename__ = 'record_references'
    revision_id: Mapped[int] = mapped_column(ForeignKey('revisions.id'), primary_key=True)
    target_key: Mapped[str] = mapped_column(ForeignKey('records.key'), primary_key=True)
    relation: Mapped[str] = mapped_column(String(50), primary_key=True)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    public_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)


class CandidateIngestion(Base):
    __tablename__ = 'candidate_ingestions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    adapter: Mapped[str] = mapped_column(String(80), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    canonical_url: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[str] = mapped_column(String(40))
    source_published_at: Mapped[str | None] = mapped_column(String(40))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    record_key: Mapped[str] = mapped_column(ForeignKey('records.key'))
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id'))
    __table_args__ = (UniqueConstraint('canonical_url'),)


class ImportBatch(Base):
    __tablename__ = 'import_batches'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    imported_at: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40))
    counts: Mapped[dict] = mapped_column(JSON)
    metadata_payload: Mapped[dict] = mapped_column(JSON)


# Explicit domain tables hold typed columns for each immutable revision. This
# permits SQL analytics without interpreting untyped event payloads. Array-valued
# fields retain JSON arrays; source and entity links are also normalized above.
def domain_table(name, *columns):
    return Table(name, Base.metadata,
                 Column('revision_id', ForeignKey('revisions.id'), primary_key=True),
                 *columns)


def S(name, nullable=False):
    return Column(name, Text, nullable=nullable)


def D(name, nullable=True):
    return Column(name, Date, nullable=nullable)


def F(name, nullable=True):
    return Column(name, Float, nullable=nullable)


def A(name):
    return Column(name, JSON, nullable=False)


PROJECTIONS = {
    'actors': domain_table('actors', S('name'), S('actor_type'), S('country_code', True),
                          F('longitude', False), F('latitude', False), A('theaters'), S('category'),
                          CheckConstraint('longitude >= -180 AND longitude <= 180'),
                          CheckConstraint('latitude >= -90 AND latitude <= 90')),
    'relationships': domain_table('relationships', S('from_actor_id'), S('to_actor_id'),
                                 S('relationship_type'), S('category'), A('theaters'), D('valid_from'), D('valid_to')),
    'developments': domain_table('developments', A('actor_ids'), D('occurred_start'), D('occurred_end'),
                                S('date_precision'), S('development_type'), S('url', True),
                                Column('discovered_at', DateTime(timezone=True)), Column('published_at', DateTime(timezone=True)), S('provider_seen_raw', True), S('actor_link_note', True), S('attribution', True), A('causal_connections'), S('evidence_locator', True), S('development_subtype', True), Column('legacy_assertion_reverified', Boolean, nullable=False)),
    'occurrences': domain_table('occurrences', S('country_code'), S('country'), S('place_name'),
                               F('longitude'), F('latitude'), S('location_precision'), D('occurred_start', False),
                               D('occurred_end'), S('date_precision'), S('action_type'), A('demands'), A('targets'),
                               A('campaign_ids'), S('inclusion_rationale'), S('confidence_note'), S('participants', True),
                               S('response', True), S('outcome', True), Column('count_eligible', Boolean, nullable=False), S('attribution', True), S('location_note', True), A('crowd_estimates'), A('active_dates'), S('attribution_note', True), Column('organisers', JSON), S('evidence_locator', True), A('causal_connections'), S('time_local_raw', True), S('purpose', True), S('event_scope', True), D('reported_ongoing_as_of')),
    'campaigns': domain_table('campaigns', A('country_codes'), D('started_at'), D('ended_at'), A('demands'), A('targets'), A('occurrence_ids'), D('reported_through'), S('date_precision'), S('coverage_note'), Column('count_eligible', Boolean, nullable=False), A('causal_connections'), S('inclusion_rationale', True), S('evidence_locator', True), A('places_reported'), S('date_uncertainty', True), S('campaign_scope', True), A('action_mix')),
    'connections': domain_table('connections', S('from_id'), S('to_id'), S('connection_type'), S('evidence_note')),
    'contests': domain_table('contests', S('office'), S('election_stage'), Column('cycle', Integer, nullable=False), S('state_code'), S('jurisdiction'),
                            S('district', True), S('geography_version', True), S('boundary_status'), S('status'),
                            Column('result_as_of', DateTime(timezone=True)), D('election_date', False), A('candidates'),
                            S('winner', True), S('winner_basis', True), Column('total_votes', Integer), S('reporting_note'), S('result_as_of_raw', True), F('longitude'), F('latitude')),
    'election_actions': domain_table('election_actions', S('action_type'), S('actor'), S('jurisdiction'), S('state_code', True),
                                    S('geography_scope'), D('occurred_start', False), D('occurred_end'), S('date_precision'),
                                    S('procedural_status'), S('claim_status'), S('effect_claim', True), S('effect_evidence', True),
                                    S('intent_claim', True), S('intent_evidence', True), A('related_contest_ids'), S('current_operative_status', True), S('allegation_note', True), S('boundary_plan', True), S('case_id', True), A('causal_connections'), S('current_case_status', True), S('evidence_locator', True), D('legal_effective_date_as_stated'), D('status_as_of')),
    'political_context': domain_table('political_context', S('domain'), S('jurisdiction'), S('country_code', True), S('state_code', True),
                                     D('as_of', False), S('context_type'), A('related_ids')),
    'sources': domain_table('sources', S('title'), S('url', True), S('publisher'), S('source_type'),
                           Column('published_at', DateTime(timezone=True)), Column('retrieved_at', DateTime(timezone=True)),
                           S('rights'), S('note'), Column('source_updated_at', DateTime(timezone=True)), S('language', True), S('content_sha256', True),
                           D('published_date'), D('retrieval_date'), S('publication_precision'), S('retrieval_precision'), S('source_tier', True), S('source_updated_at_raw', True), S('access_status', True), D('document_date'), S('evidence_locator', True), Column('source_date_not_occurrence_date', Boolean, nullable=False), Column('reviewed_at', DateTime(timezone=True)), D('source_updated_date'), S('published_time_raw', True)),
    'coverage': domain_table('coverage', S('domain'), S('geography'), S('country_code', True), S('state_code', True),
                            D('period_start', False), D('period_end', False), S('status'), S('note'),
                            Column('reviewed_at', DateTime(timezone=True)), S('assessment_method', True), S('search_audit_key', True)),
}
