from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ...config import Settings
from ...models import Extraction, RawMessage
from ...schemas import ExtractionJson
from ..triage.impact_scoring import ImpactCalibrationResult, calibrate_impact
from .canonicalization import (
    CANONICALIZER_VERSION,
    canonicalize_extraction,
    compute_canonical_payload_hash,
    compute_claim_hash,
    derive_action_class,
    event_time_bucket,
)
from .extraction_llm_client import OpenAiExtractionClient
from .extraction_validation import parse_and_validate_extraction
from .prompt_templates import render_extraction_prompt
from .reuse import (
    build_replay_identity_key,
    calibration_from_metadata,
    find_reusable_extraction,
    sha256_text,
)


logger = logging.getLogger("civicquant.phase2")
OPENAI_EXTRACTOR_NAME = "extract-and-score-openai-v1"
EXTRACTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProcessedExtraction:
    extraction_row: Extraction
    extraction_model: ExtractionJson
    calibration: ImpactCalibrationResult
    canonical_payload_hash: str
    claim_hash: str
    action_class: str
    time_bucket: str


def materialize_extraction_for_raw_message(
    db: Session,
    *,
    raw: RawMessage,
    run_id: str,
    settings: Settings,
    client: OpenAiExtractionClient,
    force_reprocess: bool,
) -> ProcessedExtraction:
    prompt = render_extraction_prompt(
        normalized_text=raw.normalized_text,
        message_time=raw.message_timestamp_utc,
        source_channel_name=raw.source_channel_name,
    )
    normalized_text_hash = sha256_text(raw.normalized_text or "")
    replay_identity_key = build_replay_identity_key(
        raw_message_id=raw.id,
        normalized_text_hash=normalized_text_hash,
        extractor_name=OPENAI_EXTRACTOR_NAME,
        prompt_version=prompt.prompt_version,
        schema_version=EXTRACTION_SCHEMA_VERSION,
        canonicalizer_version=CANONICALIZER_VERSION,
    )
    extraction = db.query(Extraction).filter_by(raw_message_id=raw.id).one_or_none()

    replay_reused = False
    content_reused = False
    content_reuse_source_extraction_id: int | None = None
    reusable_extraction: Extraction | None = None
    canonical_payload_unchanged = False
    raw_payload: dict | None = None
    llm_fingerprint_candidate: str | None = None
    backend_fingerprint_version = "unknown"
    backend_fingerprint_input = ""
    llm_response = None
    canonicalization_rules: list[str] = []
    dropped_tag_count = 0
    dropped_relation_count = 0
    canonical_payload_hash: str
    claim_hash: str
    action_class: str
    time_bucket: str

    if (
        extraction is not None
        and not force_reprocess
        and extraction.replay_identity_key == replay_identity_key
        and isinstance(extraction.canonical_payload_json, dict)
        and bool(extraction.canonical_payload_hash)
    ):
        replay_reused = True
        extraction_model = ExtractionJson.model_validate(extraction.canonical_payload_json)
        calibration = calibration_from_metadata(extraction, extraction_model)
        canonical_payload = extraction_model.model_dump(mode="json")
        dropped_tag_count = int(
            (
                extraction.metadata_json.get("structured_contract", {})
                if isinstance(extraction.metadata_json, dict)
                else {}
            ).get("dropped_tag_count", 0)
            or 0
        )
        dropped_relation_count = int(
            (
                extraction.metadata_json.get("structured_contract", {})
                if isinstance(extraction.metadata_json, dict)
                else {}
            ).get("dropped_relation_count", 0)
            or 0
        )
        canonical_payload_hash = extraction.canonical_payload_hash or compute_canonical_payload_hash(
            extraction_model
        )
        claim_hash = extraction.claim_hash or compute_claim_hash(extraction_model)
        action_class = derive_action_class(extraction_model)
        time_bucket = event_time_bucket(extraction_model)
        extraction.normalized_text_hash = normalized_text_hash
        extraction.replay_identity_key = replay_identity_key
        extraction.canonicalizer_version = CANONICALIZER_VERSION
        extraction.processing_run_id = run_id
        extraction.event_identity_fingerprint_v2 = (
            extraction_model.event_fingerprint or extraction.event_identity_fingerprint_v2
        )
        extraction.canonical_payload_hash = canonical_payload_hash
        extraction.claim_hash = claim_hash
        logger.info(
            "phase2_replay_reuse raw_message_id=%s replay_identity_key=%s canonical_payload_hash=%s",
            raw.id,
            replay_identity_key,
            canonical_payload_hash,
        )
    else:
        if settings.phase2_content_reuse_enabled and not force_reprocess:
            reusable_extraction = find_reusable_extraction(
                db,
                raw_message_id=raw.id,
                normalized_text_hash=normalized_text_hash,
                extractor_name=OPENAI_EXTRACTOR_NAME,
                prompt_version=prompt.prompt_version,
                schema_version=EXTRACTION_SCHEMA_VERSION,
                canonicalizer_version=CANONICALIZER_VERSION,
                reuse_window_hours=settings.phase2_content_reuse_window_hours,
            )
        if reusable_extraction is not None:
            content_reused = True
            content_reuse_source_extraction_id = reusable_extraction.id
            extraction_model = ExtractionJson.model_validate(reusable_extraction.canonical_payload_json)
            calibration = calibration_from_metadata(reusable_extraction, extraction_model)
            canonical_payload = extraction_model.model_dump(mode="json")
            canonical_payload_hash = reusable_extraction.canonical_payload_hash or compute_canonical_payload_hash(
                extraction_model
            )
            claim_hash = reusable_extraction.claim_hash or compute_claim_hash(extraction_model)
            action_class = derive_action_class(extraction_model)
            time_bucket = event_time_bucket(extraction_model)
            if isinstance(reusable_extraction.payload_json, dict):
                raw_payload = reusable_extraction.payload_json
            source_meta = (
                reusable_extraction.metadata_json
                if isinstance(reusable_extraction.metadata_json, dict)
                else {}
            )
            llm_fingerprint_candidate = source_meta.get("llm_event_fingerprint_candidate")
            canonicalization_rules = source_meta.get("canonicalization_rules", [])
            backend_fingerprint_version = source_meta.get("backend_event_fingerprint_version", "v2")
            backend_fingerprint_input = source_meta.get("backend_event_fingerprint_input", "")
            structured_meta = source_meta.get("structured_contract", {})
            if isinstance(structured_meta, dict):
                dropped_tag_count = int(structured_meta.get("dropped_tag_count", 0) or 0)
                dropped_relation_count = int(structured_meta.get("dropped_relation_count", 0) or 0)
            logger.info(
                "phase2_content_reuse raw_message_id=%s source_extraction_id=%s normalized_text_hash=%s canonical_payload_hash=%s",
                raw.id,
                reusable_extraction.id,
                normalized_text_hash,
                canonical_payload_hash,
            )
        else:
            llm_response = client.extract(prompt.prompt_text)
            parsed = parse_and_validate_extraction(llm_response.raw_text)
            llm_fp_raw = parsed.get("event_fingerprint") if isinstance(parsed, dict) else None
            if isinstance(llm_fp_raw, str) and llm_fp_raw.strip():
                llm_fingerprint_candidate = llm_fp_raw.strip()

            raw_payload = parsed
            extraction_model_raw, canonicalization_rules, fingerprint_info = canonicalize_extraction(parsed)
            raw_tag_count = len(parsed.get("tags", [])) if isinstance(parsed.get("tags"), list) else 0
            raw_relation_count = len(parsed.get("relations", [])) if isinstance(parsed.get("relations"), list) else 0
            dropped_tag_count = max(0, raw_tag_count - len(extraction_model_raw.tags))
            dropped_relation_count = max(0, raw_relation_count - len(extraction_model_raw.relations))
            calibration = calibrate_impact(extraction_model_raw)
            extraction_model = extraction_model_raw.model_copy(
                update={"impact_score": calibration.calibrated_score}
            )
            canonical_payload = extraction_model.model_dump(mode="json")
            canonical_payload_hash = compute_canonical_payload_hash(extraction_model)
            claim_hash = compute_claim_hash(extraction_model)
            action_class = derive_action_class(extraction_model)
            time_bucket = event_time_bucket(extraction_model)
            backend_fingerprint_version = fingerprint_info.version
            backend_fingerprint_input = fingerprint_info.canonical_input

            if extraction is not None and extraction.canonical_payload_hash == canonical_payload_hash:
                canonical_payload_unchanged = True
                if isinstance(extraction.canonical_payload_json, dict):
                    extraction_model = ExtractionJson.model_validate(extraction.canonical_payload_json)
                    canonical_payload = extraction_model.model_dump(mode="json")
                calibration = calibration_from_metadata(extraction, extraction_model)
                claim_hash = extraction.claim_hash or claim_hash
                action_class = (
                    extraction.action_class
                    if hasattr(extraction, "action_class") and extraction.action_class
                    else action_class
                )
                time_bucket = (
                    extraction.metadata_json.get("event_time_bucket", time_bucket)
                    if isinstance(extraction.metadata_json, dict)
                    else time_bucket
                )
                logger.info(
                    "phase2_canonical_payload_noop raw_message_id=%s replay_identity_key=%s canonical_payload_hash=%s",
                    raw.id,
                    replay_identity_key,
                    canonical_payload_hash,
                )

    if extraction is None:
        extraction = Extraction(
            raw_message_id=raw.id,
            extractor_name=OPENAI_EXTRACTOR_NAME,
            schema_version=EXTRACTION_SCHEMA_VERSION,
            payload_json=raw_payload or {},
        )
        db.add(extraction)

    extraction.extractor_name = OPENAI_EXTRACTOR_NAME
    extraction.schema_version = EXTRACTION_SCHEMA_VERSION
    extraction.event_fingerprint = extraction_model.event_fingerprint
    extraction.event_identity_fingerprint_v2 = extraction_model.event_fingerprint or None
    extraction.normalized_text_hash = normalized_text_hash
    extraction.replay_identity_key = replay_identity_key
    extraction.canonicalizer_version = CANONICALIZER_VERSION
    extraction.canonical_payload_hash = canonical_payload_hash
    extraction.claim_hash = claim_hash
    extraction.prompt_version = prompt.prompt_version
    extraction.processing_run_id = run_id

    if not replay_reused and not canonical_payload_unchanged:
        extraction.model_name = (
            llm_response.model_name
            if llm_response is not None
            else (reusable_extraction.model_name if reusable_extraction is not None else extraction.model_name)
        )
        extraction.event_time = extraction_model.event_time
        extraction.topic = extraction_model.topic
        extraction.impact_score = float(extraction_model.impact_score)
        extraction.confidence = float(extraction_model.confidence)
        extraction.sentiment = extraction_model.sentiment
        extraction.is_breaking = bool(extraction_model.is_breaking)
        extraction.breaking_window = extraction_model.breaking_window
        extraction.llm_raw_response = (
            llm_response.raw_text
            if llm_response is not None
            else (
                reusable_extraction.llm_raw_response
                if reusable_extraction is not None
                else extraction.llm_raw_response
            )
        )
        extraction.validated_at = (
            datetime.utcnow()
            if llm_response is not None
            else (
                reusable_extraction.validated_at
                if reusable_extraction is not None
                else extraction.validated_at
            )
        )
        extraction.payload_json = raw_payload or extraction.payload_json or {}
        extraction.canonical_payload_json = canonical_payload

    metadata_existing = extraction.metadata_json if isinstance(extraction.metadata_json, dict) else {}
    metadata_source = (
        reusable_extraction.metadata_json
        if reusable_extraction is not None and isinstance(reusable_extraction.metadata_json, dict)
        else {}
    )
    extraction.metadata_json = {
        **metadata_existing,
        "used_openai": (
            llm_response.used_openai
            if llm_response is not None
            else (
                metadata_source.get("used_openai")
                if reusable_extraction is not None
                else metadata_existing.get("used_openai")
            )
        ),
        "openai_model": (
            llm_response.model_name
            if llm_response is not None
            else (
                metadata_source.get("openai_model")
                if reusable_extraction is not None
                else metadata_existing.get("openai_model")
            )
        ),
        "openai_response_id": (
            llm_response.openai_response_id
            if llm_response is not None
            else (
                metadata_source.get("openai_response_id")
                if reusable_extraction is not None
                else metadata_existing.get("openai_response_id")
            )
        ),
        "latency_ms": (
            llm_response.latency_ms
            if llm_response is not None
            else (
                metadata_source.get("latency_ms")
                if reusable_extraction is not None
                else metadata_existing.get("latency_ms")
            )
        ),
        "retries": (
            llm_response.retries
            if llm_response is not None
            else (
                metadata_source.get("retries", 0)
                if reusable_extraction is not None
                else metadata_existing.get("retries", 0)
            )
        ),
        "fallback_reason": None,
        "canonicalization_rules": canonicalization_rules
        or metadata_existing.get("canonicalization_rules", []),
        "llm_event_fingerprint_candidate": llm_fingerprint_candidate,
        "backend_event_fingerprint": extraction_model.event_fingerprint or None,
        "backend_event_fingerprint_authoritative": bool(extraction_model.event_fingerprint),
        "backend_event_fingerprint_version": backend_fingerprint_version
        or metadata_existing.get("backend_event_fingerprint_version"),
        "backend_event_fingerprint_input": backend_fingerprint_input
        or metadata_existing.get("backend_event_fingerprint_input"),
        "canonicalizer_version": CANONICALIZER_VERSION,
        "normalized_text_hash": normalized_text_hash,
        "replay_identity_key": replay_identity_key,
        "canonical_payload_hash": canonical_payload_hash,
        "claim_hash": claim_hash,
        "action_class": action_class,
        "event_time_bucket": time_bucket,
        "replay_reused": replay_reused,
        "content_reused": content_reused,
        "content_reuse_source_extraction_id": content_reuse_source_extraction_id,
        "canonical_payload_unchanged": canonical_payload_unchanged,
        "impact_scoring": {
            "raw_llm_score": calibration.raw_llm_score,
            "calibrated_score": calibration.calibrated_score,
            "score_band": calibration.score_band,
            "shock_flags": calibration.shock_flags,
            "rules_fired": calibration.rules_fired,
            "impact_score_breakdown": calibration.score_breakdown.get("components", {}),
            "enrichment_route": calibration.enrichment_route,
            "score_breakdown": calibration.score_breakdown,
        },
        "structured_contract": {
            "event_type": extraction_model.event_type,
            "directionality": extraction_model.directionality,
            "tag_count": len(extraction_model.tags),
            "relation_count": len(extraction_model.relations),
            "dropped_tag_count": dropped_tag_count,
            "dropped_relation_count": dropped_relation_count,
        },
    }
    db.flush()

    return ProcessedExtraction(
        extraction_row=extraction,
        extraction_model=extraction_model,
        calibration=calibration,
        canonical_payload_hash=canonical_payload_hash,
        claim_hash=claim_hash,
        action_class=action_class,
        time_bucket=time_bucket,
    )
