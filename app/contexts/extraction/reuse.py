from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...models import Extraction
from ...schemas import ExtractionJson
from ..triage.impact_scoring import ImpactCalibrationResult
from ..triage.triage_engine import impact_band


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_replay_identity_key(
    *,
    raw_message_id: int,
    normalized_text_hash: str,
    extractor_name: str,
    prompt_version: str,
    schema_version: int,
    canonicalizer_version: str,
) -> str:
    source = (
        f"raw_message_id={raw_message_id}"
        f"|normalized_text_hash={normalized_text_hash}"
        f"|extractor_name={extractor_name}"
        f"|prompt_version={prompt_version}"
        f"|schema_version={schema_version}"
        f"|canonicalizer_version={canonicalizer_version}"
    )
    return sha256_text(source)


def calibration_from_metadata(
    extraction: Extraction,
    extraction_model: ExtractionJson,
) -> ImpactCalibrationResult:
    metadata = extraction.metadata_json if isinstance(extraction.metadata_json, dict) else {}
    impact_meta = metadata.get("impact_scoring") if isinstance(metadata, dict) else {}
    if not isinstance(impact_meta, dict):
        impact_meta = {}
    calibrated_score = float(impact_meta.get("calibrated_score", extraction_model.impact_score))
    enrichment_route = str(impact_meta.get("enrichment_route") or "").strip()
    if not enrichment_route:
        enrichment_route = "deep_enrich" if calibrated_score >= 80.0 else ("index_only" if calibrated_score >= 45.0 else "store_only")
    return ImpactCalibrationResult(
        raw_llm_score=float(impact_meta.get("raw_llm_score", extraction_model.impact_score)),
        calibrated_score=calibrated_score,
        score_band=str(impact_meta.get("score_band", impact_band(float(extraction_model.impact_score)))),
        enrichment_route=enrichment_route,
        shock_flags=list(impact_meta.get("shock_flags", [])),
        rules_fired=list(impact_meta.get("rules_fired", [])),
        score_breakdown=dict(impact_meta.get("score_breakdown", {})),
    )


def find_reusable_extraction(
    db: Session,
    *,
    raw_message_id: int,
    normalized_text_hash: str,
    extractor_name: str,
    prompt_version: str,
    schema_version: int,
    canonicalizer_version: str,
    reuse_window_hours: int,
) -> Extraction | None:
    query = (
        db.query(Extraction)
        .filter(
            Extraction.raw_message_id != raw_message_id,
            Extraction.normalized_text_hash == normalized_text_hash,
            Extraction.extractor_name == extractor_name,
            Extraction.prompt_version == prompt_version,
            Extraction.schema_version == schema_version,
            Extraction.canonicalizer_version == canonicalizer_version,
            Extraction.canonical_payload_json.is_not(None),
            Extraction.canonical_payload_hash.is_not(None),
        )
        .order_by(Extraction.created_at.desc(), Extraction.id.desc())
    )
    if reuse_window_hours > 0:
        query = query.filter(
            Extraction.created_at >= datetime.utcnow() - timedelta(hours=reuse_window_hours)
        )
    return query.first()

