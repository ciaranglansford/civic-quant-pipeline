### Story BE-06 – Implement Phase 2 message eligibility query

- **Story ID**: BE-06
- **Title**: Select eligible unprocessed raw messages for extraction
- **As a**: Backend engineer
- **I want**: A deterministic query that returns only Phase 2-eligible messages.
- **So that**: The scheduled processor can safely run every 10 minutes without reprocessing completed items.

#### Preconditions

- `raw_messages` rows are already inserted by Phase 1 ingest.
- A processing-state table exists for tracking completion/error status.

#### Acceptance Criteria

- A service function exists in `app/services` (for example `get_eligible_messages_for_extraction`) that:
  - Selects `raw_messages` not marked `completed` for ExtractionAgent processing.
  - Excludes rows currently `in_progress` unless lease timeout has elapsed.
  - Orders rows by `message_timestamp_utc`, then `id` for deterministic processing.
  - Supports a configurable batch size.
- The selection logic uses DB filters/joins only (no full-table in-memory filtering).
- Re-running the selector immediately after a successful run returns no previously completed rows.
- Unit tests cover:
  - First-time selection.
  - Retry selection after failed status.
  - Lease-expired reclaim behavior.

#### Out-of-scope

- Scheduling and job triggering.
