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
13. `BE-11` wire-bulletin structural normalization
14. `BE-12` literal reported-claim extraction semantic contract
15. `BE-13` deterministic entity/source canonicalization
16. `BE-14` deterministic triage and promotion actioning
17. `BE-15` repetitive/paraphrase/contradictory bulletin event-cluster refinement
18. `DB-03` entity indexing dataset layer
19. `BE-16` deferred enrichment selection hooks
20. `BE-17` event-level scheduled reporting readiness checks
21. `OPS-04` stage-based runbook and verification workflow
22. `BE-18` deterministic triage calibration for first-seen versus follow-on bulletins
23. `BE-19` related-bulletin convergence refinement without collapsing observations
24. `BE-20` summary semantic safety guardrails for extraordinary claims
25. `BE-21` local domestic incident routing override


## Implementation status

Stories in this folder are the canonical implementation backlog for Phase 2 and adjacent execution-readiness work.
Some earlier stories are already implemented in code; newer stories extend the target-state pipeline from normalization and deterministic triage through indexing, deferred enrichment hooks, and reporting readiness.
