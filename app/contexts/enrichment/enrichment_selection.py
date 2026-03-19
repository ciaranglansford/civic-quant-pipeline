from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from sqlalchemy.orm import Session

from ...models import EnrichmentCandidate, Event, Extraction
from ...schemas import ExtractionJson
from ..extraction.extraction_payload_utils import entity_signature_from_payload
from ..triage.impact_scoring import ImpactCalibrationResult


_NOVELTY_WINDOW = timedelta(hours=3)
_DUPLICATE_RULE_MARKERS = {
    "triage:repeat_downgrade",
    "triage:burst_cap_update",
    "triage:burst_cap_monitor",
    "triage:soft_related_downgrade",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class EnrichmentSelectionResult:
    selected: bool
    reason_codes: list[str]
    novelty_state: str
    novelty_cluster_key: str


def _tokenize(value: str) -> set[str]:
    return set(_TOKEN_RE.findall((value or "").lower()))


def _title_similarity(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _entity_signature(extraction: ExtractionJson) -> set[str]:
    out: set[str] = set()
    for value in extraction.entities.countries:
        cleaned = value.strip().lower()
        if cleaned:
            out.add(f"country:{cleaned}")
    for value in extraction.entities.orgs:
        cleaned = value.strip().lower()
        if cleaned:
            out.add(f"org:{cleaned}")
    for value in extraction.entities.people:
        cleaned = value.strip().lower()
        if cleaned:
            out.add(f"person:{cleaned}")
    return out


def _novelty_cluster_key(extraction: ExtractionJson) -> str:
    if extraction.event_fingerprint:
        return extraction.event_fingerprint

    event_hour = extraction.event_time.strftime("%Y-%m-%dT%H") if extraction.event_time else "none"
    source = (extraction.source_claimed or "unknown").strip().lower()
    top_keywords = sorted({k.strip().lower() for k in extraction.keywords if k and k.strip()})[:3]
    key_suffix = ",".join(top_keywords) if top_keywords else "none"
    return f"{extraction.topic}|{source}|{event_hour}|{key_suffix}"


def _blocked_by_title_entity_overlap(
    db: Session,
    *,
    event_id: int,
    extraction: ExtractionJson,
    now: datetime,
) -> bool:
    candidate_events = (
        db.query(Event)
        .filter(
            Event.id != event_id,
            Event.topic == extraction.topic,
            Event.last_updated_at >= now - _NOVELTY_WINDOW,
        )
        .order_by(Event.last_updated_at.desc())
        .limit(20)
        .all()
    )
    if not candidate_events:
        return False

    current_entities = _entity_signature(extraction)
    extraction_ids = [e.latest_extraction_id for e in candidate_events if e.latest_extraction_id is not None]
    latest_rows = db.query(Extraction).filter(Extraction.id.in_(extraction_ids)).all() if extraction_ids else []
    by_id = {row.id: row for row in latest_rows}

    for candidate in candidate_events:
        similarity = _title_similarity(extraction.summary_1_sentence, candidate.summary_1_sentence or "")
        if similarity < 0.82:
            continue

        entity_overlap = 0
        if candidate.latest_extraction_id is not None:
            latest = by_id.get(candidate.latest_extraction_id)
            if latest is not None:
                payload = latest.canonical_payload_json or latest.payload_json or {}
                entity_overlap = len(current_entities & entity_signature_from_payload(payload if isinstance(payload, dict) else {}))

        if entity_overlap < 1:
            continue

        if extraction.event_time is not None and candidate.event_time is not None:
            if abs(extraction.event_time - candidate.event_time) > timedelta(hours=4):
                continue

        return True

    return False


def evaluate_enrichment_selection(
    db: Session,
    *,
    event_id: int,
    extraction: ExtractionJson,
    calibration: ImpactCalibrationResult,
    triage_action: str | None,
    triage_rules: list[str],
    existing_event_id: int | None,
    now: datetime,
) -> EnrichmentSelectionResult:
    reasons: list[str] = []
    novelty_state = "novel"
    cluster_key = _novelty_cluster_key(extraction)

    route = calibration.enrichment_route
    reasons.append(f"enrichment:route:{route}")
    eligible = route == "deep_enrich"
    if not eligible:
        reasons.append("enrichment:not_eligible_route")
    if triage_action == "archive":
        reasons.append("enrichment:triage_archive_block")
        eligible = False

    if existing_event_id is not None:
        novelty_state = "blocked_event_lineage"
        reasons.append("enrichment:novelty_block_event_lineage")
        eligible = False

    if _DUPLICATE_RULE_MARKERS.intersection(set(triage_rules)):
        novelty_state = "blocked_duplicate_marker"
        reasons.append("enrichment:novelty_block_duplicate_marker")
        eligible = False

    recent_cluster_hit = (
        db.query(EnrichmentCandidate)
        .filter(
            EnrichmentCandidate.event_id != event_id,
            EnrichmentCandidate.novelty_cluster_key == cluster_key,
            EnrichmentCandidate.selected.is_(True),
            EnrichmentCandidate.scored_at >= now - _NOVELTY_WINDOW,
        )
        .first()
    )
    if recent_cluster_hit is not None:
        novelty_state = "blocked_cluster_repeat"
        reasons.append("enrichment:novelty_block_cluster_repeat")
        eligible = False

    if _blocked_by_title_entity_overlap(db, event_id=event_id, extraction=extraction, now=now):
        novelty_state = "blocked_title_entity_overlap"
        reasons.append("enrichment:novelty_block_title_entity_overlap")
        eligible = False

    if eligible:
        reasons.append("enrichment:selected")

    return EnrichmentSelectionResult(
        selected=eligible,
        reason_codes=sorted(set(reasons)),
        novelty_state=novelty_state,
        novelty_cluster_key=cluster_key,
    )


def select_and_store_enrichment_candidate(
    db: Session,
    *,
    event_id: int,
    extraction: ExtractionJson,
    calibration: ImpactCalibrationResult,
    triage_action: str | None,
    triage_rules: list[str],
    existing_event_id: int | None,
    now: datetime | None = None,
) -> EnrichmentCandidate:
    now = now or datetime.utcnow()
    selection = evaluate_enrichment_selection(
        db,
        event_id=event_id,
        extraction=extraction,
        calibration=calibration,
        triage_action=triage_action,
        triage_rules=triage_rules,
        existing_event_id=existing_event_id,
        now=now,
    )

    row = db.query(EnrichmentCandidate).filter_by(event_id=event_id).one_or_none()
    if row is None:
        row = EnrichmentCandidate(event_id=event_id)
        db.add(row)

    row.selected = bool(selection.selected)
    row.triage_action = triage_action
    row.reason_codes = selection.reason_codes
    row.novelty_state = selection.novelty_state
    row.novelty_cluster_key = selection.novelty_cluster_key
    row.enrichment_route = calibration.enrichment_route
    row.calibrated_score = float(calibration.calibrated_score)
    row.raw_llm_score = float(calibration.raw_llm_score)
    row.score_band = calibration.score_band
    row.shock_flags = list(calibration.shock_flags)
    row.score_breakdown = calibration.score_breakdown
    row.scored_at = now

    db.flush()
    return row


