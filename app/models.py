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
    prompt_version = Column(String(64), nullable=True)
    processing_run_id = Column(String(64), nullable=True)
    llm_raw_response = Column(Text, nullable=True)
    validated_at = Column(DateTime, nullable=True)
    payload_json = Column(JSONB_COMPAT, nullable=False)
    canonical_payload_json = Column(JSONB_COMPAT, nullable=True)
    metadata_json = Column(JSONB_COMPAT, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    raw_message = relationship("RawMessage", back_populates="extraction")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    event_fingerprint = Column(String(512), nullable=False, index=True)
    topic = Column(String(64), nullable=True)
    summary_1_sentence = Column(Text, nullable=True)
    impact_score = Column(Float, nullable=True)
    is_breaking = Column(Boolean, nullable=True)
    breaking_window = Column(String(16), nullable=True)
    event_time = Column(DateTime, nullable=True, index=True)
    last_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    latest_extraction_id = Column(
        Integer, ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True
    )

    messages = relationship("EventMessage", back_populates="event")
    latest_extraction = relationship("Extraction", foreign_keys=[latest_extraction_id])
    published_posts = relationship("PublishedPost", back_populates="event")


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


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

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


class PublishedPost(Base):
    __tablename__ = "published_posts"

    id = Column(Integer, primary_key=True)
    event_id = Column(
        Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    destination = Column(String(64), nullable=False)  # e.g. vip_telegram
    published_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(128), nullable=False, index=True)

    event = relationship("Event", back_populates="published_posts")


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
