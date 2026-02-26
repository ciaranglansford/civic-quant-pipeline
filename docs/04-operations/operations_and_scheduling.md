## Operations and Scheduling

### Purpose

Describe how to operate the Civicquant pipeline and how periodic jobs (especially digests) are scheduled in Phase 1 MVP.

### Runtime Components

- **Backend API**
  - Process: `uvicorn app.main:app --reload` (or similar).
  - Role: Handle ingest, processing, and data storage.

- **Telegram Listener**
  - Process: `python -m listener.telegram_listener`.
  - Role: Listen to source channel and send messages to backend.

- **Digest Job**
  - Process: `python -m app.jobs.run_digest` (or equivalent entrypoint).
  - Role: Generate and publish 4-hour digests to VIP chat.

### Environment Configuration

- **Backend / DB**
  - `DATABASE_URL` – Postgres connection string.
  - `API_HOST` – API bind host (default `0.0.0.0`).
  - `API_PORT` – API port (default `8000`).
  - `VIP_DIGEST_HOURS` – Digest time window in hours (default `4`).

- **Telegram Listener**
  - `TG_API_ID`
  - `TG_API_HASH`
  - `TG_SESSION_NAME`
  - `TG_SOURCE_CHANNEL`
  - `INGEST_API_BASE_URL`

- **Telegram Publishing**
  - `TG_BOT_TOKEN`
  - `TG_VIP_CHAT_ID`

### Scheduling – Digests

- **Cadence**
  - Default: every `4` hours, configured by `VIP_DIGEST_HOURS`.
  - Future: additional cadences for breaking queues (15m/1h/4h).

- **Mechanism (Phase 1)**
  - Use OS-level cron or a simple scheduler to run the digest script:
    - Example cron expression for every 4 hours:
      - `0 */4 * * *  python -m app.jobs.run_digest`

- **Digest Job Flow**
  - Read `VIP_DIGEST_HOURS` from configuration.
  - Query events in the last `VIP_DIGEST_HOURS`.
  - Build digest text grouped by topic.
  - Send digest via Telegram Bot API to `TG_VIP_CHAT_ID`.
  - Insert `published_posts` record with content hash and timestamp.

### Future Scheduling – Breaking Queues (Phase 2+)

- **Concept**
  - Maintain additional queues for:
    - `breaking_15m`
    - `breaking_1h`
    - `breaking_4h`
  - Use `is_breaking` and `breaking_window` from extraction.

- **Expected Behavior**
  - Jobs run at higher frequency (e.g., every 15 minutes) for breaking items.
  - Thresholds for which events appear in breaking digests are controlled by routing configuration.

### Operational Runbooks (Phase 1)

- **Start Backend**
  - Ensure `DATABASE_URL` is set and database is reachable.
  - Run API process.
  - Confirm health via `/health` endpoint (to be implemented) or simple status check.

- **Start Listener**
  - Ensure Telegram credentials and ingest base URL are set.
  - Run listener process.
  - Verify that new messages from the source channel result in rows in `raw_messages`.

- **Run Digest Manually**
  - Ensure API and database are running and events exist.
  - Run digest script.
  - Verify message appears in VIP Telegram chat and `published_posts`.

### Monitoring and Alerts (Manual Phase 1)

- **What to monitor**
  - API errors or high 5xx rate.
  - Listener connection errors to Telegram.
  - Digest job failures.
  - Database connectivity and disk usage.

- **How**
  - Initially via log inspection and simple OS tools.
  - Future integration with monitoring stack (Prometheus, Grafana, etc.).


## Scheduling – Phase 2 Extraction Processing

### Cadence

- Run every 10 minutes.
- Example cron:
  - `*/10 * * * * python -m app.jobs.run_phase2_extraction`

### Job Behavior

- Acquire a single-run lock (DB advisory lock or lock-row equivalent).
- Select eligible rows from `raw_messages` using processing-state status/lease criteria.
- Process in bounded batches with configured size.
- Persist per-message status (`completed`/`failed`) and run summary counts.

### Optional Manual Trigger (Internal)

- Optional endpoint: `POST /admin/process/phase2-extractions`.
- Must call the same processing service as scheduled job.
- Should be admin/internal-only and disabled by default unless auth guard is configured.

### Failure Handling and Visibility

- Required structured fields in logs: `processing_run_id`, `raw_message_id`, `status`, `attempt_count`, `prompt_version`.
- Distinguish error classes: `provider_error`, `validation_error`, `persistence_error`.
- Overlapping scheduler attempts should log and exit without duplicate processing.
