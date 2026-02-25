## Observability and Audit

### Purpose

Define strict behavior for logging and auditability across the ingest, extraction, routing, dedup, and publishing stages.

### Story OBS-01 – Log Ingest Success and Failure

- **Story ID**: OBS-01
- **Title**: Log ingest attempts with structured fields
- **As a**: Operator
- **I want**: Logs for all ingest attempts and their outcomes.
- **So that**: I can debug missing or duplicate messages.

#### Preconditions

- Listener and backend ingest endpoint are implemented.

#### Acceptance Criteria

- For each request to `/ingest/telegram`, the backend logs:
  - `request_id` (generated or trace ID)
  - `source_channel_id`
  - `telegram_message_id`
  - `result` (`success` or `failure`)
  - HTTP status code (for failure).
- Logs are emitted in a consistent format across successes and failures.
- No ingest attempt occurs without a corresponding log entry.

#### Out-of-scope

- Centralized log storage (e.g., ELK, Loki).

### Story OBS-02 – Log Extraction Validation

- **Story ID**: OBS-02
- **Title**: Log extraction and validation outcomes
- **As a**: Operator
- **I want**: Logs indicating whether extraction succeeded and passed schema validation.
- **So that**: I can detect model or stub failures quickly.

#### Preconditions

- Extraction and schema validation are implemented.

#### Acceptance Criteria

- For each extraction attempt, the system logs:
  - `raw_message_id`
  - `model_name`
  - `result` (`success` or `failure`)
  - If failure: validation errors or exception message.
- Failed extractions do not crash the ingest endpoint; they return a controlled error or degraded behavior.

#### Out-of-scope

- Automatic retries for extraction failures.

### Story OBS-03 – Log Routing Decisions

- **Story ID**: OBS-03
- **Title**: Log routing decisions and rules fired
- **As a**: Operator
- **I want**: Logs that show how routing decisions were determined.
- **So that**: I can understand why a message was (or was not) prioritized for publishing.

#### Preconditions

- Routing configuration and logic are implemented.

#### Acceptance Criteria

- For each routing operation, the system logs:
  - `raw_message_id`
  - `event_fingerprint`
  - `publish_priority`
  - `event_action`
  - `store_to`
  - `flags`
  - Short identifiers for the rules that fired (e.g., `rule_macroecon_high_impact`).
- Logs are structured and parseable.

#### Out-of-scope

- A UI for browsing routing logs.

### Story OBS-04 – Log Dedup and Event Upserts

- **Story ID**: OBS-04
- **Title**: Log deduplication decisions
- **As a**: Operator
- **I want**: Logs that show which events were considered and chosen during dedup.
- **So that**: I can verify that duplicate messages are being merged correctly.

#### Preconditions

- Event upsert logic is implemented.

#### Acceptance Criteria

- For each event upsert:
  - The system logs:
    - `raw_message_id`
    - `candidate_event_ids` considered (possibly empty)
    - `selected_event_id` (if any)
    - `event_action` (`create` or `update`)
    - Brief reason (e.g., `fingerprint_match_within_window`).
- If no event is selected and a new one is created, the log clearly indicates that creation happened due to no suitable candidate.

#### Out-of-scope

- Persisting this metadata in a dedicated database table (logs only in Phase 1).

### Story OBS-05 – Log Published Digests

- **Story ID**: OBS-05
- **Title**: Log digest publishing with event references
- **As a**: Operator
- **I want**: Logs that show which events were included in each digest publish.
- **So that**: I can trace any digest notification back to the underlying events.

#### Preconditions

- Digest generation and publishing are implemented.

#### Acceptance Criteria

- For each digest publish attempt, the system logs:
  - `destination` (e.g., `vip_telegram`)
  - `published_at`
  - `event_ids` included in the digest
  - `content_hash`
  - `result` (`success` or `failure`)
- If publishing fails, the log includes the error details.

#### Out-of-scope

- Persisting per-digest event mappings in Phase 1 (Phase 2+ may add a join table).

