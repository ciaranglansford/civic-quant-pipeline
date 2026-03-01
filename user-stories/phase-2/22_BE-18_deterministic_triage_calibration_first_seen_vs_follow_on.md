### Story BE-18 - Calibrate deterministic triage for first-seen vs follow-on bulletins

* **Story ID**: BE-18
* **Title**: Apply deterministic score-band and novelty calibration for first-seen versus repetitive bulletins
* **As a**: Backend engineer
* **I want**: Triage decisions to use deterministic calibration context instead of treating model scores as direct urgency truth.
* **So that**: Repetitive low-delta follow-on bulletins do not retain the same top-priority behavior as first-seen novel observations.

#### Preconditions

* Canonical extraction payloads are available in `canonical_payload_json`.
* Deterministic triage persistence exists via `routing_decisions.triage_action` and `routing_decisions.triage_rules`.

#### Acceptance Criteria

* Triage derives routing-only score bands without mutating stored raw scores.
  * `impact_band`: critical/high/medium/low using fixed deterministic thresholds.
  * `confidence_band`: strong/usable/weak using fixed deterministic thresholds.
* Triage derives novelty state deterministically (`new_event`, `related_update`, `repeat_low_delta`) from exact-event context and low-delta rules.
* Material novelty is computed using explicit gates.
  * New canonical person/org/country relative to candidate event context.
  * Impact band increase by at least one level.
  * Reaction-language to operational-language shift in summary tags.
  * Source class shift from commentary to authority/direct reporting.
* Burst suppression caps urgency for repetitive low-delta follow-ons in short windows.
* Triage persistence includes explicit rule IDs for auditability.
  * Includes score/confidence bands and downgrade/burst/local override rule IDs.
* Raw extraction values remain unchanged.
  * No overwrite of validated `payload_json` score fields.

#### Out-of-scope

* Learned ranking models or probabilistic triage.
