from __future__ import annotations

from typing import Any


SERVER_NAME = "civicquant-db-mcp"
SERVER_VERSION = "0.1.0"
SERVER_PROTOCOL_VERSION = "2025-03-26"

DB_URL_ENV_VAR = "CIVICQUANT_MCP_DATABASE_URL"
APP_DB_URL_ENV_VAR = "DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./civicquant_dev.db"

READONLY_SQL_DEFAULT_MAX_ROWS = 100
READONLY_SQL_HARD_MAX_ROWS = 500
LINEAGE_MAX_MESSAGES = 100


def _id_schema(field_name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            field_name: {
                "type": "integer",
                "minimum": 1,
            }
        },
        "required": [field_name],
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_event",
        "description": "Return one event with linked raw message ids and latest extraction summary fields.",
        "inputSchema": _id_schema("event_id"),
    },
    {
        "name": "get_raw_message",
        "description": "Return one raw message with extraction, routing, and event-link context.",
        "inputSchema": _id_schema("raw_message_id"),
    },
    {
        "name": "get_event_lineage",
        "description": "Return event lineage across event_messages, raw_messages, extractions, and routing_decisions.",
        "inputSchema": _id_schema("event_id"),
    },
    {
        "name": "compare_extraction_to_event",
        "description": "Compare extraction fields for a raw message against its linked event state.",
        "inputSchema": _id_schema("raw_message_id"),
    },
    {
        "name": "find_duplicate_candidate_events",
        "description": "Find likely duplicate events near a target event using deterministic similarity signals.",
        "inputSchema": _id_schema("event_id"),
    },
    {
        "name": "run_readonly_sql",
        "description": "Run a SELECT-only SQL query with a strict row cap.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "max_rows": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": READONLY_SQL_HARD_MAX_ROWS,
                    "default": READONLY_SQL_DEFAULT_MAX_ROWS,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rank_topic_opportunities",
        "description": "Rank constrained opportunity topics for a window using deterministic event-layer scoring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "string", "minLength": 1},
                "end_time": {"type": "string", "minLength": 1},
                "topic_universe": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["start_time", "end_time", "topic_universe"],
            "additionalProperties": False,
        },
    },
    {
        "name": "build_opportunity_memo_input",
        "description": "Build deterministic internal memo input pack from event-layer data for one topic/window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "string", "minLength": 1},
                "end_time": {"type": "string", "minLength": 1},
                "topic": {"type": "string", "minLength": 1},
            },
            "required": ["start_time", "end_time", "topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_topic_timeline",
        "description": "Return ordered event progression for a topic in a time window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "string", "minLength": 1},
                "end_time": {"type": "string", "minLength": 1},
                "topic": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": ["start_time", "end_time", "topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_topic_driver_pack",
        "description": "Return deterministic driver groups and selected primary driver for a topic/window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_time": {"type": "string", "minLength": 1},
                "end_time": {"type": "string", "minLength": 1},
                "topic": {"type": "string", "minLength": 1},
            },
            "required": ["start_time", "end_time", "topic"],
            "additionalProperties": False,
        },
    },
]
