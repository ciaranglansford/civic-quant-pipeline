## LLM Usage and Prompt Execution Contract

This document defines how LLM extraction fits into the wire-bulletin pipeline and how outputs must be stabilized for deterministic downstream processing.

### Stage Context

LLM extraction sits at Stage 3 (AI extraction of literal reported claim), after raw ingest and normalization, and before deterministic post-processing/triage.

## 1) Extraction Agent Contract

### Purpose

Transform normalized wire bulletins into strict structured claim payloads suitable for deterministic triage and event clustering.

### Inputs

- `normalized_text`
- `message_time`
- `source_channel_name`

### Required Output Fields

- `topic`
- `entities.countries`
- `entities.orgs`
- `entities.people`
- `entities.tickers`
- `affected_countries_first_order`
- `market_stats[]`
- `sentiment`
- `confidence` (`0..1`)
- `impact_score` (`0..100`)
- `is_breaking`
- `breaking_window`
- `event_time`
- `source_claimed`
- `summary_1_sentence`
- `keywords`
- `event_fingerprint`

### Semantic Contract (Non-Negotiable)

- Extraction is literal reported-claim capture.
- Extraction is not truth adjudication.
- Attribution and uncertainty language must be preserved, not silently removed.
- `confidence` means extraction certainty.
- `impact_score` means significance of the reported claim if taken at face value.

## 2) Prompt and Validation Rules

### Prompt Versioning

- Active prompt template version: `extraction_agent_v2`.
- `extraction_agent_v1` remains unchanged for reproducibility/auditability.
- `prompt_version` must be persisted per extraction row.

### Prompt Constraints

- Return exactly one JSON object.
- No markdown/code fences/prose.
- No additional keys.
- Enum values must match allowed sets.
- Numeric ranges must pass validation.

### Runtime Validation

- Parse as strict JSON object.
- Reject unknown keys or invalid enum/range values.
- On failure: classify and record error (`validation_error` / `provider_error`), keep row retryable.

## 3) Downstream Handoff to Deterministic Triage

### Why this handoff exists

Deterministic code must stabilize model outputs before routing, clustering, and reporting.

### Handoff Inputs

- Raw validated extraction payload
- Message metadata and processing context

### Handoff Outputs (Deterministic)

- Canonicalized payload used by routing/event logic
- Stable triage outcomes (priority/action/flags)
- Cluster-ready fingerprint and event-time context

### Stability Constraints

- Equivalent facts should preserve stable `event_fingerprint` behavior.
- Triage outcomes must be reproducible for same validated inputs/config.
- Confidence/impact are treated as bounded model signals in deterministic routing.
  - Raw values remain persisted unchanged for auditability.
  - Stage 1 routing decisions use deterministic score bands and novelty/material-change gates.
  - Repetitive low-delta bursts are downgraded by deterministic burst-cap rules.
  - Local domestic incident patterns are capped to monitor-or-lower with evidence-required override.
- Summary safety guardrail is deterministic post-processing in canonical payload only.
  - `payload_json` (raw validated extraction) is not rewritten.
  - `canonical_payload_json` may apply minimal high-risk attribution safety rewrites.

## 4) Local Validation Workflow

### Run extraction probe
- `python -m app.jobs.test_openai_extract`

Expected:
- extractor identity printed
- OpenAI usage metadata printed
- validated JSON output printed

### Run scheduled/manual extraction batch
- `python -m app.jobs.run_phase2_extraction`

Expected:
- config log line
- extractor selection log line
- run summary with selected/processed/completed/failed counts

### Verify persisted outputs

- `extractions` contains typed retrieval fields
- `payload_json` stores raw validated extraction
- `canonical_payload_json` stores deterministic canonicalized extraction
- `metadata_json` stores provider telemetry and canonicalization context
- failures remain explicit in `message_processing_states.last_error`
