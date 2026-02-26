## Phase 2 User Stories – Scheduled Extraction Processing

This folder contains narrowly-scoped, implementation-ordered stories for the Phase 2 backend slice:

1. `BE-06` message eligibility selection
2. `DB-01` processing state + watermark storage
3. `BE-07` prompt template management/versioning
4. `INF-01` OpenAI configuration
5. `INF-02` OpenAI extraction client
6. `BE-08` strict response validation
7. `DB-02` extraction traceability persistence
8. `BE-09` processing orchestration service
9. `OPS-01` 10-minute scheduler + concurrency guard
10. `OPS-02` optional admin trigger endpoint
11. `OPS-03` observability for runs/failures
12. `BE-10` focused Phase 2 automated tests


## Implementation status

Phase 2 stories BE-06 through BE-10 and OPS-01 through OPS-03 are implemented in code and covered by automated tests in `tests/test_e2e_backend.py` and `tests/test_phase2_services.py`.
