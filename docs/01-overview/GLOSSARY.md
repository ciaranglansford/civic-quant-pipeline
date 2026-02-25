# Glossary

- **Raw Message**: Original Telegram message persisted in `raw_messages`, including source metadata and normalized text.
- **Normalization**: Text cleaning step (`normalize_message_text`) that trims control chars and collapses whitespace.
- **Extraction**: Structured record (`ExtractionJson`) produced by `ExtractionAgent.extract` from raw text.
- **Event Fingerprint**: Deterministic hash key used to cluster related messages into canonical events.
- **Canonical Event**: Row in `events` representing a deduplicated/merged event over time.
- **Event Window**: Time range (`get_event_time_window`) used with fingerprint to decide create vs update behavior.
- **Routing Decision**: Per-message classification (`routing_decisions`) including destinations, publish priority, and flags.
- **Publish Priority**: `none|low|medium|high` derived from impact thresholds.
- **Breaking Window**: Enum value (`15m|1h|4h|none`) in extraction schema indicating urgency framing.
- **Digest**: Human-readable text summary built from recent events and sent to Telegram VIP destination.
- **Published Post**: Persisted record of outbound digest content and hash for deduplication.
- **Idempotent Ingest**: Behavior where duplicate source message IDs return `status="duplicate"` rather than creating new rows.
