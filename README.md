# Civicquant Intelligence Pipeline – Phase 1 MVP

This repository contains the Phase 1 MVP implementation of the **Civicquant Intelligence Pipeline**:

- **Source**: High-frequency Telegram market feed (via MTProto user client).
- **Backend**: FastAPI app for ingest, storage, routing, and basic dedup.
- **Storage**: Postgres (single DB, multiple tables).
- **Outputs**: Structured archive + digest generation endpoint/script.

The implementation follows the JSON specification you provided (topics, routing logic, dedup strategy, non-functional requirements, and roadmap).

## Components

- **FastAPI app (`app/`)**
  - `POST /ingest/telegram` – ingest raw Telegram messages from the listener.
  - Normalization + stubbed LLM extraction service.
  - Basic routing and dedup/event upsert.
  - DB models for `raw_messages`, `extractions`, `events`, `event_messages`, `routing_decisions`, and `published_posts`.
  - Digest generation service (4-hour window by default) with an HTTP endpoint and script entrypoint.

- **Telegram listener (`listener/`)**
  - MTProto user client using **Telethon**.
  - Subscribes to a configured source channel and forwards messages to `POST /ingest/telegram`.

## Quickstart

1. **Create and activate a virtual environment** (recommended).
2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Set environment variables** (or create a `.env` file in the project root):

- **Backend / DB**
  - `DATABASE_URL` – e.g. `postgresql+psycopg2://user:password@localhost:5432/civicquant`
  - `API_HOST` – FastAPI bind host (default `0.0.0.0`)
  - `API_PORT` – FastAPI port (default `8000`)
  - `VIP_DIGEST_HOURS` – window for digest queries (default `4`)

- **Telegram listener**
  - `TG_API_ID` – Telegram API ID (from https://my.telegram.org)
  - `TG_API_HASH` – Telegram API hash
  - `TG_SESSION_NAME` – local session file name (e.g. `civicquant`)
  - `TG_SOURCE_CHANNEL` – source channel username or ID to listen to
  - `INGEST_API_BASE_URL` – base URL of the backend, e.g. `http://localhost:8000`

- **Telegram publishing (digests)**
  - `TG_BOT_TOKEN` – Telegram bot token for publishing digests.
  - `TG_VIP_CHAT_ID` – Chat ID of the VIP group/channel to receive digests.

4. **Run the backend**:

```bash
uvicorn app.main:app --reload
```

This will automatically create tables in the configured Postgres database on startup.

5. **Run the Telegram listener**:

```bash
python -m listener.telegram_listener
```

On first run, Telethon will guide you through authenticating the user account. After that, the listener will watch the configured source channel and call the backend ingest endpoint.

6. **Run a digest manually** (for cron or ad-hoc):

```bash
python -m app.jobs.run_digest
```

This will:

- Query events from the last `VIP_DIGEST_HOURS` hours.
- Generate a text digest grouped by topic.
- Post the digest to the `TG_VIP_CHAT_ID` using `TG_BOT_TOKEN`.

## Next Steps

- Swap the stub extraction service for a real LLM API using the provided extraction schema.
- Implement evidence/corroboration service and reliability scores.
- Extend routing logic with a versioned config file and more destinations.
- Add embeddings + pgvector for stronger dedup and semantic search.

