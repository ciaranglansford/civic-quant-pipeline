### Story BE-24 - Add production quality scorecard and threshold checks for extraction outputs

* **Story ID**: BE-24
* **Title**: Define and enforce quality scorecard thresholds for Stage 3-5 stored outputs
* **As a**: Backend engineer
* **I want**: A deterministic quality scorecard over recent extraction/routing rows.
* **So that**: Calibration drift is visible early and release readiness is assessed against explicit thresholds.

#### Preconditions

* Extractions, routing decisions, and canonical payloads are persisted.
* Existing test and operations workflows can run targeted SQL or script-based checks.

#### Acceptance Criteria

* A quality scorecard query/script is added to operations docs with required metrics:
  * promote/update/monitor/archive distribution,
  * canonical-summary rewrite rate,
  * soft-related/burst downgrade rule fire rate,
  * payload completeness/integrity checks,
  * confidence/impact percentile spread.
* Baseline acceptance thresholds are documented for release readiness review.
  * Promote-rate ceiling target for repetitive wire bursts.
  * Maximum malformed-summary tolerance target (target: zero known malformed rewrite patterns).
  * Minimum downgrade-rule activation target during bursty windows.
* Verification workflow includes explicit pass/fail interpretation guidance.
* Tests or validation fixtures include one deterministic sample dataset expected to trigger scorecard flags.

#### Out-of-scope

* External observability platform rollout.
