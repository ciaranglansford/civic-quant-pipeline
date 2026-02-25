# Inferred Engineering Decisions (from Code)

## decision-1-fastapi-for-thin-http-layer
**What:** FastAPI is used as a thin ingress/API layer.

**Evidence:** `app.main` creates app and includes router; core business logic lives in service modules.

**Why (inferred):** Keep request parsing/validation and HTTP concerns separate from pipeline logic.

## decision-2-service-module-separation
**What:** Pipeline logic is split into focused modules: normalization, extraction, routing, event upsert, digest query/build/publish.

**Evidence:** Separate files under `app/services/` with clear single-purpose function sets.

**Why (inferred):** Improves testability and allows replacing components (for example extraction implementation) without changing router layer.

## decision-3-schema-first-validation-via-pydantic
**What:** Request/response and extracted structures are strongly typed with Pydantic models and constrained literals.

**Evidence:** `app/schemas.py` defines `TelegramIngestPayload`, `ExtractionJson`, `RoutingDecisionData`, `IngestResponse`, etc.

**Why (inferred):** Enforces stable API contracts and catches malformed payloads early.

## decision-4-idempotent-ingest-based-on-source-message-identity
**What:** Duplicate ingest requests are detected using source channel ID + telegram message ID.

**Evidence:** Unique DB constraint on `raw_messages`; pre-check and `IntegrityError` fallback in ingest pipeline.

**Why (inferred):** Listener retries and network duplication should not create duplicate business records.

## decision-5-db-centric-state-management
**What:** Pipeline state is persisted in normalized relational tables rather than in-memory/event-stream state.

**Evidence:** SQLAlchemy model set and transaction-driven commit/rollback pattern.

**Why (inferred):** Supports auditability and deterministic digest generation from persisted events.

## decision-6-content-hash-dedup-for-digest-publication
**What:** Digest publishing uses SHA-256 content hash + lookback window to avoid duplicate outbound messages.

**Evidence:** `digest_runner._content_hash` and `has_recent_duplicate` before publish.

**Why (inferred):** Prevent repetitive publishing in recurring schedule windows.

## decision-7-log-based-observability
**What:** Operational visibility is implemented with structured-ish logging statements.

**Evidence:** Named loggers and event-specific log lines in ingest, event manager, listener, digest modules.

**Why (inferred):** Minimal operational footprint for MVP without metrics/tracing stack.
