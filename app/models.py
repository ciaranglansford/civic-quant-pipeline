from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from .db import Base

JSONB_COMPAT = JSON().with_variant(JSONB, "postgresql")


class RawMessage(Base):
    __tablename__ = "raw_messages"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id",
            "telegram_message_id",
            name="uq_raw_source_msg",
        ),
    )

    id = Column(Integer, primary_key=True)
    source_channel_id = Column(String(255), nullable=False)
    source_channel_name = Column(String(255), nullable=True)
    telegram_message_id = Column(String(255), nullable=False)
    message_timestamp_utc = Column(DateTime, nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    raw_entities = Column(JSON, nullable=True)
    forwarded_from = Column(String(255), nullable=True)
    normalized_text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    extraction = relationship("Extraction", back_populates="raw_message", uselist=False)
    routing_decision = relationship(
        "RoutingDecision", back_populates="raw_message", uselist=False
    )
    event_links = relationship("EventMessage", back_populates="raw_message")
    processing_state = relationship("MessageProcessingState", back_populates="raw_message", uselist=False)


class MessageProcessingState(Base):
    __tablename__ = "message_processing_states"
    __table_args__ = (
        UniqueConstraint("raw_message_id", name="uq_message_processing_state_raw"),
        Index("ix_mps_status_lease", "status", "lease_expires_at"),
    )

    id = Column(Integer, primary_key=True)
    raw_message_id = Column(Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    processing_run_id = Column(String(64), nullable=True)

    raw_message = relationship("RawMessage", back_populates="processing_state")


class ProcessingLock(Base):
    __tablename__ = "processing_locks"

    lock_name = Column(String(64), primary_key=True)
    locked_until = Column(DateTime, nullable=False)
    owner_run_id = Column(String(64), nullable=False)


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint("raw_message_id", name="uq_extraction_raw_message"),
        Index("idx_extractions_topic_event_time", "topic", "event_time"),
        Index("idx_extractions_topic_event_time_impact", "topic", "event_time", "impact_score"),
        Index("idx_extractions_replay_identity_key", "replay_identity_key"),
        Index("idx_extractions_canonical_payload_hash", "canonical_payload_hash"),
        Index("idx_extractions_claim_hash", "claim_hash"),
        Index("idx_extractions_event_identity_fp_v2", "event_identity_fingerprint_v2"),
        Index(
            "idx_extractions_content_reuse_lookup",
            "normalized_text_hash",
            "extractor_name",
            "prompt_version",
            "schema_version",
            "canonicalizer_version",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True)
    raw_message_id = Column(
        Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False
    )
    model_name = Column(String(255), nullable=True)
    extractor_name = Column(Text, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    event_time = Column(DateTime, nullable=True, index=True)
    topic = Column(Text, nullable=True)
    impact_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    sentiment = Column(Text, nullable=True)
    is_breaking = Column(Boolean, nullable=True)
    breaking_window = Column(Text, nullable=True)
    event_fingerprint = Column(Text, nullable=True, index=True)
    event_identity_fingerprint_v2 = Column(String(512), nullable=True, index=True)
    normalized_text_hash = Column(String(64), nullable=True, index=True)
    replay_identity_key = Column(String(64), nullable=True, index=True)
    canonicalizer_version = Column(String(32), nullable=True)
    canonical_payload_hash = Column(String(64), nullable=True, index=True)
    claim_hash = Column(String(64), nullable=True, index=True)
    prompt_version = Column(String(64), nullable=True)
    processing_run_id = Column(String(64), nullable=True)
    llm_raw_response = Column(Text, nullable=True)
    validated_at = Column(DateTime, nullable=True)
    payload_json = Column(JSONB_COMPAT, nullable=False)
    canonical_payload_json = Column(JSONB_COMPAT, nullable=True)
    metadata_json = Column(JSONB_COMPAT, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    raw_message = relationship("RawMessage", back_populates="extraction")
    theme_evidence = relationship("EventThemeEvidence", back_populates="extraction")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "event_identity_fingerprint_v2",
            name="uq_events_identity_fp_v2",
        ),
    )

    id = Column(Integer, primary_key=True)
    event_fingerprint = Column(String(512), nullable=False, index=True)
    event_identity_fingerprint_v2 = Column(String(512), nullable=True, index=True)
    topic = Column(String(64), nullable=True)
    summary_1_sentence = Column(Text, nullable=True)
    impact_score = Column(Float, nullable=True)
    is_breaking = Column(Boolean, nullable=True)
    breaking_window = Column(String(16), nullable=True)
    event_time = Column(DateTime, nullable=True, index=True)
    event_time_bucket = Column(String(16), nullable=True, index=True)
    action_class = Column(String(64), nullable=True)
    canonical_payload_hash = Column(String(64), nullable=True, index=True)
    claim_hash = Column(String(64), nullable=True, index=True)
    review_required = Column(Boolean, nullable=False, default=False, index=True)
    review_reason = Column(String(128), nullable=True)
    last_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_published_telegram = Column(Boolean, nullable=False, default=False, index=True)
    is_published_twitter = Column(Boolean, nullable=False, default=False, index=True)

    latest_extraction_id = Column(
        Integer, ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True
    )

    messages = relationship("EventMessage", back_populates="event")
    latest_extraction = relationship("Extraction", foreign_keys=[latest_extraction_id])
    published_posts = relationship("PublishedPost", back_populates="event")
    enrichment_candidate = relationship("EnrichmentCandidate", back_populates="event", uselist=False)
    deep_enrichment = relationship("EventDeepEnrichment", back_populates="event", uselist=False)
    tags = relationship("EventTag", back_populates="event")
    relations = relationship("EventRelation", back_populates="event")
    theme_evidence = relationship("EventThemeEvidence", back_populates="event")


class EventMessage(Base):
    __tablename__ = "event_messages"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "raw_message_id",
            name="uq_event_message_link",
        ),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    raw_message_id = Column(
        Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False
    )
    linked_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    event = relationship("Event", back_populates="messages")
    raw_message = relationship("RawMessage", back_populates="event_links")


class EventTag(Base):
    __tablename__ = "event_tags"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "tag_type",
            "tag_value",
            "tag_source",
            name="uq_event_tags_event_type_value_source",
        ),
        Index("ix_event_tags_type_value_event", "tag_type", "tag_value", "event_id"),
        Index("ix_event_tags_event_id", "event_id"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    tag_type = Column(String(64), nullable=False)
    tag_value = Column(String(255), nullable=False)
    tag_source = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    event = relationship("Event", back_populates="tags")


class EventRelation(Base):
    __tablename__ = "event_relations"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "subject_type",
            "subject_value",
            "relation_type",
            "object_type",
            "object_value",
            "relation_source",
            "inference_level",
            name="uq_event_relations_event_relation_shape",
        ),
        Index("ix_event_relations_relation_event", "relation_type", "event_id"),
        Index("ix_event_relations_subject_lookup", "subject_type", "subject_value", "relation_type"),
        Index("ix_event_relations_object_lookup", "object_type", "object_value", "relation_type"),
        Index("ix_event_relations_event_id", "event_id"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    subject_type = Column(String(64), nullable=False)
    subject_value = Column(String(255), nullable=False)
    relation_type = Column(String(64), nullable=False)
    object_type = Column(String(64), nullable=False)
    object_value = Column(String(255), nullable=False)
    relation_source = Column(String(16), nullable=False)
    inference_level = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    event = relationship("Event", back_populates="relations")


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"
    __table_args__ = (
        UniqueConstraint("raw_message_id", name="uq_routing_decision_raw"),
    )

    id = Column(Integer, primary_key=True)
    raw_message_id = Column(
        Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False
    )
    store_to = Column(JSON, nullable=False)  # list of destination strings
    publish_priority = Column(String(16), nullable=False)
    requires_evidence = Column(Boolean, nullable=False, default=False)
    event_action = Column(String(16), nullable=False)  # create|update|ignore
    triage_action = Column(String(16), nullable=True)  # archive|monitor|update|promote
    triage_rules = Column(JSON, nullable=True)  # list of fired triage rule identifiers
    flags = Column(JSON, nullable=False)  # list of strings
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    raw_message = relationship("RawMessage", back_populates="routing_decision")


class DigestArtifact(Base):
    """Persisted digest artifact.

    `input_hash` is a stable identity derived from source digest inputs.
    It allows dedupe across reruns even when synthesized canonical text varies.
    `canonical_hash` remains the hash of rendered canonical text.
    """

    __tablename__ = "digest_artifacts"

    id = Column(Integer, primary_key=True)
    window_start_utc = Column(DateTime, nullable=False, index=True)
    window_end_utc = Column(DateTime, nullable=False, index=True)
    canonical_text = Column(Text, nullable=False)
    canonical_hash = Column(String(128), nullable=False, unique=True, index=True)
    input_hash = Column(String(128), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    published_posts = relationship("PublishedPost", back_populates="artifact")


class PublishedPost(Base):
    """Per-destination publish attempt/outcome for a digest artifact."""

    __tablename__ = "published_posts"
    __table_args__ = (
        UniqueConstraint("artifact_id", "destination", name="uq_published_posts_artifact_destination"),
        Index("ix_published_posts_destination_status", "destination", "status"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    artifact_id = Column(
        Integer, ForeignKey("digest_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    destination = Column(String(64), nullable=False)  # e.g. vip_telegram
    status = Column(String(32), nullable=False, default="published")
    last_attempted_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(128), nullable=False, index=True)
    last_error = Column(Text, nullable=True)
    external_ref = Column(String(255), nullable=True)

    event = relationship("Event", back_populates="published_posts")
    artifact = relationship("DigestArtifact", back_populates="published_posts")


class EnrichmentCandidate(Base):
    __tablename__ = "enrichment_candidates"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_enrichment_candidate_event"),
        Index("ix_enrichment_candidates_selected_scored", "selected", "scored_at"),
        Index("ix_enrichment_candidates_route_selected_scored", "enrichment_route", "selected", "scored_at"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    selected = Column(Boolean, nullable=False, default=False)
    triage_action = Column(String(16), nullable=True)
    reason_codes = Column(JSON, nullable=False, default=list)
    novelty_state = Column(String(64), nullable=False, default="novel")
    novelty_cluster_key = Column(String(255), nullable=True, index=True)
    enrichment_route = Column(String(32), nullable=False, default="store_only", index=True)
    calibrated_score = Column(Float, nullable=False, default=0.0)
    raw_llm_score = Column(Float, nullable=True)
    score_band = Column(String(16), nullable=False, default="low")
    shock_flags = Column(JSON, nullable=False, default=list)
    score_breakdown = Column(JSONB_COMPAT, nullable=False, default=dict)
    scored_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    event = relationship("Event", back_populates="enrichment_candidate")


class EventDeepEnrichment(Base):
    __tablename__ = "event_deep_enrichments"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_event_deep_enrichment_event"),
        Index("ix_event_deep_enrichment_created", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True)
    enrichment_route = Column(String(32), nullable=False, default="deep_enrich")
    mechanism_notes = Column(JSONB_COMPAT, nullable=False, default=list)
    downstream_exposure_hints = Column(JSONB_COMPAT, nullable=False, default=list)
    contradiction_cues = Column(JSONB_COMPAT, nullable=False, default=list)
    offset_cues = Column(JSONB_COMPAT, nullable=False, default=list)
    theme_affinity_hints = Column(JSONB_COMPAT, nullable=False, default=list)
    metadata_json = Column(JSONB_COMPAT, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    event = relationship("Event", back_populates="deep_enrichment")


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "raw_message_id",
            "entity_type",
            "entity_value",
            name="uq_entity_mentions_raw_type_value",
        ),
        Index("ix_entity_mentions_type_value_time", "entity_type", "entity_value", "event_time"),
        Index("ix_entity_mentions_topic_time", "topic", "event_time"),
        Index("ix_entity_mentions_breaking_time", "is_breaking", "event_time"),
    )

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(32), nullable=False)  # country|org|person|ticker
    entity_value = Column(String(255), nullable=False)
    raw_message_id = Column(
        Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False
    )
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    topic = Column(String(64), nullable=True)
    is_breaking = Column(Boolean, nullable=True)
    event_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ThemeRun(Base):
    __tablename__ = "theme_runs"
    __table_args__ = (
        Index(
            "ix_theme_runs_theme_cadence_window_created",
            "theme_key",
            "cadence",
            "window_start_utc",
            "window_end_utc",
            "created_at",
        ),
        Index("ix_theme_runs_theme_created", "theme_key", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    run_key = Column(String(64), nullable=False, unique=True, index=True)
    theme_key = Column(String(128), nullable=False, index=True)
    cadence = Column(String(16), nullable=False)
    window_start_utc = Column(DateTime, nullable=False, index=True)
    window_end_utc = Column(DateTime, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="running", index=True)
    dry_run = Column(Boolean, nullable=False, default=False)
    emit_brief = Column(Boolean, nullable=False, default=True)
    selected_evidence_count = Column(Integer, nullable=False, default=0)
    assessment_count = Column(Integer, nullable=False, default=0)
    thesis_card_count = Column(Integer, nullable=False, default=0)
    suppressed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    assessments = relationship("ThemeOpportunityAssessment", back_populates="theme_run")
    thesis_cards = relationship("ThesisCard", back_populates="theme_run")
    brief_artifact = relationship("ThemeBriefArtifact", back_populates="theme_run", uselist=False)


class EventThemeEvidence(Base):
    __tablename__ = "event_theme_evidence"
    __table_args__ = (
        UniqueConstraint(
            "theme_key",
            "event_id",
            "extraction_id",
            name="uq_event_theme_evidence_theme_event_extraction",
        ),
        Index("ix_event_theme_evidence_theme_event_time_id", "theme_key", "event_time", "id"),
    )

    id = Column(Integer, primary_key=True)
    theme_key = Column(String(128), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    extraction_id = Column(
        Integer, ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_time = Column(DateTime, nullable=True, index=True)
    event_topic = Column(String(64), nullable=True, index=True)
    impact_score = Column(Float, nullable=True)
    calibrated_score = Column(Float, nullable=True)
    matched_archetypes = Column(JSON, nullable=False, default=list)
    match_reason_codes = Column(JSON, nullable=False, default=list)
    severity_snapshot_json = Column(JSONB_COMPAT, nullable=False, default=dict)
    entity_refs = Column(JSON, nullable=False, default=list)
    geography_refs = Column(JSON, nullable=False, default=list)
    metadata_json = Column(JSONB_COMPAT, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    event = relationship("Event", back_populates="theme_evidence")
    extraction = relationship("Extraction", back_populates="theme_evidence")


class ThemeOpportunityAssessment(Base):
    __tablename__ = "theme_opportunity_assessments"
    __table_args__ = (
        UniqueConstraint("stable_key", name="uq_theme_opportunity_assessment_stable_key"),
        Index("ix_theme_opportunity_assessment_theme_created", "theme_key", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    theme_run_id = Column(Integer, ForeignKey("theme_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    stable_key = Column(String(128), nullable=False, unique=True, index=True)
    theme_key = Column(String(128), nullable=False, index=True)
    cadence = Column(String(16), nullable=False)
    window_start_utc = Column(DateTime, nullable=False, index=True)
    window_end_utc = Column(DateTime, nullable=False, index=True)
    active_lenses = Column(JSON, nullable=False, default=list)
    active_transmission_patterns = Column(JSON, nullable=False, default=list)
    primary_lens = Column(String(64), nullable=True, index=True)
    primary_transmission_pattern = Column(String(64), nullable=True, index=True)
    evidence_summary_json = Column(JSONB_COMPAT, nullable=False, default=dict)
    top_supporting_evidence_ids = Column(JSON, nullable=False, default=list)
    top_contradictory_evidence_ids = Column(JSON, nullable=False, default=list)
    dominant_drivers = Column(JSONB_COMPAT, nullable=False, default=dict)
    transmission_narrative_json = Column(JSONB_COMPAT, nullable=False, default=dict)
    candidate_opportunities = Column(JSON, nullable=False, default=list)
    candidate_risks = Column(JSON, nullable=False, default=list)
    evidence_strength_score = Column(Float, nullable=False, default=0.0)
    lens_fit_score = Column(Float, nullable=False, default=0.0)
    opportunity_priority_score = Column(Float, nullable=False, default=0.0)
    confidence_score = Column(Float, nullable=False, default=0.0)
    urgency = Column(String(32), nullable=False, default="low")
    time_horizon = Column(String(32), nullable=False, default="medium_term")
    invalidation_conditions = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    theme_run = relationship("ThemeRun", back_populates="assessments")
    thesis_cards = relationship("ThesisCard", back_populates="assessment")


class ThesisCard(Base):
    __tablename__ = "thesis_cards"
    __table_args__ = (
        Index("ix_thesis_cards_theme_status_created", "theme_key", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    theme_run_id = Column(Integer, ForeignKey("theme_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(
        Integer,
        ForeignKey("theme_opportunity_assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    theme_key = Column(String(128), nullable=False, index=True)
    cadence = Column(String(16), nullable=False)
    window_start_utc = Column(DateTime, nullable=False, index=True)
    window_end_utc = Column(DateTime, nullable=False, index=True)
    title = Column(Text, nullable=False)
    what_happened = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    transmission_path = Column(Text, nullable=False)
    opportunity_angles = Column(JSON, nullable=False, default=list)
    confidence = Column(Float, nullable=False, default=0.0)
    what_to_watch_next = Column(Text, nullable=False)
    invalidation_criteria = Column(Text, nullable=False)
    supporting_evidence_refs = Column(JSON, nullable=False, default=list)
    narrative_signature = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="draft_only", index=True)
    suppression_reason = Column(Text, nullable=True)
    material_update_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    theme_run = relationship("ThemeRun", back_populates="thesis_cards")
    assessment = relationship("ThemeOpportunityAssessment", back_populates="thesis_cards")


class ThemeBriefArtifact(Base):
    __tablename__ = "theme_brief_artifacts"
    __table_args__ = (
        UniqueConstraint("theme_run_id", name="uq_theme_brief_artifact_run"),
    )

    id = Column(Integer, primary_key=True)
    theme_run_id = Column(Integer, ForeignKey("theme_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    theme_key = Column(String(128), nullable=False, index=True)
    cadence = Column(String(16), nullable=False)
    window_start_utc = Column(DateTime, nullable=False, index=True)
    window_end_utc = Column(DateTime, nullable=False, index=True)
    summary_text = Column(Text, nullable=False)
    highlights_json = Column(JSON, nullable=False, default=list)
    assessment_ids_json = Column(JSON, nullable=False, default=list)
    thesis_card_ids_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="created")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    theme_run = relationship("ThemeRun", back_populates="brief_artifact")
