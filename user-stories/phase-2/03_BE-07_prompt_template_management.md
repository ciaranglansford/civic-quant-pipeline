### Story BE-07 – Add ExtractionAgent prompt template loader and versioning

- **Story ID**: BE-07
- **Title**: Manage strict ExtractionAgent prompt templates in code
- **As a**: Backend engineer
- **I want**: A versioned prompt template loaded from repository files.
- **So that**: LLM behavior is repeatable and auditable across runs.

#### Preconditions

- Extraction contract fields are defined in `plans/llm_usage_and_prompts.md`.

#### Acceptance Criteria

- A prompt template file is added under a stable path (for example `app/prompts/extraction_agent_v1.txt`).
- A prompt-loading utility exists that:
  - Loads template text from disk.
  - Injects `normalized_text`, `message_time`, and `source_channel_name` placeholders.
  - Returns prompt text plus `prompt_version` (e.g., `extraction_agent_v1`).
- Template instructions explicitly enforce:
  - JSON-only output.
  - No extra fields.
  - Enum and numeric range constraints.
  - Deterministic `event_fingerprint` requirement.
- Extraction persistence includes `prompt_version` for each processed message.
- Tests validate successful template rendering and failure on missing placeholders/files.

#### Out-of-scope

- Runtime editing of prompts via admin UI.
