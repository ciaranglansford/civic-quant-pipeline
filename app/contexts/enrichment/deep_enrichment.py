from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ...models import EnrichmentCandidate, Event, EventDeepEnrichment, Extraction


@dataclass(frozen=True)
class DeepEnrichmentBatchSummary:
    selected: int
    processed: int
    created: int
    skipped_existing: int


def _payload_for_event(db: Session, *, event: Event) -> dict:
    if event.latest_extraction_id is None:
        return {}
    extraction = db.query(Extraction).filter_by(id=event.latest_extraction_id).one_or_none()
    if extraction is None:
        return {}
    payload = extraction.canonical_payload_json or extraction.payload_json or {}
    return payload if isinstance(payload, dict) else {}


def _build_mechanism_notes(payload: dict) -> list[str]:
    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    notes: list[str] = []
    if isinstance(relations, list):
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            subject = str(relation.get("subject_value") or "").strip()
            relation_type = str(relation.get("relation_type") or "").strip()
            obj = str(relation.get("object_value") or "").strip()
            if not (subject and relation_type and obj):
                continue
            notes.append(f"{subject} {relation_type} {obj}")
            if len(notes) >= 6:
                break
    summary = payload.get("summary_1_sentence")
    if not notes and isinstance(summary, str) and summary.strip():
        notes.append(summary.strip())
    return notes


def _build_downstream_hints(payload: dict) -> list[str]:
    tags = payload.get("tags", []) if isinstance(payload, dict) else []
    hints: list[str] = []
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            tag_type = str(tag.get("tag_type") or "").strip()
            tag_value = str(tag.get("tag_value") or "").strip()
            if not (tag_type and tag_value):
                continue
            if tag_type in {"commodities", "sectors", "companies"}:
                hints.append(f"Monitor downstream exposure to {tag_value}.")
            if len(hints) >= 6:
                break
    return sorted(set(hints))


def _build_contradiction_cues(payload: dict) -> list[str]:
    cues: list[str] = []
    directionality = payload.get("directionality")
    if directionality == "easing":
        cues.append("Directionality indicates easing pressure; compare against stress narratives.")

    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    if isinstance(relations, list):
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            relation_type = str(relation.get("relation_type") or "").strip()
            source = str(relation.get("relation_source") or "").strip()
            if relation_type == "contradicts":
                cues.append("Explicit contradictory relation detected.")
            if source == "inferred":
                cues.append("Contains inferred relation(s); verify against observed updates.")
    return sorted(set(cues))


def _build_offset_cues(payload: dict) -> list[str]:
    cues: list[str] = []
    directionality = payload.get("directionality")
    if directionality == "easing":
        cues.append("Potential offset from easing directionality.")
    if directionality == "neutral":
        cues.append("Neutral directionality may offset one-sided stress interpretation.")

    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    if isinstance(relations, list):
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            relation_type = str(relation.get("relation_type") or "").strip()
            if relation_type in {"supports", "expands_production_of"}:
                cues.append(f"Offset signal: {relation_type}.")
    return sorted(set(cues))


def _build_theme_affinity_hints(payload: dict) -> list[str]:
    tags = payload.get("tags", []) if isinstance(payload, dict) else []
    hints: list[str] = []
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            tag_type = str(tag.get("tag_type") or "").strip()
            tag_value = str(tag.get("tag_value") or "").strip()
            if tag_type == "strategic" and tag_value:
                hints.append(tag_value)
    return sorted(set(hints))


def run_deep_enrichment_batch(
    db: Session,
    *,
    limit: int,
    now: datetime | None = None,
) -> DeepEnrichmentBatchSummary:
    now = now or datetime.utcnow()
    candidates = (
        db.query(EnrichmentCandidate)
        .filter(
            EnrichmentCandidate.selected.is_(True),
            EnrichmentCandidate.enrichment_route == "deep_enrich",
        )
        .order_by(EnrichmentCandidate.scored_at.desc(), EnrichmentCandidate.id.desc())
        .limit(limit)
        .all()
    )

    selected = len(candidates)
    processed = 0
    created = 0
    skipped_existing = 0

    for candidate in candidates:
        processed += 1
        existing = db.query(EventDeepEnrichment).filter_by(event_id=candidate.event_id).one_or_none()
        if existing is not None:
            skipped_existing += 1
            continue

        event = db.query(Event).filter_by(id=candidate.event_id).one_or_none()
        if event is None:
            continue
        payload = _payload_for_event(db, event=event)

        row = EventDeepEnrichment(
            event_id=event.id,
            enrichment_route="deep_enrich",
            mechanism_notes=_build_mechanism_notes(payload),
            downstream_exposure_hints=_build_downstream_hints(payload),
            contradiction_cues=_build_contradiction_cues(payload),
            offset_cues=_build_offset_cues(payload),
            theme_affinity_hints=_build_theme_affinity_hints(payload),
            metadata_json={
                "candidate_id": candidate.id,
                "calibrated_score": candidate.calibrated_score,
                "processed_at": now.isoformat(),
            },
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        created += 1

    return DeepEnrichmentBatchSummary(
        selected=selected,
        processed=processed,
        created=created,
        skipped_existing=skipped_existing,
    )
