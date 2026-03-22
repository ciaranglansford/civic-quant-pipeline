# Configuration

Runtime settings are defined in `app/config.py` (`Settings`) plus listener-specific runtime variables in `listener/telegram_listener.py`.

## Core Settings (`app/config.py`)

| Env var | Default | Used by | Notes |
|---|---|---|---|
| `API_HOST` | `0.0.0.0` | API runtime | Host binding for FastAPI process. |
| `API_PORT` | `8000` | API runtime | Port setting for API process. |
| `DATABASE_URL` | `sqlite+pysqlite:///./civicquant_dev.db` | API + jobs | SQLAlchemy connection URL. |
| `TG_API_ID` | unset | Listener/backfill | Telegram MTProto credential. |
| `TG_API_HASH` | unset | Listener/backfill | Telegram MTProto credential. |
| `TG_SESSION_NAME` | unset | Listener/backfill | Telethon session file name. |
| `TG_SOURCE_CHANNEL` | unset | Listener/backfill | Source channel handle/id. |
| `INGEST_API_BASE_URL` | unset | Listener | Base URL for posting ingest payloads. |
| `VIP_DIGEST_HOURS` | `4` | Digest | Digest window size in hours. |
| `TG_BOT_TOKEN` | unset | Digest publish | Telegram bot token for digest delivery. |
| `TG_VIP_CHAT_ID` | unset | Digest publish | Target Telegram chat for digest delivery. |
| `DIGEST_LLM_ENABLED` | `false` | Digest synthesis | Enables LLM synthesis path when model/key are configured. |
| `DIGEST_OPENAI_MODEL` | unset | Digest synthesis | Overrides extraction model for digest synthesis. |
| `DIGEST_OPENAI_TIMEOUT_SECONDS` | `30.0` | Digest synthesis | HTTP timeout for digest model calls. |
| `DIGEST_OPENAI_MAX_RETRIES` | `2` | Digest synthesis | Retry count for digest model calls. |
| `DIGEST_TOP_DEVELOPMENTS_LIMIT` | `3` | Digest | Top developments cap. |
| `DIGEST_SECTION_BULLET_LIMIT` | `6` | Digest | Per-section bullet cap. |
| `PHASE2_EXTRACTION_ENABLED` | `false` | Phase2 | Must be true to run phase2 extraction job/trigger. |
| `PHASE2_BATCH_SIZE` | `50` | Phase2 | Eligible raw rows per run. |
| `PHASE2_LEASE_SECONDS` | `600` | Phase2 | Lease duration for in-progress rows. |
| `PHASE2_SCHEDULER_LOCK_SECONDS` | `540` | Phase2 + deep enrichment | Processing lock duration. |
| `PHASE2_ADMIN_TOKEN` | unset | Admin route auth | Required for `/admin/process/phase2-extractions` and structured query admin endpoints. |
| `PHASE2_FORCE_REPROCESS` | `false` | Phase2 | Forces model call path in jobs unless query override says otherwise. |
| `PHASE2_CONTENT_REUSE_ENABLED` | `true` | Phase2 | Enables cross-message canonical extraction reuse. |
| `PHASE2_CONTENT_REUSE_WINDOW_HOURS` | `6` | Phase2 | Time window for content reuse lookup. |
| `DEEP_ENRICHMENT_ENABLED` | `true` | Deep enrichment | Enables deep enrichment workflow. |
| `DEEP_ENRICHMENT_BATCH_SIZE` | `50` | Deep enrichment | Candidate rows per run. |
| `OPENAI_API_KEY` | unset | Extraction + digest (fallback model key) | Required for phase2 extraction. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Extraction (and digest fallback) | Extraction model name. |
| `OPENAI_TIMEOUT_SECONDS` | `30.0` | Extraction | HTTP timeout for extraction model calls. |
| `OPENAI_MAX_RETRIES` | `2` | Extraction | Retry count for extraction model calls. |

## Listener-Only Settings (`listener/telegram_listener.py`)

| Env var | Default | Purpose |
|---|---|---|
| `TG_POLL_INTERVAL_S` | `60` | Poll interval for listener fetch loop. |

## Script Safety Flags

| Env var | Used by | Purpose |
|---|---|---|
| `CONFIRM_CLEAR_NON_RAW` | `app/jobs/clear_all_but_raw_messages.py` | Required guard before clearing derived tables. |

`app/jobs/reset_dev_schema.py` is destructive and currently has no active runtime confirmation guard.

## Minimal Local `.env` for API + Phase2

```dotenv
DATABASE_URL=sqlite+pysqlite:///./civicquant_dev.db
PHASE2_EXTRACTION_ENABLED=true
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
PHASE2_ADMIN_TOKEN=change_me
```

Add listener, digest, and theme batch values as needed for your local workflow.
