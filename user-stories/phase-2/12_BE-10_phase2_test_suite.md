### Story BE-10 – Add comprehensive Phase 2 automated tests

- **Story ID**: BE-10
- **Title**: Cover scheduler workflow, validation strictness, and idempotency with tests
- **As a**: Backend engineer
- **I want**: Focused test coverage for all critical Phase 2 processing paths.
- **So that**: Refactors and future agent work do not break extraction processing guarantees.

#### Preconditions

- Phase 2 processing service and scheduler entrypoint exist.

#### Acceptance Criteria

- Test modules are added for:
  - eligibility/selection logic
  - strict JSON validation
  - orchestrator success/failure/retry behavior
  - scheduler overlap guard
  - optional manual trigger endpoint (if enabled)
- Idempotency tests prove no duplicate extraction rows for same `raw_message_id` across reruns.
- Tests verify deterministic handling of `event_fingerprint` persistence from validated payload.
- CI/local test command includes new Phase 2 tests.

#### Out-of-scope

- Load/performance testing at production scale.
