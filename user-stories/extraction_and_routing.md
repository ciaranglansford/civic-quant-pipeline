## Extraction and Routing

### Purpose

Define strict behavior for structured extraction from messages and rules-based routing decisions for Phase 1 MVP.

### Story EXT-01 – Implement ExtractionAgent Interface

- **Story ID**: EXT-01
- **Title**: Define and implement `ExtractionAgent` interface
- **As a**: Backend engineer
- **I want**: A single service interface for message extraction.
- **So that**: The system can swap between stub logic and real LLM calls without changing callers.

#### Preconditions

- Normalized text and message metadata are available from ingest.

#### Acceptance Criteria

- A component named `ExtractionAgent` (class or module) exists with a clear method, for example:
  - `extract(normalized_text, message_time, source_channel_name) -> extraction_json`.
- The return type matches the `llm_extraction_schema` fields (topic, entities, affected countries, market_stats, sentiment, confidence, impact_score, is_breaking, breaking_window, event_time, source_claimed, summary_1_sentence, keywords, event_fingerprint).
- Callers do not depend on how extraction is implemented (stub vs. LLM).
- All extraction calls go through this interface.

#### Out-of-scope

- Integration with any specific LLM provider in Phase 1.

### Story EXT-02 – Stub Extraction That Produces Valid JSON

- **Story ID**: EXT-02
- **Title**: Implement deterministic stub extraction
- **As a**: System owner
- **I want**: A deterministic, non-LLM extraction implementation for early testing.
- **So that**: The rest of the pipeline can be built and tested without LLM dependencies.

#### Preconditions

- `ExtractionAgent` interface is defined.

#### Acceptance Criteria

- The stub implementation:
  - Produces valid JSON matching every field in `llm_extraction_schema`.
  - Uses simple heuristics or defaults (e.g., `topic="other"`, `sentiment="unknown"`, `impact_score=0`) where it cannot infer details.
  - Generates a stable `event_fingerprint` based on a deterministic function of `normalized_text` (e.g., hash) and static configuration.
- Stub logic does not make any external network or LLM calls.
- All validation rules pass for stub outputs (enums and numeric ranges).

#### Out-of-scope

- High-quality semantic understanding of the messages.

### Story EXT-03 – Store Extraction Results

- **Story ID**: EXT-03
- **Title**: Persist extraction results in database
- **As a**: Data consumer
- **I want**: Each raw message’s extraction stored with model version.
- **So that**: I can later re-run extraction or compare versions.

#### Preconditions

- Raw messages are stored in `raw_messages`.
- Stub extraction is implemented.

#### Acceptance Criteria

- An `extractions` table exists with at least:
  - `id` (primary key)
  - `raw_message_id` (foreign key to `raw_messages`)
  - `model_name` (string)
  - `extraction_json` (JSON)
  - `created_at` (timestamp)
- On ingest, after raw message insertion:
  - The system calls `ExtractionAgent`.
  - Stores one row in `extractions` linked to the raw message.
- For idempotent duplicate ingests, extraction is not duplicated; there is at most one extraction per unique raw message.

#### Out-of-scope

- Re-extraction with new model versions (Phase 2+).

### Story ROUT-01 – Define Routing Configuration

- **Story ID**: ROUT-01
- **Title**: Define deterministic routing configuration
- **As a**: System owner
- **I want**: A versioned configuration structure controlling routing thresholds and destinations.
- **So that**: Routing behavior is transparent and changeable without code changes (or with minimal changes in Phase 1).

#### Preconditions

- Extraction outputs are available per message.

#### Acceptance Criteria

- A routing configuration exists either as:
  - A JSON/YAML file loaded at startup, or
  - A clearly defined in-code structure representing the same information.
- Configuration includes at least:
  - Impact thresholds for `publish_priority` (`none`, `low`, `medium`, `high`).
  - Topic-based destination mappings (e.g., `macro_econ` -> `macro_events`).
  - Rules for when `requires_evidence` is set to `true` (may be disabled in Phase 1).
  - Rules for event actions (`create`, `update`, `ignore`) based on `impact_score`, `is_breaking`, and `event_fingerprint` match.
- Configuration version or hash is logged at startup.

#### Out-of-scope

- Maintaining a full configuration UI or editor.

### Story ROUT-02 – Implement Routing Logic

- **Story ID**: ROUT-02
- **Title**: Apply routing rules to each extraction
- **As a**: Backend engineer
- **I want**: A pure function that converts extraction JSON to routing decisions.
- **So that**: Routing decisions are consistent and testable.

#### Preconditions

- Routing configuration is available.
- Extraction JSON is produced for a message.

#### Acceptance Criteria

- A routing function exists, for example:
  - `route(extraction_json) -> routing_decision`.
- The routing decision includes:
  - `store_to: string[]`
  - `publish_priority: "none" | "low" | "medium" | "high"`
  - `requires_evidence: boolean`
  - `event_action: "create" | "update" | "ignore"`
  - `flags: string[]`
- Given the same input extraction and configuration, the routing function always produces the same output.
- Unit tests cover:
  - At least one high-impact breaking case.
  - At least one low-impact case that is not published.

#### Out-of-scope

- Using an LLM for routing decisions in Phase 1.

### Story ROUT-03 – Store Routing Decisions

- **Story ID**: ROUT-03
- **Title**: Persist routing decisions
- **As a**: Operator
- **I want**: A record of which routing decisions were made for each message.
- **So that**: I can audit and debug the pipeline’s behavior.

#### Preconditions

- Routing decisions are computed per extraction.

#### Acceptance Criteria

- A `routing_decisions` table exists with at least:
  - `id` (primary key)
  - `raw_message_id` (foreign key)
  - `store_to` (JSON list)
- `publish_priority` (string)
  - `requires_evidence` (boolean)
  - `event_action` (string)
  - `flags` (JSON list)
  - `created_at` (timestamp)
- For each ingested message, a corresponding routing decision row is created.
- Routing decisions are never updated; if logic must change, new messages get new decisions.

#### Out-of-scope

- Historical re-routing of old messages.

