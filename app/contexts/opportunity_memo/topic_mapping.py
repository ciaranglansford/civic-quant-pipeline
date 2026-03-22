from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .constants import OPPORTUNITY_TOPICS, TOPIC_KEYWORDS, TOPIC_KEYWORD_ORDER
from .contracts import TopicMappingDiagnostics, TopicMappingResult


def _normalize(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _topic_hits_for_text(text: str, *, field_name: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = defaultdict(list)
    normalized = _normalize(text)
    if not normalized:
        return hits

    for topic in OPPORTUNITY_TOPICS:
        for keyword in TOPIC_KEYWORDS[topic]:
            if keyword in normalized:
                hits[topic].append(f"{field_name}:{keyword}")
    return hits


def _merge_hits(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for topic, entries in source.items():
        if topic not in target:
            target[topic] = []
        target[topic].extend(entries)


def _select_topic_from_hits(hits: dict[str, list[str]]) -> tuple[str | None, list[str]]:
    if not hits:
        return None, []

    ranked = sorted(
        hits.items(),
        key=lambda item: (-len(item[1]), TOPIC_KEYWORD_ORDER.get(item[0], 9999), item[0]),
    )
    topic, matched = ranked[0]
    unique_matched = sorted(set(matched))
    return topic, unique_matched


def _topic_hits_from_tags(tags: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for tag in tags:
        tag_type = _normalize(tag.get("tag_type") if isinstance(tag, dict) else None)
        tag_value = _normalize(tag.get("tag_value") if isinstance(tag, dict) else None)
        if not tag_value:
            continue
        field_name = f"event_tags.{tag_type or 'unknown'}"
        _merge_hits(hits, _topic_hits_for_text(tag_value, field_name=field_name))
    return hits


def _topic_hits_from_relations(relations: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        relation_type = _normalize(str(relation.get("relation_type") or ""))
        subject = _normalize(str(relation.get("subject_value") or ""))
        obj = _normalize(str(relation.get("object_value") or ""))
        if relation_type:
            _merge_hits(
                hits,
                _topic_hits_for_text(relation_type, field_name="event_relations.relation_type"),
            )
        if subject:
            _merge_hits(
                hits,
                _topic_hits_for_text(subject, field_name="event_relations.subject_value"),
            )
        if obj:
            _merge_hits(
                hits,
                _topic_hits_for_text(obj, field_name="event_relations.object_value"),
            )
    return hits


def _iter_payload_text_fields(payload: dict[str, Any]) -> Iterable[tuple[str, str]]:
    summary = payload.get("summary_1_sentence")
    if isinstance(summary, str):
        yield "latest_extraction_payload.summary_1_sentence", summary

    topic = payload.get("topic")
    if isinstance(topic, str):
        yield "latest_extraction_payload.topic", topic

    keywords = payload.get("keywords")
    if isinstance(keywords, list):
        for keyword in keywords:
            if isinstance(keyword, str):
                yield "latest_extraction_payload.keywords", keyword

    entities = payload.get("entities")
    if isinstance(entities, dict):
        for key in ("countries", "orgs", "people", "tickers"):
            values = entities.get(key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        yield f"latest_extraction_payload.entities.{key}", value

    market_stats = payload.get("market_stats")
    if isinstance(market_stats, list):
        for row in market_stats:
            if not isinstance(row, dict):
                continue
            label = row.get("label")
            context = row.get("context")
            if isinstance(label, str):
                yield "latest_extraction_payload.market_stats.label", label
            if isinstance(context, str):
                yield "latest_extraction_payload.market_stats.context", context


def _topic_hits_from_payload(payload: dict[str, Any]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for field_name, text in _iter_payload_text_fields(payload):
        _merge_hits(hits, _topic_hits_for_text(text, field_name=field_name))
    return hits


def map_event_to_topic(
    *,
    event_id: int,
    tags: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    latest_extraction_payload: dict[str, Any],
) -> TopicMappingResult:
    reason_trail: list[str] = []

    tag_hits = _topic_hits_from_tags(tags)
    topic, matched_fields = _select_topic_from_hits(tag_hits)
    if topic is not None:
        reason_trail.append("precedence:event_tags")
        reason_trail.extend([f"hit:{entry}" for entry in matched_fields])
        return TopicMappingResult(
            event_id=event_id,
            topic=topic,
            diagnostics=TopicMappingDiagnostics(
                source_layer="event_tags",
                matched_fields=matched_fields,
                reason_trail=reason_trail,
                final_topic=topic,
            ),
        )

    relation_hits = _topic_hits_from_relations(relations)
    topic, matched_fields = _select_topic_from_hits(relation_hits)
    if topic is not None:
        reason_trail.append("precedence:event_relations")
        reason_trail.extend([f"hit:{entry}" for entry in matched_fields])
        return TopicMappingResult(
            event_id=event_id,
            topic=topic,
            diagnostics=TopicMappingDiagnostics(
                source_layer="event_relations",
                matched_fields=matched_fields,
                reason_trail=reason_trail,
                final_topic=topic,
            ),
        )

    payload_hits = _topic_hits_from_payload(latest_extraction_payload)
    topic, matched_fields = _select_topic_from_hits(payload_hits)
    if topic is not None:
        reason_trail.append("precedence:latest_extraction_payload")
        reason_trail.extend([f"hit:{entry}" for entry in matched_fields])
        return TopicMappingResult(
            event_id=event_id,
            topic=topic,
            diagnostics=TopicMappingDiagnostics(
                source_layer="latest_extraction_payload",
                matched_fields=matched_fields,
                reason_trail=reason_trail,
                final_topic=topic,
            ),
        )

    reason_trail.append("precedence:no_match")
    return TopicMappingResult(
        event_id=event_id,
        topic=None,
        diagnostics=TopicMappingDiagnostics(
            source_layer="no_match",
            matched_fields=[],
            reason_trail=reason_trail,
            final_topic=None,
        ),
    )
