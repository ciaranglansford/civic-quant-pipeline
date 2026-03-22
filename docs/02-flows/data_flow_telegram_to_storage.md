## Data Flow - Telegram Bulletin to Structured Intelligence

> Legacy flow note retained for history. Prefer `docs/system-flow.md` for current implementation-truth flow.

### Purpose

Describe staged processing for Telegram wire-bulletin inputs, with explicit separation of current implementation and target-state intent.

### Input Domain

This system ingests headline/ticker bulletins that are often:
- brief and urgent,
- source-attributed,
- repetitive,
- incremental,
- occasionally contradictory,
- and potentially unverified at ingest time.

## Current Implementation (Implemented)

1. Ingest
- Listener polls channel, builds payload, and posts to backend.
- Backend validates schema and stores immutable raw row idempotently.

2. Normalize
- Deterministic normalization currently focuses on whitespace stabilization.

3. Extract (Phase2 Scheduled/Manual)
- Phase2 job selects eligible raw messages.
- OpenAI extraction runs with strict schema validation.
- Invalid outputs are marked failed; no silent stub substitution.

4. Route and Cluster
- Deterministic routing computes action/priority/flags.
- Event manager clusters observations into canonical events.

5. Report
- Digest job queries events and publishes event-level summaries.

## Target-State Stages

### Stage 1 - Raw Ingest
- Capture and persist bulletin exactly as received.
- No truth validation at this stage.

### Stage 2 - Structural Normalization
- Deterministically normalize formatting and wire markers.
- Preserve claim content while reducing formatting variance.

### Stage 3 - AI Extraction of Literal Reported Claim
- Extract what bulletin explicitly reports.
- Preserve attribution and uncertainty phrases.
- Do not rewrite claim as confirmed fact.

### Stage 4 - Deterministic Post-Processing / Triage
- Validate schema and canonicalize values.
- Compute deterministic actioning (`archive`, `update`, `monitor`, `promote`).

### Stage 5 - Event Clustering
- Treat each message as an observation.
- Cluster to evolving event records.

### Stage 6 - Entity Indexing / Dataset Construction
- Maintain queryable dataset by topic/ticker/country/breaking/time.

### Stage 7 - Deferred Enrichment / Validation
- Current status: deterministic enrichment candidate selection is implemented.
- External-provider enrichment execution remains a later stage.

### Stage 8 - Scheduled Reporting
- Build reporting from event-level structured data, not raw messages.

## Notes on Semantics

- `confidence`: extraction certainty.
- `impact_score`: claim significance if taken at face value.
- Neither metric implies factual confirmation.

