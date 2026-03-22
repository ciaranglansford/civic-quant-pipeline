# Deployment and Runtime Operations

> Legacy sectioned deployment note retained for context. Prefer `docs/architecture.md`, `docs/configuration.md`, and `docs/operations.md`.

## Deployment Overview

The system runs as multiple processes sharing one SQL database.

Typical topology:
- API process (`uvicorn app.main:app`)
- Listener process (`python -m listener.telegram_listener`)
- Phase2 extraction job (scheduled or manual)
- Digest/reporting job (scheduled or manual)

## Process-to-Stage Mapping

| Process/Job | Pipeline stages | Purpose |
|---|---|---|
| Listener | Stage 1 ingress source | Capture bulletins from Telegram feed and forward to API |
| API ingest + normalization | Stage 1-2 | Validate payloads, write immutable raw records, normalize text |
| Phase2 extraction job | Stage 3-5 | Extract literal reported claim, triage deterministically, cluster events |
| Digest job | Stage 8 | Build/publish event-level reports |
| Enrichment workflow (future) | Stage 7 | Selective external validation/corroboration |

Ownership note:
- Phase2 orchestration lives in `app/workflows/phase2_pipeline.py`.
- Business logic is context-owned in `app/contexts/*`.
- Digest/reporting remains canonical in `app/digest/*`.

## Scheduling Responsibility Split

### Extraction cadence
- Higher-frequency operational loop.
- Recommended schedule: every 10 minutes.
- Keeps event clusters fresh and ready for reporting.

### Reporting cadence
- Lower-frequency summary loop.
- Recommended schedule: every 4 hours (or configured window).
- Publishes event-level aggregates.

## Failure-Domain Notes

- Capture can continue if extraction is paused/failing; raw ingest remains source-of-record.
- Extraction delays reduce event freshness but do not erase raw bulletin history.
- Reporting quality depends on freshness/completeness of extraction + event clustering stages.
- Full pipeline recovery is possible via reprocessing derived tables while preserving raw records.

## Runtime Requirements

### Required baseline
- `DATABASE_URL`
- Python dependencies from `requirements.txt`

### Listener-specific
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

### Phase2 extraction
- `PHASE2_EXTRACTION_ENABLED=true`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`

### Reporting
- `TG_BOT_TOKEN`
- `TG_VIP_CHAT_ID`

## Health and Observability

- Liveness endpoint: `GET /health`
- Logs are primary observability source.
- Track logs by stage: capture, extraction, triage, clustering, reporting.

## Caveat

No standardized infrastructure-as-code or migration framework is fully established in this repository yet. Operational control currently relies on documented jobs and scripts.

