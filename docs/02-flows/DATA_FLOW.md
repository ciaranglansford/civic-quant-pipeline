# Data Flow

> Legacy staged flow document retained for context. Prefer `docs/system-flow.md` for current runtime-truth flow.

## Overview

This document describes the runtime flow for Telegram wire-bulletin ingestion and processing.

It distinguishes:
- Current implementation,
- Target-state intended architecture,
- Future optional enhancements.

For operational execution details, see:
- `docs/04-operations/operations_and_scheduling.md`

## Current Implementation Flow

### Trigger
- Source: Telegram wire-style bulletin feed.
- Listener mode: poll loop (`get_messages`), not push subscription.

### Steps
1. Listener polls source and builds ingest payload.
2. Listener posts payload to `POST /ingest/telegram` with retries.
3. Backend validates payload and normalizes text deterministically.
4. Backend stores immutable idempotent `raw_messages` row.
5. Backend creates/maintains `message_processing_states` (`pending` on ingest).
6. Phase2 extraction job selects eligible rows and calls OpenAI extraction.
7. Strict schema validation runs before persistence.
8. Structured extraction is persisted (`extractions` typed fields + payload/metadata JSON).
9. Deterministic routing + event clustering persist `routing_decisions`, `events`, and `event_messages`.
10. Scheduled digest job performs deterministic event selection + pre-dedupe, optional LLM synthesis, strict validation/fallback, and persists `published_posts`.

## Execution Touchpoints by Stage

### Stage 1: Raw Capture
- Responsible module/job:
  - `listener/telegram_listener.py`
  - `app/routers/ingest.py`
  - `app/contexts/ingest/ingest_pipeline.py`
- Local commands:
  - `python -m listener.telegram_listener`
  - `uvicorn app.main:app --reload`
- Observable outputs:
  - logs: listener post + ingest success/failure
  - DB: `raw_messages`, `message_processing_states`

### Stage 2: Structural Normalization
- Responsible module/job:
  - `app/contexts/ingest/normalization.py`
- Local command:
  - runs as part of ingest request path
- Observable outputs:
  - DB: `raw_messages.normalized_text`

### Stage 3: AI Claim Extraction
- Responsible module/job:
  - `app/jobs/run_phase2_extraction.py`
  - `app/workflows/phase2_pipeline.py`
- Local commands:
  - `python -m app.jobs.run_phase2_extraction`
  - `python -m app.jobs.test_openai_extract`
- Observable outputs:
  - logs: phase2 config/extractor/summary
  - DB: `extractions`, `message_processing_states`

### Stage 4: Deterministic Post-Processing / Triage
- Responsible module/job:
  - `app/contexts/triage/routing_engine.py`
  - `app/contexts/triage/triage_engine.py`
  - `app/contexts/triage/routing_decisions.py`
  - `app/contexts/extraction/canonicalization.py`
- Local command:
  - executed inside phase2 batch
- Observable outputs:
  - DB: `routing_decisions`
  - canonical summary safety changes in `extractions.canonical_payload_json` (raw payload unchanged)

### Stage 5: Event Clustering
- Responsible module/job:
  - `app/contexts/events/event_manager.py`
- Local command:
  - executed inside phase2 batch
- Observable outputs:
  - logs: `event_create` / `event_update`
  - DB: `events`, `event_messages`

### Stage 6: Entity Indexing / Dataset Construction
- Responsible module/job:
  - current indexed storage contracts in extraction/event tables
- Local command:
  - use extraction batch and DB queries
- Observable outputs:
  - typed/indexed extraction fields for topic/time/impact queries

### Stage 7: Deferred Enrichment / Validation
- Responsible module/job:
  - `app/contexts/enrichment/enrichment_selection.py` (candidate selection in current flow)
- Local command:
  - executed inside phase2 batch
- Observable outputs:
  - DB: `enrichment_candidates`

### Stage 8: Scheduled Reporting
- Responsible module/job:
  - `app/jobs/run_digest.py`
  - `app/digest/orchestrator.py`
  - `app/digest/builder.py`
  - `app/digest/synthesizer.py`
- Local command:
  - `python -m app.jobs.run_digest`
- Observable outputs:
  - logs: synthesis fallback reasons, publish/skip lines
  - DB: `digest_artifacts`, `published_posts`

## Target-State Staged Pipeline

### 1) Raw Capture
- What: persist bulletins exactly as received.
- Why: immutable source-of-record for audit and replay.
- Consumes: listener payload.
- Produces: raw message rows.

### 2) Structural Normalization
- What: deterministic cleanup of wire-style formatting noise.
- Why: stable inputs for extraction and matching.
- Consumes: raw text.
- Produces: normalized text.

### 3) AI Claim Extraction
- What: extract literal reported claim with attribution/uncertainty.
- Why: convert bulletin text into structured claim data.
- Consumes: normalized text + message metadata.
- Produces: validated structured extraction payload.

### 4) Deterministic Post-Processing / Triage
- What: code-based validation, canonicalization, ranking/triage.
- Why: stabilize AI outputs and reduce noisy actioning.
- Consumes: extraction payload.
- Produces: deterministic triage/routing outcomes.
  - Raw LLM `impact_score` is preserved for auditability.
  - Backend-calibrated impact score is authoritative for triage/routing/event impact/enrichment decisions.
  - Score bands are derived only after deterministic caps/boosts/shock gating rules are applied.
  - Repetitive low-delta follow-ons are downgraded with deterministic burst suppression.
  - Local domestic incident patterns are capped to monitor-or-lower and forced evidence-required.

### 5) Event Clustering
- What: cluster repeated/incremental/contradictory observations into evolving event records.
- Why: events are the downstream unit for reasoning and reporting.
- Consumes: message-level extraction + routing context.
- Produces: canonical events and message-event links.

### 6) Entity Indexing / Dataset Construction
- What: maintain queryable dataset over events/extractions/entities.
- Why: power retrieval by topic, ticker, country, breaking relevance, and time range.
- Consumes: structured persisted outputs.
- Produces: internal analytical query surface.

### 7) Deferred Enrichment / External Validation
- What: selective external corroboration and enrichment.
- Why: separate verification from raw capture and claim extraction.
- Consumes: selected events.
- Produces: enriched event confidence/corroboration state.

### 8) Scheduled Reporting
- What: generate synthesized briefings from structured event-level data.
- Why: avoid reporting from raw noisy bulletin text.
- Consumes: curated event dataset.
- Produces: canonical digest artifacts + destination payload publications with ID-level coverage traceability.

## Key Semantics

- Bulletins are treated as reported claims until validated later.
- `confidence` is extraction/classification certainty.
- Raw `impact_score` is model-reported claim significance signal.
- Calibrated impact score is deterministic operational severity used downstream.

## Future Optional Enhancements

- Selective external evidence pipelines and reliability scoring.
- Additional event-level reporting channels.
- Expanded normalization/canonicalization rules for wire feed variants.



