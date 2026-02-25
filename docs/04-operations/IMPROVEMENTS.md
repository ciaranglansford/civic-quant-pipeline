# Engineering Improvements Backlog

Actionable backlog focused on readability, maintainability, correctness, and DX. Priorities are relative to current code risk.

---

## 1) Add schema migration tooling
- **Type:** maintainability
- **Priority:** P1
- **Evidence:** DB schema is created via `Base.metadata.create_all` at runtime startup (`app/db.py`, `app/main.py`) with no migration history.
- **Proposed change:** Introduce Alembic migration scripts and replace implicit runtime schema creation with controlled migrations for non-test environments.
- **Acceptance criteria:**
  - Alembic config committed.
  - Initial revision reflects current schema.
  - App startup in production mode does not auto-create tables.
- **Risk/impact notes:** Medium implementation effort; prevents schema drift and improves deployment safety.

## 2) Add explicit authn/authz for ingest endpoint
- **Type:** security
- **Priority:** P0
- **Evidence:** `POST /ingest/telegram` has no authentication or signature verification (`app/routers/ingest.py`).
- **Proposed change:** Add API key or signed HMAC verification for listener-originated requests; reject unauthorized requests with 401/403.
- **Acceptance criteria:**
  - Unauthorized requests fail.
  - Authorized listener requests succeed.
  - Tests cover both paths.
- **Risk/impact notes:** High security value; requires coordinated secret distribution.

## 3) Centralize transactional error taxonomy
- **Type:** correctness
- **Priority:** P1
- **Evidence:** Router catches broad `Exception` and returns generic 500, which obscures error classes (`app/routers/ingest.py`).
- **Proposed change:** Introduce typed domain exceptions (validation/domain/conflict/external failure) and map to explicit HTTP status codes and structured error responses.
- **Acceptance criteria:**
  - Exception classes documented and used in services.
  - Router maps them deterministically.
  - Tests assert status codes and error payload shape.
- **Risk/impact notes:** Low runtime risk; improves operability/debugging.

## 4) Strengthen type boundaries and interfaces between services
- **Type:** readability
- **Priority:** P1
- **Evidence:** Some service functions return loosely typed `dict[str, object]` (`process_ingest_payload` in `app/services/ingest_pipeline.py`).
- **Proposed change:** Replace dict returns with typed Pydantic/dataclass result objects.
- **Acceptance criteria:**
  - No `dict[str, object]` for core pipeline outputs.
  - Mypy/pyright-friendly annotations across router/service boundary.
- **Risk/impact notes:** Low risk; improves maintainability and refactor safety.

## 5) Introduce structured logging context helpers
- **Type:** DX
- **Priority:** P2
- **Evidence:** Logging is mostly formatted strings with repeated fields and no shared context helper (`app/logging_utils.py`, router/listener/services).
- **Proposed change:** Add a small structured logging wrapper (JSON formatter or adapter) and standard fields (`request_id`, `source_channel_id`, `raw_message_id`, `event_id`).
- **Acceptance criteria:**
  - Log entries are machine-parseable with stable keys.
  - Request/event identifiers consistently present in ingest path logs.
- **Risk/impact notes:** Low risk; improves observability and incident response.

## 6) Move routing configuration to external versioned config
- **Type:** maintainability
- **Priority:** P2
- **Evidence:** Routing thresholds/destinations are hardcoded in `app/config_routing.py`.
- **Proposed change:** Load routing config from versioned YAML/JSON with schema validation and optional runtime reload.
- **Acceptance criteria:**
  - Config file with version field and validation.
  - Unit tests for config parsing and fallback behavior.
- **Risk/impact notes:** Medium change surface; better operational control without code deploy.

## 7) Expand extraction determinism tests
- **Type:** testing
- **Priority:** P1
- **Evidence:** Existing tests are e2e-style and do not directly assert extraction fingerprint/topic heuristics (`tests/test_e2e_backend.py`, `app/services/extraction_agent.py`).
- **Proposed change:** Add unit tests for extraction edge cases (empty text, ticker/number parsing, topic hints, fingerprint stability).
- **Acceptance criteria:**
  - Dedicated extraction test module with representative fixtures.
  - Stable expected outputs for deterministic inputs.
- **Risk/impact notes:** Low risk; guards against accidental behavior regressions.

## 8) Add retry + timeout policy abstraction for outbound HTTP
- **Type:** maintainability
- **Priority:** P2
- **Evidence:** Retry logic exists in listener (`post_with_retries`) but not shared with digest publisher; policies differ by module.
- **Proposed change:** Create shared outbound HTTP utility with configurable retry classes and timeouts; adopt for listener and publisher.
- **Acceptance criteria:**
  - Common utility module used by both call sites.
  - Configurable retryable status codes and backoff policy.
- **Risk/impact notes:** Medium refactor scope; improves consistency.

## 9) Add DB indexes aligned with hot queries
- **Type:** performance
- **Priority:** P2
- **Evidence:** Some lookups depend on non-indexed columns in filters (for example digest duplicate checks and event link scans).
- **Proposed change:** Verify query plans and add indexes where needed (for example `event_messages.raw_message_id`, `published_posts(destination, content_hash, published_at)`).
- **Acceptance criteria:**
  - Migration includes new indexes.
  - Query plan/benchmark shows reduced scan cost on representative dataset.
- **Risk/impact notes:** Low-to-medium risk depending on DB size.

## 10) Define module-level naming and size conventions
- **Type:** readability
- **Priority:** P2
- **Evidence:** Module naming is generally clear, but there is no explicit convention doc or lint enforcement for function complexity and naming consistency.
- **Proposed change:** Add lightweight engineering conventions (function length, naming, dependency direction) and enforce with linters where practical.
- **Acceptance criteria:**
  - Conventions documented in repo.
  - Lint checks for agreed rules in CI/local tooling.
- **Risk/impact notes:** Process change more than code risk; improves long-term clarity.
