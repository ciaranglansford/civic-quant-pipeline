# Civicquant Intelligence Pipeline

Civicquant is a Telegram wire-bulletin ingestion and intelligence pipeline.

The system is designed for headline/ticker-style bulletins that are:
- short and urgent,
- source-attributed,
- repetitive and incremental,
- sometimes contradictory,
- often reported claims before confirmation.

This is not a public chat parser. It is a staged pipeline for capturing bulletin observations, structuring them, clustering them into events, and producing scheduled reporting from structured data.

## Pipeline Overview

The refined target-state flow is:

1. Raw ingest
2. Structural normalization
3. AI extraction of literal reported claim
4. Deterministic post-processing / triage
5. Event clustering
6. Entity indexing / dataset construction
7. Deferred enrichment / external validation
8. Scheduled reporting

## Truth Model

- Bulletins are treated as reported claims unless validated later.
- Extraction must preserve attribution and uncertainty language.
- `confidence` means confidence in extraction/classification quality, not factual truth.
- `impact_score` means significance of the reported claim if taken at face value, not confirmation.

## Current Implementation (What Exists Today)

- FastAPI backend with:
  - `GET /health`
  - `POST /ingest/telegram`
  - `POST /admin/process/phase2-extractions` (token-gated)
- Poll-based Telegram listener (`python -m listener.telegram_listener`) that forwards messages to ingest API.
- Idempotent raw capture into `raw_messages`.
- Deterministic normalization before extraction.
- Scheduled/manual phase2 extraction (`python -m app.jobs.run_phase2_extraction`) using OpenAI Responses API with strict schema validation and prompt template `extraction_agent_v2`.
- Extraction persistence stores raw validated payload (`payload_json`) and deterministic canonicalized payload (`canonical_payload_json`).
- Deterministic routing + triage + event upsert (`events`, `event_messages`, `routing_decisions`) with entity indexing (`entity_mentions`).
- Stage 1 deterministic calibration is active in triage/routing:
  - score bands are used for routing decisions (raw scores remain unchanged),
  - repetitive low-delta bursts are downgraded,
  - local domestic incident patterns are capped to monitor-or-lower and forced evidence-required,
  - high-risk unattributed summaries are safety-rewritten only in canonical payloads.
- Digest job (`python -m app.jobs.run_digest`) publishing event-based summaries.

## Component Map

- `app/routers/`: HTTP interfaces (`ingest`, `admin`).
- `app/services/`: normalization, extraction processing, routing, event management, digest logic.
- `app/models.py`: storage contract for raw messages, processing state, extractions, events, routing decisions, published posts.
- `app/jobs/`: operational jobs (phase2 extraction, digest, reset/test helpers).
- `listener/`: Telegram ingestion worker.
- `docs/`: architecture, flow, interfaces, operations, audit references.

## Quickstart

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure `.env` (or environment variables):

- Backend:
  - `DATABASE_URL`
  - `API_HOST` (optional)
  - `API_PORT` (optional)
  - `VIP_DIGEST_HOURS` (optional)
- Listener:
  - `TG_API_ID`
  - `TG_API_HASH`
  - `TG_SESSION_NAME`
  - `TG_SOURCE_CHANNEL`
  - `INGEST_API_BASE_URL`
- Digest publishing:
  - `TG_BOT_TOKEN`
  - `TG_VIP_CHAT_ID`
- Phase2 extraction:
  - `PHASE2_EXTRACTION_ENABLED=true`
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`
  - `OPENAI_TIMEOUT_SECONDS`
  - `OPENAI_MAX_RETRIES`
  - `PHASE2_BATCH_SIZE`
  - `PHASE2_LEASE_SECONDS`
  - `PHASE2_ADMIN_TOKEN` (for admin trigger endpoint)

## Local Execution Paths

### Path A: Minimal backend-only loop

Use this when validating ingest API + schema + DB setup.

1. Start backend:
```bash
uvicorn app.main:app --reload
```
2. Run tests:
```bash
pytest -q
```

### Path B: Full local pipeline loop

Use this when validating capture -> extraction -> clustering -> reporting.

1. Start backend:
```bash
uvicorn app.main:app --reload
```
2. Start listener (optional if manually posting ingest payloads):
```bash
python -m listener.telegram_listener
```
3. Run phase2 extraction batch:
```bash
python -m app.jobs.run_phase2_extraction
```
4. Run digest/report job:
```bash
python -m app.jobs.run_digest
```

## Command-by-Stage Matrix

| Pipeline stage | Command | Primary purpose | Key output |
|---|---|---|---|
| Setup | `pip install -r requirements.txt` | Install dependencies | Runnable env |
| Stage 1-2 (capture/normalize) | `uvicorn app.main:app --reload` + `python -m listener.telegram_listener` | Ingest and normalize bulletins | `raw_messages`, `message_processing_states` |
| Stage 3-5 (extract/triage/cluster) | `python -m app.jobs.run_phase2_extraction` | Structured claim extraction + routing + event updates | `extractions`, `routing_decisions`, `events`, `event_messages` |
| Stage 3 probe | `python -m app.jobs.test_openai_extract` | Prompt/extractor smoke test | Console output + validation proof |
| Stage 8 (reporting) | `python -m app.jobs.run_digest` | Generate event-level digest | `published_posts` |
| Verification | `pytest -q` | Full test suite | Pass/fail summary |
| Verification (targeted) | `pytest -q tests/test_extraction_llm_client.py` | Extraction client tests | Pass/fail summary |
| Verification (targeted) | `pytest -q tests/test_e2e_backend.py` | End-to-end pipeline checks | Pass/fail summary |

## Reprocessing Guidance

- Preserve raw ingest data and re-run derived processing:
```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```
Use this when iterating extraction/routing/event logic while keeping source bulletin history.

- Full destructive dev reset:
```bash
CONFIRM_RESET_DEV_SCHEMA=true python -m app.jobs.reset_dev_schema
```
Use this when schema/layout drift makes partial reprocessing insufficient.

## Runtime Inputs and Outputs (Quick Reference)

| Runtime | Pipeline position | Consumes | Produces |
|---|---|---|---|
| Listener | Stage 1 ingress source | Telegram source feed | HTTP ingest payloads |
| Backend ingest route | Stage 1-2 | Listener payload | Immutable raw rows + normalized text |
| Phase2 extraction job | Stage 3-5 | Eligible raw messages | Structured claim rows + triage + events |
| Digest job | Stage 8 | Event-level structured data | Published report records |

## Docs Entry Points

- Overview: `docs/01-overview/README.md`
- Architecture: `docs/01-overview/ARCHITECTURE.md`
- Flows: `docs/02-flows/DATA_FLOW.md`
- Interfaces/storage: `docs/03-interfaces/schemas_and_storage_model.md`
- Operations: `docs/04-operations/operations_and_scheduling.md`
- Audit: `docs/05-audit/spec_vs_impl_audit.md`

## Notes

This repository contains both implemented behavior and forward-looking architecture intent in docs. Each major doc distinguishes current state vs target state vs future optional enhancements.
