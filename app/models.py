from datetime import datetime

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
)
from sqlalchemy.orm import relationship

from .db import Base


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


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True)
    raw_message_id = Column(
        Integer, ForeignKey("raw_messages.id", ondelete="CASCADE"), nullable=False
    )
    model_name = Column(String(255), nullable=False, default="stub-extractor-v1")
    extraction_json = Column(JSON, nullable=False)
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

