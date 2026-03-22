from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..contexts.opportunity_memo import (
    OPPORTUNITY_TOPICS,
    OpenAiOpportunityMemoWriter,
    OpenAiOpportunityResearchProvider,
    OpportunityMemoRunResult,
    OpportunityMemoWriter,
    OpportunityMemoWriterError,
    OpportunityResearchError,
    OpportunityResearchProvider,
    build_opportunity_memo_input_pack,
    build_research_plan,
    canonical_hash_for_opportunity_memo,
    input_hash_for_opportunity_memo,
    rank_topic_candidates,
    render_opportunity_memo_markdown,
    render_opportunity_memo_telegram_html,
    validate_opportunity_memo,
)
from ..contexts.opportunity_memo.constants import (
    MEMO_DESTINATION_TELEGRAM,
    MEMO_SELECTION_MODE_AUTO,
    MEMO_SELECTION_MODE_MANUAL,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_DELIVERY_FAILED,
    RUN_STATUS_NO_TOPIC_FOUND,
    RUN_STATUS_RUNNING,
    RUN_STATUS_VALIDATION_FAILED,
)
from ..digest.adapters.telegram import send_telegram_text
from ..models import (
    OpportunityMemoArtifact,
    OpportunityMemoDelivery,
    OpportunityMemoExternalSource,
    OpportunityMemoInputEvent,
    OpportunityMemoRun,
)


logger = logging.getLogger("civicquant.opportunity_memo")


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _recent_memo_topics(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
) -> set[str]:
    span = end_time - start_time
    lookback = max(span, timedelta(hours=24))
    from_time = start_time - lookback

    rows = (
        db.query(OpportunityMemoRun)
        .filter(
            OpportunityMemoRun.completed_at.is_not(None),
            OpportunityMemoRun.completed_at >= from_time,
            OpportunityMemoRun.status.in_([RUN_STATUS_COMPLETED, RUN_STATUS_DELIVERY_FAILED]),
            OpportunityMemoRun.selected_topic.is_not(None),
        )
        .all()
    )
    out: set[str] = set()
    for row in rows:
        if row.selected_topic:
            out.add(str(row.selected_topic))
    return out


def _generation_settings(settings: Settings) -> dict[str, object]:
    return {
        "topic_selection_threshold": settings.opportunity_memo_topic_score_threshold,
        "min_supporting_events": settings.opportunity_memo_min_supporting_events,
        "min_external_sources": settings.opportunity_memo_min_external_sources,
        "research_model": settings.opportunity_memo_research_model or settings.openai_model,
        "writer_model": settings.opportunity_memo_writer_model or settings.openai_model,
        "source_limit": settings.opportunity_memo_external_source_limit,
    }


def _default_research_provider(settings: Settings) -> OpportunityResearchProvider:
    return OpenAiOpportunityResearchProvider(
        timeout_seconds=settings.opportunity_memo_openai_timeout_seconds,
        max_retries=settings.opportunity_memo_openai_max_retries,
    )


def _default_writer(settings: Settings) -> OpportunityMemoWriter:
    return OpenAiOpportunityMemoWriter(
        timeout_seconds=settings.opportunity_memo_openai_timeout_seconds,
        max_retries=settings.opportunity_memo_openai_max_retries,
    )


def run_opportunity_memo(
    db: Session,
    *,
    start_time: datetime,
    end_time: datetime,
    topic: str | None = None,
    settings: Settings | None = None,
    research_provider: OpportunityResearchProvider | None = None,
    memo_writer: OpportunityMemoWriter | None = None,
) -> OpportunityMemoRunResult:
    settings = settings or get_settings()
    start_utc = _to_utc_naive(start_time)
    end_utc = _to_utc_naive(end_time)
    if start_utc >= end_utc:
        raise ValueError("start_time must be earlier than end_time")

    run = OpportunityMemoRun(
        run_key=str(uuid.uuid4()),
        window_start_utc=start_utc,
        window_end_utc=end_utc,
        requested_topic=topic,
        selection_mode=MEMO_SELECTION_MODE_MANUAL if topic is not None else MEMO_SELECTION_MODE_AUTO,
        status=RUN_STATUS_RUNNING,
        started_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()

    if topic is not None and topic not in OPPORTUNITY_TOPICS:
        run.status = RUN_STATUS_VALIDATION_FAILED
        run.error_message = f"unsupported topic '{topic}'. allowed topics={','.join(OPPORTUNITY_TOPICS)}"
        run.validation_errors_json = [{"code": "unsupported_topic", "message": run.error_message}]
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        return OpportunityMemoRunResult(
            run_id=run.id,
            status=run.status,
            selected_topic=None,
            topic_score=None,
            message=run.error_message,
            validation_errors=run.validation_errors_json,
        )

    recent_topics = _recent_memo_topics(db, start_time=start_utc, end_time=end_utc)
    topic_universe = [topic] if topic is not None else list(OPPORTUNITY_TOPICS)
    ranked_topics = rank_topic_candidates(
        db,
        start_time=start_utc,
        end_time=end_utc,
        topic_universe=topic_universe,
        limit=max(1, len(topic_universe)),
        recent_memo_topics=recent_topics,
    )

    selected_topic = topic
    selected_topic_score = 0.0
    selection_reason = "manual_topic_override" if topic is not None else "auto_selection_threshold_passed"
    selected_topic_breakdown: dict[str, float] = {
        "normalized_event_count": 0.0,
        "normalized_weighted_impact": 0.0,
        "normalized_novelty": 0.0,
        "normalized_coherence": 0.0,
        "normalized_actionability": 0.0,
    }

    if topic is None:
        if not ranked_topics or ranked_topics[0].topic_score < settings.opportunity_memo_topic_score_threshold:
            run.status = RUN_STATUS_NO_TOPIC_FOUND
            run.error_message = "no memo-worthy topic found"
            run.selection_diagnostics_json = {
                "threshold": settings.opportunity_memo_topic_score_threshold,
                "ranked_topics": [row.model_dump(mode="json") for row in ranked_topics],
            }
            run.completed_at = datetime.utcnow()
            run.updated_at = datetime.utcnow()
            db.flush()
            logger.info(
                "opportunity_memo_no_topic run_id=%s window_start=%s window_end=%s",
                run.id,
                start_utc.isoformat(),
                end_utc.isoformat(),
            )
            return OpportunityMemoRunResult(
                run_id=run.id,
                status=run.status,
                selected_topic=None,
                topic_score=None,
                message=run.error_message,
            )

        selected_topic = ranked_topics[0].topic
        selected_topic_score = ranked_topics[0].topic_score
        selected_topic_breakdown = ranked_topics[0].breakdown.model_dump(mode="json")
    else:
        if ranked_topics:
            selected_topic_score = ranked_topics[0].topic_score
            selected_topic_breakdown = ranked_topics[0].breakdown.model_dump(mode="json")

    assert selected_topic is not None

    input_pack, topic_events = build_opportunity_memo_input_pack(
        db,
        start_time=start_utc,
        end_time=end_utc,
        topic=selected_topic,
        topic_score=selected_topic_score,
        selection_reason=selection_reason,
        topic_breakdown=selected_topic_breakdown,
    )

    run.selected_topic = selected_topic
    run.topic_score = float(selected_topic_score)
    run.selected_primary_driver_key = (
        input_pack.selected_primary_driver.driver_key
        if input_pack.selected_primary_driver is not None
        else None
    )
    run.selected_primary_driver_score = (
        float(input_pack.selected_primary_driver.score)
        if input_pack.selected_primary_driver is not None
        else None
    )
    run.selection_diagnostics_json = input_pack.selection_diagnostics.model_dump(mode="json")
    run.updated_at = datetime.utcnow()
    db.flush()

    provider = research_provider or _default_research_provider(settings)
    writer = memo_writer or _default_writer(settings)

    try:
        research_plan = build_research_plan(input_pack)
        external_pack = provider.retrieve(
            input_pack=input_pack,
            plan=research_plan,
            settings=settings,
        )
    except OpportunityResearchError as exc:
        run.status = RUN_STATUS_VALIDATION_FAILED
        run.error_message = str(exc)
        run.validation_errors_json = [
            {"code": "external_research_failed", "message": str(exc)},
        ]
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        return OpportunityMemoRunResult(
            run_id=run.id,
            status=run.status,
            selected_topic=selected_topic,
            topic_score=selected_topic_score,
            message=run.error_message,
            validation_errors=run.validation_errors_json,
        )

    if settings.opportunity_memo_external_source_limit > 0:
        external_pack.sources = external_pack.sources[: settings.opportunity_memo_external_source_limit]

    try:
        memo = writer.write(
            input_pack=input_pack,
            external_evidence=external_pack,
            settings=settings,
        )
    except OpportunityMemoWriterError as exc:
        run.status = RUN_STATUS_VALIDATION_FAILED
        run.error_message = str(exc)
        run.validation_errors_json = [
            {"code": "writer_failed", "message": str(exc)},
        ]
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        return OpportunityMemoRunResult(
            run_id=run.id,
            status=run.status,
            selected_topic=selected_topic,
            topic_score=selected_topic_score,
            message=run.error_message,
            validation_errors=run.validation_errors_json,
        )

    validation = validate_opportunity_memo(
        memo=memo,
        input_pack=input_pack,
        external_evidence=external_pack,
        min_supporting_events=settings.opportunity_memo_min_supporting_events,
        min_external_sources=settings.opportunity_memo_min_external_sources,
        topic_selection_threshold=settings.opportunity_memo_topic_score_threshold,
    )
    if not validation.ok:
        run.status = RUN_STATUS_VALIDATION_FAILED
        run.error_message = "; ".join(issue.message for issue in validation.errors)
        run.validation_errors_json = [issue.model_dump(mode="json") for issue in validation.errors]
        run.completed_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.flush()
        return OpportunityMemoRunResult(
            run_id=run.id,
            status=run.status,
            selected_topic=selected_topic,
            topic_score=selected_topic_score,
            message=run.error_message,
            validation_errors=run.validation_errors_json,
        )

    generation_settings = _generation_settings(settings)
    selected_primary_driver_payload = (
        input_pack.selected_primary_driver.model_dump(mode="json")
        if input_pack.selected_primary_driver is not None
        else {}
    )
    input_hash = input_hash_for_opportunity_memo(
        window_start_utc=start_utc,
        window_end_utc=end_utc,
        selected_topic=selected_topic,
        selected_event_ids=input_pack.selected_event_ids,
        selected_primary_driver=selected_primary_driver_payload,
        generation_settings=generation_settings,
    )
    canonical_hash = canonical_hash_for_opportunity_memo(memo=memo)
    canonical_text = render_opportunity_memo_markdown(
        memo=memo,
        topic=selected_topic,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
    )
    telegram_payload = render_opportunity_memo_telegram_html(
        memo=memo,
        topic=selected_topic,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
    )

    artifact = OpportunityMemoArtifact(
        run_id=run.id,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
        topic=selected_topic,
        input_hash=input_hash,
        canonical_hash=canonical_hash,
        memo_json=memo.model_dump(mode="json"),
        traceability_json=memo.traceability.model_dump(mode="json"),
        canonical_text=canonical_text,
        status="created",
    )
    db.add(artifact)
    db.flush()

    mapping_by_event_id = {
        int(row.get("id") or 0): dict(row.get("mapping_diagnostics") or {})
        for row in topic_events
    }
    supporting_event_ids = (
        set(input_pack.selected_primary_driver.supporting_event_ids)
        if input_pack.selected_primary_driver is not None
        else set()
    )
    timeline_by_event_id = {item.event_id: item for item in input_pack.event_timeline}
    for index, event_id in enumerate(input_pack.selected_event_ids):
        timeline = timeline_by_event_id.get(event_id)
        db.add(
            OpportunityMemoInputEvent(
                run_id=run.id,
                artifact_id=artifact.id,
                event_id=event_id,
                event_time=timeline.event_time if timeline is not None else None,
                summary=timeline.summary if timeline is not None else None,
                impact_score=timeline.impact_score if timeline is not None else None,
                position_index=index,
                driver_supporting=event_id in supporting_event_ids,
                mapping_diagnostics_json=mapping_by_event_id.get(event_id, {}),
            )
        )

    for source in external_pack.sources:
        db.add(
            OpportunityMemoExternalSource(
                artifact_id=artifact.id,
                source_id=source.source_id,
                source_type=source.source_type,
                title=source.title,
                publisher=source.publisher,
                retrieved_at=source.retrieved_at,
                query=source.query,
                summary=source.summary,
                claim_support_tags=list(source.claim_support_tags),
                url=str(source.url) if source.url is not None else None,
            )
        )

    delivery = OpportunityMemoDelivery(
        artifact_id=artifact.id,
        destination=MEMO_DESTINATION_TELEGRAM,
        status="failed",
        attempted_at=datetime.utcnow(),
        content=telegram_payload,
        content_hash=_content_hash(telegram_payload),
    )
    db.add(delivery)
    db.flush()

    # Persist artifact + source links before any delivery attempt.
    db.commit()

    try:
        external_ref = send_telegram_text(telegram_payload, settings=settings)
        delivery.status = "published"
        delivery.published_at = datetime.utcnow()
        delivery.last_error = None
        delivery.external_ref = external_ref
        run.status = RUN_STATUS_COMPLETED
        artifact.status = "delivered"
        delivery_status = "published"
    except Exception as exc:  # noqa: BLE001
        delivery.status = "failed"
        delivery.published_at = None
        delivery.last_error = str(exc)[:1000]
        delivery.external_ref = None
        run.status = RUN_STATUS_DELIVERY_FAILED
        artifact.status = "delivery_failed"
        delivery_status = "failed"

    run.completed_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    db.flush()
    db.commit()

    logger.info(
        "opportunity_memo_run_done run_id=%s status=%s topic=%s topic_score=%.4f artifact_id=%s delivery_status=%s",
        run.id,
        run.status,
        selected_topic,
        selected_topic_score,
        artifact.id,
        delivery_status,
    )
    return OpportunityMemoRunResult(
        run_id=run.id,
        status=run.status,
        selected_topic=selected_topic,
        topic_score=selected_topic_score,
        artifact_id=artifact.id,
        delivery_status=delivery_status,
        validation_errors=[],
        message=(
            "; ".join(issue.message for issue in validation.warnings)
            if validation.warnings
            else None
        ),
    )
