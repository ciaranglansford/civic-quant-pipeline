## Deduplication and Events

### Purpose

Define strict behavior for matching messages to canonical events and updating event records over time.

### Story EVT-01 – Define Event Model

- **Story ID**: EVT-01
- **Title**: Define canonical event model
- **As a**: Backend engineer
- **I want**: A structured `events` table representing canonical events.
- **So that**: Multiple related messages can be merged into a single evolving record.

#### Preconditions

- Extraction outputs include `event_fingerprint`, `topic`, `summary_1_sentence`, `impact_score`, `is_breaking`, `breaking_window`, `event_time`.

#### Acceptance Criteria

- An `events` table exists with at least:
  - `id` (primary key)
  - `event_fingerprint` (string, indexed)
  - `topic` (string)
  - `summary_1_sentence` (text)
  - `impact_score` (numeric)
  - `is_breaking` (boolean)
  - `breaking_window` (string)
  - `event_time` (timestamp)
  - `last_updated_at` (timestamp)
- The table may also store a reference to the latest extraction used to populate its fields.
- `event_fingerprint` is required and non-empty for all rows.

#### Out-of-scope

- Vector embeddings or semantic similarity fields.

### Story EVT-02 – Compute Time Windows

- **Story ID**: EVT-02
- **Title**: Implement event time window computation
- **As a**: Backend engineer
- **I want**: A function that determines the relevant time window for deduplication based on topic and breaking status.
- **So that**: Event matching rules are consistent and configurable.

#### Preconditions

- Extraction JSON and topic are available.

#### Acceptance Criteria

- A function exists, for example:
  - `get_event_time_window(topic, is_breaking) -> timedelta`.
- Defaults follow the specification:
  - `default_hours = 24`
  - `breaking_hours = 6`
  - `macro_econ_hours = 48`
- The function is pure and deterministic: same inputs produce same outputs.
- Unit tests verify the correct window is selected for:
  - Macro economic events.
  - Breaking vs. non-breaking events.
  - Other topics.

#### Out-of-scope

- Dynamic, per-source time windows.

### Story EVT-03 – Match and Upsert Events

- **Story ID**: EVT-03
- **Title**: Match messages to existing events or create new events
- **As a**: Event manager agent
- **I want**: Deterministic create/update/ignore decisions when processing new messages.
- **So that**: Duplicate or near-duplicate events are merged correctly.

#### Preconditions

- `event_fingerprint` and `event_time` are available from extraction.
- Event time window computation is implemented.

#### Acceptance Criteria

- A function or method exists, for example:
  - `upsert_event(extraction_json, raw_message_id) -> {event_id, event_action}`.
- Behavior:
  - Query for existing events with the same `event_fingerprint` whose `event_time` is within the computed time window.
  - If such an event exists:
    - `event_action = "update"`.
    - Update event fields as described in EVT-05.
  - If no such event exists:
    - Create a new `events` row using fields from extraction.
    - `event_action = "create"`.
- The function never creates multiple events for the same fingerprint within the time window.

#### Out-of-scope

- Embedding-based similarity comparisons (Phase 2+).

### Story EVT-04 – Link Messages to Events

- **Story ID**: EVT-04
- **Title**: Link raw messages to events
- **As a**: Data consumer
- **I want**: A join table between `raw_messages` and `events`.
- **So that**: I can see all underlying messages for any event.

#### Preconditions

- `events` and `raw_messages` tables exist.

#### Acceptance Criteria

- An `event_messages` table exists with at least:
  - `id` (primary key)
  - `event_id` (foreign key to `events`)
  - `raw_message_id` (foreign key to `raw_messages`)
  - `linked_at` (timestamp)
- Each time an event is created or updated for a raw message:
  - A corresponding row is inserted into `event_messages`.
- Duplicate links for the same `(event_id, raw_message_id)` are not created.

#### Out-of-scope

- Storing per-link metadata beyond timestamps.

### Story EVT-05 – Update Event Fields on New Information

- **Story ID**: EVT-05
- **Title**: Update event record when new information arrives
- **As a**: Event manager agent
- **I want**: Event records to reflect the latest and most complete state of the event.
- **So that**: Consumers see the best available summary and impact score.

#### Preconditions

- An existing event has been matched for an incoming message.

#### Acceptance Criteria

- When updating an event, the system:
  - Updates `summary_1_sentence` if the new summary is more informative or higher-confidence.
  - Updates `impact_score` if the new score is higher.
  - Updates `topic`, `is_breaking`, `breaking_window`, and `event_time` only if the new extraction provides more precise or non-null values.
  - Updates `last_updated_at` to the current time.
- The update policy is implemented as a pure function described in code or documentation (e.g., “prefer non-null, higher impact, more specific topic”).

#### Out-of-scope

- Manual curation or human overrides of event records.

### Story EVT-06 – Log Event Update Actions

- **Story ID**: EVT-06
- **Title**: Log event creation and updates
- **As a**: Operator
- **I want**: Logs that describe why events were created or updated.
- **So that**: I can audit deduplication behavior.

#### Preconditions

- Event upsert logic is implemented.

#### Acceptance Criteria

- For each call to the event upsert function:
  - A log entry is produced containing:
    - `raw_message_id`
    - `event_id`
    - `event_action` (`create` or `update`)
    - If `update`: which fields changed and their old/new values (or a concise description).
- Logs are emitted in a consistent, parseable format.
- No event create/update occurs without a corresponding log entry.

#### Out-of-scope

- Separate change-log table in the database (can be added later).

