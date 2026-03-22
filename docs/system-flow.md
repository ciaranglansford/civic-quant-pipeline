# System Flow

## End-to-End Flow

1. Source capture
- `listener/telegram_listener.py` polls Telegram and posts to `POST /ingest/telegram`.
- `POST /ingest/source` supports non-Telegram sources.

2. Ingest + normalization
- `app/routers/ingest.py` normalizes text via `app/contexts/ingest/normalization.py`.
- `app/contexts/ingest/ingest_pipeline.py` stores `raw_messages` idempotently on `(source_channel_id, telegram_message_id)`.
- A `message_processing_states` row is created with `status="pending"`.

3. Phase2 batch selection and locking
- `app/workflows/phase2_pipeline.py` acquires `processing_locks.lock_name="phase2_extraction"`.
- Eligible raws include `pending`, `failed`, and expired-lease `in_progress`.

4. Extraction + validation + canonicalization
- `materialize_extraction_for_raw_message` in `app/contexts/extraction/processing.py`.
- Reuse order:
  - replay identity reuse (same raw + same extraction contract)
  - content reuse (same normalized text + same extraction contract within configured window)
  - otherwise OpenAI call
- Raw model output is strictly parsed in `extraction_validation.py`.
- Canonical payload is produced in `canonicalization.py` and persisted separately from raw validated payload.

5. Deterministic scoring, triage, and routing
- `app/contexts/triage/impact_scoring.py` computes calibrated score and enrichment route.
- `app/contexts/triage/decisioning.py` computes triage action and routing decision.
- Routing decision is persisted in `routing_decisions`.

6. Event clustering and structured facets
- `app/contexts/events/event_manager.py` creates/updates events and links via `event_messages`.
- `app/contexts/events/structured_persistence.py` replaces `event_tags` and `event_relations` from canonical extraction output.
- Identity conflict cases mark `events.review_required=true` and are downgraded for routing.

7. Additional phase2 side effects
- `app/contexts/entities/entity_indexing.py` stores `entity_mentions`.
- `app/contexts/themes/evidence.py` stores deterministic event-theme evidence matches.
- `app/contexts/enrichment/enrichment_selection.py` stores `enrichment_candidates`.
- `message_processing_states` is finalized as `completed` or `failed`.

8. Deep enrichment (Pass B)
- `app/workflows/deep_enrichment_pipeline.py` acquires `processing_locks.lock_name="deep_enrichment"`.
- `app/contexts/enrichment/deep_enrichment.py` materializes `event_deep_enrichments` for selected `deep_enrich` candidates.

9. Digest pipeline
- `app/digest/orchestrator.py` freezes window and fetches events from `app/digest/query.py`:
  - filter by `last_updated_at` window
  - filter by impact threshold (`> 25.0`)
  - optional destination unpublished filter
- `app/digest/builder.py` builds source events and deterministic pre-dedupe groups.
- `app/digest/synthesizer.py` runs LLM synthesis when enabled, else deterministic fallback.
- Output is strictly validated; invalid synthesis falls back.
- Artifact is persisted and committed before publish attempt.
- Publish outcomes are recorded in `published_posts`.
- Covered event IDs are marked published per destination (`is_published_telegram` / `is_published_twitter`).

10. Theme batch pipeline
- `app/workflows/theme_batch_pipeline.py` runs per theme/cadence window.
- Ensures evidence rows for window, builds evidence bundle, runs internal enrichment provider, creates:
  - `theme_opportunity_assessments`
  - `thesis_cards`
  - `theme_brief_artifacts`
- Run lifecycle is persisted in `theme_runs`.

## Key Invariants

- Raw ingest records are immutable source-of-record rows.
- Canonical digest artifact is persisted before any publish attempt.
- Digest coverage is tracked at source event ID level.
- Model output never directly controls publish state transitions.
- Claims remain claim-level representations, not confirmed facts.
