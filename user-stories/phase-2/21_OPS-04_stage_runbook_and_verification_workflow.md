### Story OPS-04 - Document stage-based local execution and verification workflow

* **Story ID**: OPS-04
* **Title**: Provide stage-by-stage runbook for listener, backend, extraction, reporting, reprocess, and tests
* **As a**: Backend engineer
* **I want**: A single coherent run/verify workflow tied to pipeline stages.
* **So that**: New contributors can execute and validate the full pipeline locally without ambiguity.

#### Preconditions

* Core docs and plans exist in `README.md`, `docs/`, and `plans/`.
* Operational jobs/scripts exist under `app/jobs` and listener module.

#### Acceptance Criteria

* Runbook docs define:
  * where each runtime component sits in the pipeline,
  * what each command consumes/produces,
  * when to run each command in local development.
* Local command guidance includes:
  * dependency install,
  * backend start,
  * listener start,
  * phase2 extraction run,
  * extraction probe,
  * digest/report run,
  * full and targeted tests,
  * preserve-raw reprocess and full reset workflows.
* Terminology is consistent across stories/plans/docs:
  * raw bulletin,
  * normalization,
  * literal reported claim,
  * deterministic triage,
  * event cluster,
  * entity indexing,
  * deferred enrichment,
  * scheduled reporting.
* Documentation explicitly preserves semantic guardrails for confidence/impact and non-truth-adjudication.
* Verification workflow includes Stage 1 deterministic calibration checks:
  * repetitive follow-on bulletins show downgrade behavior with triage rule IDs,
  * local domestic incident patterns cap urgency and force evidence routing,
  * high-risk unattributed summaries are safety-rewritten in canonical payload only,
  * raw vs canonical payload separation remains auditable.

#### Out-of-scope

* Deploying external dashboards or observability stacks.
