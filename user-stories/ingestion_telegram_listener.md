## Ingestion – Telegram Listener (MTProto)

### Purpose

Define strict behavior for the MTProto-based Telegram listener that reads from a single external channel and posts messages to the backend ingest endpoint.

### Story ING-01 – Configure Telethon Client

- **Story ID**: ING-01
- **Title**: Configure Telethon client with API credentials and session storage
- **As a**: System owner
- **I want**: The listener to authenticate as my Telegram user account using Telethon and reuse a local session file.
- **So that**: It can continuously read messages from the specified Telegram channel without re-authentication prompts.

#### Preconditions

- Telegram API ID and API hash are available.
- A session name for Telethon is configured via environment variable.

#### Acceptance Criteria

- The listener code uses Telethon `TelegramClient` with:
  - `api_id` and `api_hash` from environment variables.
  - A persistent session name (file-based) from an environment variable.
- On first run, the client prompts for login and then stores the session locally.
- On subsequent runs, the client starts without requiring a new login.
- If credentials are missing or invalid, the listener exits with a clear error message including which variable is misconfigured.

#### Out-of-scope

- Handling multiple user accounts.
- Handling multiple sessions in parallel.

### Story ING-02 – Subscribe to Single Source Channel

- **Story ID**: ING-02
- **Title**: Listen to one configured Telegram channel
- **As a**: System owner
- **I want**: The listener to subscribe to exactly one external Telegram channel specified in configuration.
- **So that**: Only the intended market feed is ingested.

#### Preconditions

- `TG_SOURCE_CHANNEL` is configured as a username or numeric ID.
- Telethon client is authenticated and connected.

#### Acceptance Criteria

- The listener resolves `TG_SOURCE_CHANNEL` to a Telegram entity (channel or supergroup).
- The listener subscribes only to this entity for new messages.
- Messages from other chats, dialogs, or direct messages are ignored and never sent to the backend.
- If the channel cannot be resolved, the listener logs a clear error and exits without attempting ingestion.

#### Out-of-scope

- Listening to multiple channels.
- Auto-discovery of channels.

### Story ING-03 – Build Ingest Payload

- **Story ID**: ING-03
- **Title**: Build backend ingest payload for each new message
- **As a**: Backend engineer
- **I want**: The listener to construct a JSON payload that matches the ingest API schema.
- **So that**: The backend can validate and store all required fields consistently.

#### Preconditions

- A new message event is received from the configured channel.
- The backend ingest endpoint path is known (e.g., `/ingest/telegram`).

#### Acceptance Criteria

- For each new message, the listener constructs a payload with:
  - `source_channel_id`: stable numeric or string identifier for the channel.
  - `source_channel_name`: human-readable channel name if available.
  - `telegram_message_id`: Telegram message ID as string.
  - `message_timestamp_utc`: message timestamp converted to UTC ISO8601.
  - `raw_text`: full text content of the message (empty string if none).
  - `raw_entities_if_available`: raw entities/markup from Telegram if available, otherwise `null`.
  - `forwarded_from_if_available`: original source name if the message is forwarded, otherwise `null`.
- The payload is strictly JSON-serializable (no Telethon objects).
- If a required field cannot be determined, the listener logs an error and skips sending that message.

#### Out-of-scope

- Any preprocessing or normalization of text.
- Any LLM calls or extraction logic.

### Story ING-04 – Post to Backend with Retries

- **Story ID**: ING-04
- **Title**: POST messages to backend ingest endpoint with retry logic
- **As a**: System owner
- **I want**: The listener to reliably deliver each message to the backend, with retries on transient failures.
- **So that**: Temporary network issues do not cause message loss.

#### Preconditions

- Ingest API base URL is configured via environment variable.
- Listener can construct a valid payload for a new message.

#### Acceptance Criteria

- For each new message, the listener performs an HTTP `POST` to `<INGEST_API_BASE_URL>/ingest/telegram` with JSON payload.
- On HTTP 2xx response, the message is considered successfully delivered.
- On network errors or HTTP 5xx responses:
  - The listener retries delivery a configurable number of times with backoff.
  - If all retries fail, the error is logged with channel ID, message ID, and last response status.
- On HTTP 4xx (other than 429) responses, the listener logs the error and does not retry.
- The listener never silently drops messages without logging an error.

#### Out-of-scope

- Queuing or offline buffering beyond in-memory retries.

### Story ING-05 – Logging of Ingest Attempts

- **Story ID**: ING-05
- **Title**: Log ingest successes and failures
- **As a**: Operator
- **I want**: Basic structured logging for each ingest attempt.
- **So that**: I can audit which messages were delivered and which failed.

#### Preconditions

- Stories ING-01 to ING-04 are implemented.

#### Acceptance Criteria

- For every POST attempt, the listener logs:
  - `source_channel_id`
  - `telegram_message_id`
  - `attempt_number`
  - `result` (`success` or `failure`)
  - For failures: HTTP status or error type.
- Logs are emitted in a consistent, parseable format (e.g., JSON lines or clearly structured text).
- Successful deliveries produce a single success log entry; failed deliveries after all retries produce at least one failure log entry.

#### Out-of-scope

- Centralized log aggregation or dashboards.

