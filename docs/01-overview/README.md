# Civicquant Documentation (Code-Derived)

## Project Summary

This repository implements a market-intelligence ingestion pipeline centered on Telegram messages.

From the code, the current implemented capabilities are:
- A FastAPI service with:
  - `GET /health` for liveness.
  - `POST /ingest/telegram` for Telegram message ingest.
- A SQLAlchemy-backed persistence layer for raw messages, extracted structure, routing decisions, canonical events, event-to-message links, and published digest records.
- A rule-based extraction + routing pipeline (no external LLM call in current implementation).
- A Telethon-based listener process that consumes Telegram channel messages and forwards them to the ingest API.
- A digest job that groups recent events and publishes a digest to Telegram via bot API.

See [Architecture](./ARCHITECTURE.md), [Data Flow](../02-flows/DATA_FLOW.md), and [API](../03-interfaces/API.md).

## Quickstart

## quickstart-prerequisites
- Python 3.10+ (inferred from runtime artifacts under `__pycache__` and current typing syntax).
- A reachable SQLAlchemy database URL (`DATABASE_URL` is required at settings load).
- Optional: Telegram credentials for listener and digest publishing.

## quickstart-install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## quickstart-configure
Create a `.env` file or export environment variables.

Required for backend startup:
- `DATABASE_URL`

Optional for backend:
- `API_HOST` (default `0.0.0.0`)
- `API_PORT` (default `8000`)
- `VIP_DIGEST_HOURS` (default `4`)
- `TG_BOT_TOKEN` and `TG_VIP_CHAT_ID` (required only when publishing digest)

Required for Telegram listener process:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

## quickstart-run-backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The backend initializes logging and creates DB tables on app lifespan startup.

## quickstart-run-listener
```bash
python -m listener.telegram_listener
```

This process subscribes to one configured channel and forwards each new message to `POST /ingest/telegram`.

## quickstart-run-digest-job
```bash
python -m app.jobs.run_digest
```

This queries recent events, builds digest text, publishes to Telegram bot API, and stores the published digest hash/record.

## quickstart-test
```bash
pytest -q
```

## Key Commands

| Purpose | Command |
|---|---|
| Install dependencies | `pip install -r requirements.txt` |
| Run API server | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Run listener | `python -m listener.telegram_listener` |
| Run digest job | `python -m app.jobs.run_digest` |
| Run tests | `pytest -q` |

## Repository Map

| Path | Purpose |
|---|---|
| `app/` | FastAPI application, schemas, DB setup, SQLAlchemy models, routers, and services. |
| `app/routers/` | HTTP route handlers (`ingest.py`). |
| `app/services/` | Ingest pipeline, extraction/routing logic, event upsert, digest generation, Telegram publishing. |
| `app/jobs/` | CLI-style job entrypoints (`run_digest.py`). |
| `listener/` | Telegram MTProto listener that posts messages to backend. |
| `tests/` | End-to-end-ish API and digest behavior tests using `TestClient` and SQLite file DB. |
| `docs/` | Documentation generated from code inspection (this directory). |
| `requirements.txt` | Python dependencies. |

## Notes on Source of Truth

This documentation is derived from executable code paths and tests. Existing planning/user-story artifacts were intentionally not used as authoritative behavior definitions.
