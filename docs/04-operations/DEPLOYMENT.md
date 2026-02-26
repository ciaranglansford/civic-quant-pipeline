# Deployment and Runtime Operations

## deployment-overview

No container files or CI/CD workflow definitions are present in this repository. Deployment details below are inferred from runtime entrypoints and settings in code.

## environments

## local-development
Typical local setup inferred from code:
1. Install Python dependencies from `requirements.txt`.
2. Set `DATABASE_URL`.
3. Start API server (`uvicorn app.main:app`).
4. Optionally run listener and digest job as separate processes.

## production-like
Likely production topology:
- **Process 1**: ASGI server hosting FastAPI app.
- **Process 2**: Telegram listener worker.
- **Process 3**: Scheduled digest runner (cron or scheduler).
- **Shared DB**: SQL database configured via `DATABASE_URL`.

Uncertainty: no infra-as-code or process manager config is checked in, so exact orchestration method is not specified.

## runtime-requirements

## software
- Python with packages in `requirements.txt`:
  - FastAPI/Uvicorn
  - SQLAlchemy + psycopg2-binary
  - Pydantic + pydantic-settings
  - httpx
  - Telethon

## services
- SQL database reachable through `DATABASE_URL`.
- Telegram access:
  - MTProto credentials for listener process.
  - Bot token/chat ID for digest publication.

## configuration-and-secrets

### backend-required
- `DATABASE_URL`

### backend-optional
- `API_HOST`
- `API_PORT`
- `VIP_DIGEST_HOURS`
- `TG_BOT_TOKEN`
- `TG_VIP_CHAT_ID`

### listener-required
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_NAME`
- `TG_SOURCE_CHANNEL`
- `INGEST_API_BASE_URL`

### secret-handling-note
- All sensitive keys are expected from env vars or `.env` file loading via Pydantic settings.
- No secret vault integration is implemented in code.

## database-lifecycle

On API startup (`lifespan`), `init_db()` runs `Base.metadata.create_all(bind=engine)`.

Operational implication:
- Tables auto-create if absent.
- No explicit migration/versioning mechanism is present.

## scheduling

Digest publication is not automatic inside API runtime; it is implemented as a separate job entrypoint (`app.jobs.run_digest`).

Expected deployment action:
- Configure scheduler (cron/systemd timer/job runner) to execute at desired interval.

## health-and-observability

- Liveness endpoint: `GET /health`.
- Logging is configured with `logging.basicConfig(level=INFO)` in backend lifecycle and listener module.
- No built-in metrics or distributed tracing instrumentation.

## Phase 2 Extraction Runtime Configuration

The scheduled extraction processor uses separate environment-driven settings:

- `PHASE2_EXTRACTION_ENABLED` (bool)
- `PHASE2_BATCH_SIZE` (int)
- `OPENAI_API_KEY` (secret)
- `OPENAI_MODEL` (string)
- `OPENAI_TIMEOUT_SECONDS` (int/float)
- `OPENAI_MAX_RETRIES` (int)

Deployment notes:
- Keep secrets externalized (environment or secret manager).
- Backend API process may run without OpenAI config when Phase 2 processor is disabled.
- Scheduler process should fail fast with clear error if enabled but required OpenAI settings are missing.
