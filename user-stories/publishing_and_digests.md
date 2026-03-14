## Canonical Digest Pipeline and Publishing

### Purpose

Define strict behavior for canonical digest generation and destination publishing.

Invariant:
**No publish attempt occurs unless a canonical artifact has already been persisted.**

The digest remains no-interpretation and informational only.

### Implementation Ownership and Local Adoption Notes

- Authoritative digest implementation lives in `app/digest/`.
- Digest job entrypoint remains `app/jobs/run_digest.py`.
- Legacy `app/services/digest_query.py`, `app/services/digest_builder.py`, `app/services/digest_runner.py`, and `app/services/telegram_publisher.py` are compatibility shims only.
- The repo has no migration framework; `create_all` does not alter existing tables.
- Local/dev schema adoption step for this refactor:
  - `python -m app.jobs.reset_dev_schema`

### Story PUB-01 - Deterministic Event Selection

- **Story ID**: PUB-01
- **Title**: Select events for the frozen digest window
- **As a**: Backend engineer
- **I want**: Deterministic event inclusion for digest generation.
- **So that**: Digest content is stable, auditable, and rerunnable.

#### Acceptance Criteria

- Window bounds are frozen at run start in UTC.
- Event inclusion rule is exact:
  - Include event iff `last_updated_at` is in `[window_start_utc, window_end_utc)`.
- Event ordering is deterministic:
  - `last_updated_at` descending, then `event_id` ascending.
- Re-entry behavior is explicit:
  - An event may appear again in later digests if `last_updated_at` changes into that later window.

### Story PUB-02 - Build Canonical Digest Model

- **Story ID**: PUB-02
- **Title**: Build canonical digest structure from selected events
- **As a**: Backend engineer
- **I want**: A structured canonical digest model as the source of digest semantics.
- **So that**: Rendering and destination publishing remain decoupled from core logic.

#### Acceptance Criteria

- Canonical builder returns structured digest sections/items.
- Topic ordering is alphabetical by normalized topic label.
- Item ordering inside each topic is:
  - `last_updated_at` descending, then `event_id` ascending.
- Canonical model does not contain destination-specific constraints.

### Story PUB-03 - Deterministic Canonical Text Rendering

- **Story ID**: PUB-03
- **Title**: Render canonical digest text deterministically
- **As a**: Operator
- **I want**: Canonical text artifact rendering to be deterministic.
- **So that**: Hashing, dedupe, and auditing are stable.

#### Acceptance Criteria

- Renderer input is canonical digest model.
- Renderer output is deterministic plain text bytes for identical input.
- Canonical text includes no runtime-generated timestamps or volatile fields.
- If window metadata is shown, only frozen `window_start_utc` and `window_end_utc` are used in fixed UTC format.
- Footer states informational/no-investment-advice behavior.

### Story PUB-04 - Persist Canonical Artifact Before Publish

- **Story ID**: PUB-04
- **Title**: Persist canonical artifact before adapter publish
- **As a**: System owner
- **I want**: Canonical digest artifacts persisted before any publish attempt.
- **So that**: Every publish attempt is traceable to a persisted canonical source artifact.

#### Acceptance Criteria

- `digest_artifacts` persistence concept exists.
- Artifact stores canonical text and deterministic canonical hash.
- The invariant is enforced:
  - **No publish attempt occurs unless a canonical artifact has already been persisted.**

### Story PUB-05 - Adapter-Based Destination Publishing

- **Story ID**: PUB-05
- **Title**: Publish via destination adapters from canonical source
- **As a**: System owner
- **I want**: Channel-specific publishing through adapters, not through canonical digest logic.
- **So that**: New channels can be added without changing digest semantics.

#### Acceptance Criteria

- Adapters consume canonical digest and/or rendered canonical text artifact.
- Telegram adapter is implemented now.
- Telegram presentation is adapter-owned and destination-specific:
  - bold `News Digest` title,
  - compact metadata block (window/events/topics),
  - deterministic `Top developments` section,
  - bold topic section headers with compact bullets,
  - understated `- Not investment advice.` footer.
- X adapter exists only as placeholder/deferred (not production publishing support).
- Channel constraints do not leak into canonical model/builder/renderer.

### Story PUB-06 - Minimal Dedupe and Rerun Safety

- **Story ID**: PUB-06
- **Title**: Per-destination rerun-safe dedupe
- **As a**: Operator
- **I want**: Minimal, deterministic dedupe behavior for reruns.
- **So that**: Successful destination publishes are not duplicated and failed ones can retry.

#### Acceptance Criteria

- Artifact identity uses `canonical_hash`.
- Destination payload identity uses payload `content_hash`.
- For an artifact+destination:
  - If status is `published`, skip publish on rerun.
  - If status is `failed`, retry on rerun.
- No per-destination dedupe windows in this version.

### Story PUB-07 - Publication Audit Persistence

- **Story ID**: PUB-07
- **Title**: Persist per-destination publish outcomes
- **As a**: Operator
- **I want**: Destination-level audit rows linked to canonical artifact.
- **So that**: I can trace published/failed/deferred outcomes per destination.

#### Acceptance Criteria

- `published_posts` persists per-destination outcomes linked to `digest_artifacts`.
- Rows include destination status and payload hash.
- Reruns update/skip based on stored status semantics.

### Deferred / Placeholder Scope

- Real X publishing is deferred.
- Placeholder adapter may return deferred status but does not publish externally.
- Full run/artifact/publication schema split and advanced dedupe policies are deferred.
