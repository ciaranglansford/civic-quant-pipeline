## Publishing and 4-Hour VIP Digests

### Purpose

Define strict behavior for generating and publishing 4-hour digests to the VIP Telegram chat, enforcing the no-interpretation rule.

### Story PUB-01 – Query Events for Digest Window

- **Story ID**: PUB-01
- **Title**: Fetch events for the last N hours
- **As a**: Backend engineer
- **I want**: A query that returns all relevant events in a configurable time window.
- **So that**: The digest generator can build summaries for the VIP chat.

#### Preconditions

- `events` table exists and is populated.
- Configuration value `VIP_DIGEST_HOURS` is available.

#### Acceptance Criteria

- A function exists, for example:
  - `get_events_for_digest(hours) -> list[events]`.
- The function:
  - Selects events whose `event_time` or `last_updated_at` falls within the last `hours` relative to execution time.
  - Allows `hours` to default to `VIP_DIGEST_HOURS`.
  - Returns events along with their topics and latest summaries.
- The query is index-supported and efficient for at least a 7-day history.

#### Out-of-scope

- Filtering by audience-specific preferences.

### Story PUB-02 – Generate Category-Grouped Digest Text

- **Story ID**: PUB-02
- **Title**: Generate digest text grouped by topic
- **As a**: VIP user
- **I want**: A digest with grouped headlines and key facts but no trading advice.
- **So that**: I can quickly scan what matters in the last few hours.

#### Preconditions

- A list of events for the digest window is available.

#### Acceptance Criteria

- A digest generation function exists, for example:
  - `build_digest(events) -> string`.
- Behavior:
  - Groups events by topic.
  - For each topic section:
    - Renders a heading (e.g., `Macro / Central Banks`).
    - Lists each event as a bullet with:
      - 1-sentence summary from `summary_1_sentence`.
      - Key numbers and entities extracted from the event or its messages where available.
      - A corroboration label (Phase 1: `corroboration: unknown` or derived from simple rules).
  - Adds a header indicating time window and counts per topic.
  - Adds a footer disclaimer explicitly stating that the digest is not investment advice.
- Generated text does not:
  - Recommend trades or positions.
  - Use language like “buy”, “sell”, “enter”, “exit”, or similar prescriptive phrasing.

#### Out-of-scope

- Long-form narrative writeups (Phase 2+).

### Story PUB-03 – Post Digest to VIP Telegram Chat

- **Story ID**: PUB-03
- **Title**: Send digest via Telegram bot
- **As a**: System owner
- **I want**: Digests posted to a VIP Telegram chat using a bot.
- **So that**: The VIP group receives structured updates automatically.

#### Preconditions

- Telegram bot token and VIP chat ID are configured.
- Digest text is generated successfully.

#### Acceptance Criteria

- A component exists that:
  - Uses the Telegram Bot API with `TG_BOT_TOKEN`.
  - Sends the digest text to `TG_VIP_CHAT_ID`.
- On success:
  - A log entry records the publish attempt with destination and timestamp.
- On failure:
  - The error is logged with enough detail to debug (HTTP status, response body).
  - No infinite retry loop occurs; failures are bounded and visible.

#### Out-of-scope

- Splitting very long digests into multiple messages (optional enhancement).

### Story PUB-04 – Record Published Digests

- **Story ID**: PUB-04
- **Title**: Persist digest publishing events
- **As a**: Operator
- **I want**: An audit log of what was published, where, and when.
- **So that**: I can trace any digest back to its underlying events.

#### Preconditions

- Digests are generated and posted to Telegram.

#### Acceptance Criteria

- A `published_posts` table exists with at least:
  - `id` (primary key)
  - `event_id` (nullable foreign key, if digest is tied to a single event) or `null` for multi-event digests
  - `destination` (e.g., `vip_telegram`)
  - `published_at` (timestamp)
  - `content` (text)
  - `content_hash` (string)
- For each digest publish:
  - A new `published_posts` row is inserted with `destination="vip_telegram"`.
  - `content_hash` is computed deterministically from the digest text.
- The system does not publish the exact same content hash to the same destination more than once within a configured time window.

#### Out-of-scope

- Detailed per-event linkage for multi-event digests (can be addressed via separate link tables later).

