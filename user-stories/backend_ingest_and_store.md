## Backend – Ingest Endpoint and Storage

### Purpose

Define strict behavior for the backend ingest endpoint and raw message storage, ensuring idempotent, immutable records in the database.

### Story BE-01 – Define Ingest Payload Schema

- **Story ID**: BE-01
- **Title**: Define `TelegramIngestPayload` schema
- **As a**: Backend engineer
- **I want**: A typed request model that exactly matches the listener payload.
- **So that**: The ingest endpoint can validate and document required fields consistently.

#### Preconditions

- Specification of ingest payload fields is available.

#### Acceptance Criteria

- A Pydantic model named `TelegramIngestPayload` exists in the backend codebase.
- The model contains the following fields with correct types:
  - `source_channel_id: string`
  - `source_channel_name: string | null`
  - `telegram_message_id: string`
  - `message_timestamp_utc: datetime (timezone-aware or treated as UTC)`
  - `raw_text: string`
  - `raw_entities_if_available: any | null`
  - `forwarded_from_if_available: string | null`
- The FastAPI route for `/ingest/telegram` uses this model as its request body type.
- Invalid requests (missing required fields or wrong types) return a 422 error with details.

#### Out-of-scope

- Any transformation of data for storage.

### Story BE-02 – Implement Ingest Endpoint

- **Story ID**: BE-02
- **Title**: Implement `/ingest/telegram` endpoint
- **As a**: Backend engineer
- **I want**: A FastAPI endpoint that accepts the ingest payload and passes it to the ingest pipeline.
- **So that**: Listener data is validated and processed via consistent application logic.

#### Preconditions

- `TelegramIngestPayload` model is defined.
- Database session utilities are available.

#### Acceptance Criteria

- A POST endpoint `/ingest/telegram` exists and:
  - Accepts a `TelegramIngestPayload` body.
  - Returns a JSON response with at least `status` and `raw_message_id` or an error code.
- The endpoint:
  - Normalizes the text using a dedicated normalization function.
  - Attempts to insert the raw message into the database.
  - Triggers extraction, routing, and event upsert logic synchronously or via a clearly defined internal call.
- Idempotent duplicate requests (same `source_channel_id` and `telegram_message_id`) do not create duplicate rows and return a deterministic response.

#### Out-of-scope

- Asynchronous task queues or background workers.

### Story BE-03 – Normalize Message Text

- **Story ID**: BE-03
- **Title**: Normalize message text deterministically
- **As a**: Backend engineer
- **I want**: Message text normalization that removes noise but preserves numbers and key tokens.
- **So that**: Deduplication and extraction work on stable input across repeats/near-duplicates.

#### Preconditions

- Raw message text is available from the ingest payload.

#### Acceptance Criteria

- A single normalization function is implemented and used everywhere normalized text is needed.
- Normalization performs at least:
  - Trimming leading/trailing whitespace.
  - Converting multiple spaces/newlines to a single space where safe.
  - Preserving numeric values and their units (e.g., `25bp`, `2.5%`).
- Normalization is deterministic: the same input string always produces the same normalized string.
- Normalized text is stored alongside raw text in the `raw_messages` table.

#### Out-of-scope

- Language detection or translation.

### Story BE-04 – Persist Immutable Raw Messages

- **Story ID**: BE-04
- **Title**: Store raw messages as immutable records
- **As a**: Data consumer
- **I want**: Every ingested Telegram message stored exactly once and never edited.
- **So that**: I can reconstruct the exact original message history.

#### Preconditions

- Database connection and migrations are in place.

#### Acceptance Criteria

- A `raw_messages` table exists with columns for all ingest payload fields and `normalized_text`.
- Rows in `raw_messages` are only ever inserted or deleted; they are not updated in normal operation.
- Application code does not execute `UPDATE` statements on `raw_messages` except for migrations or emergency maintenance.
- The ingest pipeline creates exactly one row per unique `(source_channel_id, telegram_message_id)`.

#### Out-of-scope

- Soft delete mechanisms or archival.

### Story BE-05 – Enforce Idempotency at DB Layer

- **Story ID**: BE-05
- **Title**: Enforce uniqueness by `(source_channel_id, telegram_message_id)`
- **As a**: Backend engineer
- **I want**: The database to enforce idempotency for raw messages.
- **So that**: Duplicate ingest requests cannot create duplicate records.

#### Preconditions

- `raw_messages` table is defined.

#### Acceptance Criteria

- A unique constraint or unique index is defined on `(source_channel_id, telegram_message_id)` in `raw_messages`.
- On constraint violation:
  - The application catches the error.
  - The ingest endpoint returns a success or explicit “duplicate” response without crashing.
- Under concurrent requests with the same IDs, only one row is inserted.

#### Out-of-scope

- Handling duplicates across different channels.

