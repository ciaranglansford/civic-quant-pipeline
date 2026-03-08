### Story BE-22 - Add deterministic promote-throttle for high-frequency source/topic bursts

* **Story ID**: BE-22
* **Title**: Cap repeated `new_event` promotions within short source/topic windows
* **As a**: Backend engineer
* **I want**: Deterministic promotion-throttle rules for repetitive wire bursts from the same source/topic.
* **So that**: Promote rates remain selective and reflect genuinely novel high-signal observations instead of repetitive restatements.

#### Preconditions

* Stage 1 triage and burst downgrade rules are active.
* `routing_decisions` persists `triage_action` and `triage_rules`.

#### Acceptance Criteria

* Deterministic promote-throttle is implemented for triage calibration.
  * Window key uses `(topic, source_claimed, 15-minute bucket)`.
  * First qualifying row may retain `promote`.
  * Subsequent `new_event` rows in the same key are downgraded to `update` unless exempt.
* Deterministic exemptions are explicit and auditable.
  * `impact_band = critical` may bypass throttle.
  * `materially_new = true` may bypass throttle.
* Rule IDs are persisted for observability.
  * `triage:promote_throttle_update`
  * `triage:promote_throttle_exempt_critical`
  * `triage:promote_throttle_exempt_material`
* Event association boundaries remain unchanged.
  * No soft-related event reassignment fallback introduced.
* Regression tests cover:
  * repeated source/topic burst with promote throttling,
  * exempt critical case,
  * exempt materially-new case.

#### Out-of-scope

* Learned/ML ranking or probabilistic suppression.
