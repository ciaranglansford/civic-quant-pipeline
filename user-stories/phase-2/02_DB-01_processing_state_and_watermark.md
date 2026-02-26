### Story DB-01 – Add extraction processing state storage

- **Story ID**: DB-01
- **Title**: Create table for message processing state and run cursors
- **As a**: Backend engineer
- **I want**: Durable status and watermark records for Phase 2 extraction processing.
- **So that**: Scheduled runs can resume safely, retry failed items, and provide traceability.

#### Preconditions

- SQLAlchemy model pattern in `app/models.py` is the source for table definitions.

#### Acceptance Criteria

- A new table/model is added (for example `message_processing_states`) with at least:
  - `raw_message_id` (FK to `raw_messages`, unique)
  - `status` enum-like string: `pending|in_progress|completed|failed`
  - `attempt_count` integer
  - `last_attempted_at` timestamp nullable
  - `completed_at` timestamp nullable
  - `lease_expires_at` timestamp nullable
  - `last_error` text nullable
  - `processing_run_id` string nullable
- A unique key enforces one processing-state row per `raw_message_id`.
- Indexes exist to support eligibility query (`status`, `lease_expires_at`, `raw_message_id`).
- Schema initialization (`init_db`) creates the new table in local/dev environments.
- Tests verify state row creation and status transitions used by Phase 2 service.

#### Out-of-scope

- Evidence, routing, or publishing states.
