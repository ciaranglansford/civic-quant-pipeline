### Story BE-09 – Build Phase 2 extraction processing orchestrator service

- **Story ID**: BE-09
- **Title**: Orchestrate eligibility, LLM call, validation, and persistence per batch
- **As a**: Backend engineer
- **I want**: A single service that executes the Phase 2 extraction workflow for eligible messages.
- **So that**: Scheduler and optional manual triggers share the same idempotent processing logic.

#### Preconditions

- Eligibility query, processing-state model, prompt loader, LLM client, and validator exist.

#### Acceptance Criteria

- A service function (for example `run_phase2_extraction_batch`) performs, in order:
  - Acquire/process a batch of eligible messages.
  - Mark each message `in_progress` with lease and `processing_run_id`.
  - Render prompt and call LLM client.
  - Validate strict JSON and map to `ExtractionJson`.
  - Persist extraction with trace fields.
  - Mark status `completed` or `failed` with error details.
- Service is idempotent:
  - Re-running after completion does not duplicate extraction rows.
  - Partial failures are retryable from failed/in-progress-expired states.
- The service returns a structured run summary: counts for `selected`, `processed`, `completed`, `failed`, `skipped`.
- Unit/integration tests cover mixed-success batches and retry behavior.

#### Out-of-scope

- Routing/event upsert redesign beyond existing Phase 1 behavior.
