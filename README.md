# Civicquant Intelligence Pipeline

Civicquant is a structured intelligence pipeline for wire-style bulletin streams. It is not a generic news aggregator and it is not a raw event feed formatter.

The system combines:
- deterministic ingestion, storage, filtering, and publication state management
- LLM extraction of structured claims
- LLM-assisted digest synthesis with deterministic validation and fallback
- deterministic batch thematic thesis generation (POC) over scheduled windows

## What The System Produces

The pipeline converts short bulletin text into:
- structured event records (`events`) representing reported claims
- a stronger structured event object in extraction payloads (`event_type`, `directionality`, controlled `tags`, typed `relations`, `impact_inputs`)
- scheduled digests that synthesize those events into a briefing format
- scheduled thematic opportunity assessments and thesis cards (batch-only, internal POC)

Important truth-model rule:
- events and digest bullets represent reported claims, not confirmed facts
- uncertainty and attribution language (for example "reportedly", "according to", "claimed") should be preserved when present

## Pipeline Architecture

`Ingestion -> Extraction (LLM) -> Event Storage -> Digest Selection (deterministic) -> Digest Synthesis (LLM) -> Rendering -> Publishing`

## Internal Module Layout

This repository is a modular monolith with one FastAPI app and context-owned modules.

- `app/routers/*`: thin HTTP adapters only
- `app/workflows/phase2_pipeline.py`: phase2 sequencing, retries, locks, and state transitions
- `app/contexts/ingest/*`: ingest envelope mapping + normalization + raw persistence
- `app/contexts/extraction/*`: extraction client, prompt rendering, validation, canonicalization, reuse contracts
- `app/contexts/triage/*`: impact calibration, triage rules, routing decisions, relatedness logic
- `app/contexts/events/*`: event matching/upsert and event-message linking
- `app/contexts/entities/*`: entity mention indexing/query
- `app/contexts/enrichment/*`: enrichment candidate selection + provider seam contracts
- `app/contexts/feed/*`: canonical feed query behavior
- `app/digest/*`: canonical digest/report semantics, artifacts, synthesis, and destination adapters
- `app/contexts/themes/*`: theme/lens registry, matching, evidence persistence, and bundle construction
- `app/contexts/opportunities/*`: enrichment providers, scoring, assessments, thesis cards, and briefs
- `app/workflows/theme_batch_pipeline.py`: batch thematic workflow coordinator

Transitional shims intentionally retained in this pass:
- `app/services/digest_*`
- `app/services/telegram_publisher.py`

### Stage-by-stage

1. Ingestion
- Listener posts source messages to ingest routes.
- Backend normalizes text and writes immutable raw rows (`raw_messages`).

2. Extraction (LLM)
- `app/workflows/phase2_pipeline.py` calls the extraction client.
- LLM returns strict JSON, then deterministic validation/canonicalization runs.
- Structured outputs are stored in `extractions`.
- Pass A extraction now emits controlled tags/relations and impact inputs.
- Unknown controlled tag/relation values are dropped safely during canonicalization (core-invalid payloads still fail).

3. Event Storage / Clustering
- Deterministic routing + event upsert logic writes `events` and `event_messages`.
- Normalized structured facets are synced into `event_tags` and `event_relations` for queryability.

4. Digest Selection (deterministic)
- `app/digest/query.py` filters by frozen time window and impact threshold.
- Selection and publication-eligibility checks are deterministic.

5. Digest Synthesis (LLM + deterministic guardrails)
- `app/digest/builder.py` builds `SourceDigestEvent` rows and deterministic pre-dedupe groups.
- `app/digest/synthesizer.py` asks the LLM for structured digest composition.
- Strict validation enforces ID accounting, disjoint coverage, topic validity, and non-empty bullets.
- If synthesis is disabled or invalid, deterministic fallback composition is used.

6. Rendering
- Canonical text render (`app/digest/renderer_text.py`) is produced from `CanonicalDigest`.
- Destination adapters render payloads from canonical semantics only.

7. Publishing
- Artifact is persisted before any publish attempt.
- Per-destination rows are tracked in `published_posts`.
- Covered source event IDs are marked published after successful destination publish.

8. Thematic Batch Thesis (deterministic POC)
- Continuous flow only persists event-theme evidence matches.
- Scheduled batch run evaluates lenses/transmission patterns over a time window.
- Assessments, gated thesis cards, and brief artifacts are persisted.

## Two-Pass Enrichment Model

- Pass A (phase2): extraction + canonicalization + deterministic impact scoring + deterministic enrichment route assignment.
- Pass B (separate job): runs only for `deep_enrich` candidates and persists narrow structured enrichment output in `event_deep_enrichments`.

Deterministic enrichment routes:
- `store_only`
- `index_only`
- `deep_enrich`

Routing is deterministic and inspectable; model output does not decide orchestration.

## LLM Usage

LLM is used in two places:

1. Extraction layer
- Parses normalized message text into structured extraction JSON.
- Output is schema-validated and post-processed deterministically.

2. Digest synthesis layer
- Merges semantically similar developments.
- Composes top developments and topic bullets.
- Produces non-redundant structured digest output.
- Preserves uncertainty/attribution language when source inputs include it.

What the LLM does not control:
- event selection thresholds/window logic
- publication state transitions
- source-event coverage accounting
- artifact deduplication identity
- enrichment route assignment

## Digest Composition

- Top developments are synthesized (not simple "newest N").
- Events represented in top developments do not reappear in topic sections.
- Deterministic pre-dedupe groups obvious duplicates before synthesis.
- LLM can merge same-story groups into one bullet.
- A single bullet can map to multiple `source_event_ids`.
- All covered source event IDs are tracked in the canonical digest and used for publish marking.

## Deterministic vs LLM-driven Components

Deterministic components:
- ingestion and raw persistence
- extraction validation/canonicalization
- digest event selection (window + impact filter + destination publication eligibility)
- pre-dedupe grouping by claim hash / fingerprint / normalized summary
- synthesis output validation
- publication state updates and destination dedupe
- fallback builder behavior

LLM-driven components:
- extraction content interpretation
- digest semantic merging and editorial phrasing
- relative prominence ordering in synthesized briefing text

Why the split exists:
- LLM is used for meaning and synthesis quality.
- Code remains authoritative for state, identity, dedupe rules, and publication safety.

## Failure Handling and Fallback

- Digest synthesis can be disabled (`digest_llm_enabled=false`) or unavailable (missing key/model).
- If synthesis output fails schema/semantic validation, the pipeline falls back to deterministic builder output.
- The pipeline still emits a valid canonical digest object and can continue publishing.

## Design Principles

- LLM for meaning, code for state.
- Never let LLM control publication or state transitions.
- All source events must be accounted for, even when merged.
- Digest is an interpretation layer, not raw data replay.

## Key Runtime Components

- Backend API: `uvicorn app.main:app --reload`
- Listener: `python -m listener.telegram_listener`
- Extraction job: `python -m app.jobs.run_phase2_extraction`
- Deep enrichment job: `python -m app.jobs.run_deep_enrichment`
- Digest job: `python -m app.jobs.run_digest`
- Theme batch job: `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs`

## Configuration Highlights

### Extraction
- `PHASE2_EXTRACTION_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`

### Digest
- `VIP_DIGEST_HOURS`
- `DIGEST_LLM_ENABLED`
- `DIGEST_OPENAI_MODEL`
- `DIGEST_OPENAI_TIMEOUT_SECONDS`
- `DIGEST_OPENAI_MAX_RETRIES`
- `DIGEST_TOP_DEVELOPMENTS_LIMIT`
- `DIGEST_SECTION_BULLET_LIMIT`
- `TG_BOT_TOKEN`
- `TG_VIP_CHAT_ID`

## Quickstart

1. Install dependencies
```bash
pip install -r requirements.txt
```

2. Configure `.env`
- database + API settings
- listener credentials/settings
- extraction settings
- digest settings

3. Run backend
```bash
uvicorn app.main:app --reload
```

4. Run phase2 extraction
```bash
python -m app.jobs.run_phase2_extraction
```

5. Run digest
```bash
python -m app.jobs.run_digest
```

6. Run theme batch POC
```bash
python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily
```

## Digest vs Raw Event Feed

- Raw feed/API event list is an indexed event dataset.
- Digest is a synthesized briefing built from selected events.
- Digest bullets can represent merged source events and are intentionally editorially compressed.

## Documentation

- Docs index: `docs/README.md`
- New digest technical deep dive: `docs/digest_pipeline.md`
- Existing digest architecture notes: `docs/03-architecture/digest_canonical_pipeline.md`

