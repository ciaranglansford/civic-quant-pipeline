# Architecture

> Legacy sectioned architecture note retained for context. Prefer `docs/architecture.md` and `docs/system-flow.md` for current implementation truth.

## Purpose

Define the pipeline architecture for a Telegram wire-bulletin intelligence system and clearly separate:
- current implementation,
- target-state architecture,
- future optional enhancements.

## Current Implementation

### Runtime Processes

1. API process (`uvicorn app.main:app`)
2. Listener process (`python -m listener.telegram_listener`)
3. Jobs (`run_phase2_extraction`, `run_digest`, operational reset/test jobs)

### Implemented Data Path

1. Listener polls Telegram (`get_messages` loop), identifies unseen bulletins, posts to ingest API.
2. Ingest endpoint validates payload and persists idempotent `raw_messages` records.
3. Normalization creates deterministic `normalized_text`.
4. Phase2 job selects eligible raw messages, runs OpenAI extraction, validates strict schema, and persists structured extraction fields.
5. Routing + event manager cluster observations into canonical events.
6. Digest job runs deterministic event selection and optional LLM synthesis to publish a structured briefing.

### Storage Model (Implemented)

- `raw_messages`: immutable source records
- `message_processing_states`: extraction state machine
- `extractions`: structured claim extraction + typed retrieval columns + payload/metadata JSON
- `routing_decisions`: deterministic triage/routing outputs
- `events` and `event_messages`: evolving event clusters and links
- `published_posts`: reporting audit trail

### Current Module Ownership (Implemented)

- `app/routers/*`: thin HTTP adapters.
- `app/workflows/phase2_pipeline.py`: orchestration for phase2 sequencing/state.
- `app/contexts/ingest/*`: source envelope + normalization + raw persistence.
- `app/contexts/extraction/*`: prompting/client/validation/canonicalization/reuse.
- `app/contexts/triage/*`: calibration + triage + routing decisions.
- `app/contexts/events/*`: event identity, matching, and upsert logic.
- `app/contexts/entities/*`: entity indexing/query helpers.
- `app/contexts/enrichment/*`: enrichment candidate selection and provider seam.
- `app/contexts/feed/*`: feed query endpoints backing logic.
- `app/digest/*`: canonical digest/report semantics + synthesis + artifact/publish flow.

Digest transition note:
- `app/services/digest_*` and `app/services/telegram_publisher.py` are temporary compatibility shims only.

## Target-State Pipeline

### Stage 1: Raw Ingest
- Capture every bulletin exactly as received.
- Persist immutable source-of-record row.
- Idempotent ingest, no semantic interpretation.

### Stage 2: Structural Normalization
- Deterministic cleanup of wire-style noise (spacing, markers, punctuation patterns, attribution forms).
- Produce stable extraction input.
- Preprocessing only, not verification.

### Stage 3: AI Claim Extraction
- Extract literal reported claim from bulletin text.
- Preserve attribution and uncertainty language.
- Do not convert reported claims into confirmed facts.

### Stage 4: Deterministic Post-Processing / Triage
- Validate schema.
- Canonicalize entities and sources.
- Normalize key output values.
- Compute deterministic triage outcomes (`archive`, `update`, `monitor`, `promote`).

### Stage 5: Event Clustering
- Treat each message as an observation.
- Cluster related observations into an evolving event.
- Use events as downstream unit for reasoning and reporting.

### Stage 6: Entity Indexing / Dataset Construction
- Build queryable internal dataset over messages, extractions, events, and entities.
- Support filtering by topic, ticker, country, breaking relevance, and time window.

### Stage 7: Deferred Enrichment / External Validation
- Run selective validation only for chosen events.
- Confirm, deny, or enrich prior reported claims in later workflows.

### Stage 8: Scheduled Reporting
- Select event candidates deterministically (window + thresholds + publication eligibility).
- Synthesize digest composition (top developments + topic bullets) with strict validation and deterministic fallback.
- Generate reporting from structured event-level data, not raw bulletin text.

## Future Optional Enhancements

- Multi-source evidence aggregation and reliability scoring.
- More advanced deterministic normalization rules for wire-format edge cases.
- Rich ranking and downstream distribution channels.
- Additional analyst/report outputs from indexed dataset slices.

## Non-Negotiable Principles

1. Raw messages are immutable source-of-record data.
2. Normalization is deterministic preprocessing, not truth validation.
3. AI extraction captures literal reported claims, not verified truth.
4. `confidence` refers to extraction certainty, not factual truth.
5. `impact_score` reflects significance of the reported claim if taken at face value.
6. Deterministic post-processing is required to stabilize output.
7. Events, not individual messages, are the downstream unit for indexing/reporting.
8. Validation/enrichment happens later and selectively.
9. Scheduled reporting consumes structured event data, not raw messages.
10. LLM can shape digest wording/semantic merge but cannot control publication state transitions.

