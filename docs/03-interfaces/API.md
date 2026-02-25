# API and Interfaces

## http-api-overview

The repository exposes an HTTP API via FastAPI.

Base app factory: `app.main:create_app`.
Router registration: `app.include_router(ingest_router)`.

## endpoints

## get-health
- **Method/Path:** `GET /health`
- **Handler:** inline `health()` function in `app.main:create_app`
- **Response model:** `HealthResponse`
- **Response body:**
  ```json
  { "status": "ok" }
  ```
- **Auth:** none implemented in code.

## post-ingest-telegram
- **Method/Path:** `POST /ingest/telegram`
- **Handler:** `app.routers.ingest:ingest_telegram`
- **Request model:** `TelegramIngestPayload`
- **Response model:** `IngestResponse`
- **Auth:** none implemented in code.

### request-fields-telegramingestpayload
| Field | Type | Required | Notes |
|---|---|---|---|
| `source_channel_id` | `str` | yes | Channel identifier string. |
| `source_channel_name` | `str \| null` | no | Human-readable source name. |
| `telegram_message_id` | `str` | yes | Message identifier within source channel. |
| `message_timestamp_utc` | `datetime` | yes | Parsed by Pydantic. |
| `raw_text` | `str` | yes | Original message text. |
| `raw_entities_if_available` | `Any \| null` | no | Pass-through raw entities blob. |
| `forwarded_from_if_available` | `str \| null` | no | Forward source label if present. |

### response-fields-ingestresponse
| Field | Type | Notes |
|---|---|---|
| `status` | `"created" \| "duplicate"` | Duplicate indicates idempotent hit on existing raw message. |
| `raw_message_id` | `int` | Primary key of `raw_messages`. |
| `event_id` | `int \| null` | Canonical event ID when created/found. |
| `event_action` | `"create" \| "update" \| "ignore" \| null` | `null` on duplicate shortcut path. |

### error-behavior
- Unexpected exceptions in handler path return HTTP `500` with body `{ "detail": "ingest failed" }`.
- Validation errors are FastAPI/Pydantic standard 422 responses.

## non-http-interfaces

## cli-entrypoints
| Command | Entry function | Purpose |
|---|---|---|
| `python -m app.jobs.run_digest` | `app.jobs.run_digest:main` | Generate + publish digest in configured window. |
| `python -m listener.telegram_listener` | `listener.telegram_listener:main` | Start Telegram listener and forward messages to ingest API. |

## event-consumer-interface
- Listener subscribes to Telethon `events.NewMessage(chats=entity)` and maps each event into HTTP ingest payload.

## examples-from-tests

### ingest-example
The test suite posts this shape to `/ingest/telegram`:
```json
{
  "source_channel_id": "c1",
  "source_channel_name": "feed",
  "telegram_message_id": "m1",
  "message_timestamp_utc": "<utc-iso8601>",
  "raw_text": "FED hikes 25bp; USD jumps",
  "raw_entities_if_available": null,
  "forwarded_from_if_available": null
}
```

Expected first response status is `created`; second identical request returns `duplicate`.
