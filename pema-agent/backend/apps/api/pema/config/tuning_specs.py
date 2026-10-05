# ported from: src/config/env.ts (defaults) and src/config/tuning-definitions.ts (kind, min, max, options)
"""The 72 tuning parameters of zalo-agent as DATA: key, kind, default, bounds, enum options.

Generated mechanically from the two TypeScript files above (package A) so that every package can call
``get_tuning(key)`` with the ORIGINAL defaults from day one. Nothing here was retyped by hand. Keys keep
the original names; they are also the (unprefixed) environment variable names that override a default.

Package D1 owns this area from here on: it adds labels, hints, groups and presets
(``tuning_definitions.py``, ``tuning_number_presets.py``) and the DB-backed provider; the numbers below
change only when the original changes. Cross-rules between parameters (``validate_tuning``) are D1's too.

``max`` of ``LLM_MAX_OUTPUT_TOKENS`` is the 200000 of tuning-definitions.ts (env.ts has no upper bound).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

type TuningKind = Literal["number", "boolean", "enum", "timezone"]
type TuningValue = int | float | bool | str


@dataclass(frozen=True)
class TuningSpec:
    kind: TuningKind
    default: TuningValue
    minimum: float | None = None
    maximum: float | None = None
    options: tuple[str, ...] = ()


TUNING_SPECS: Final[dict[str, TuningSpec]] = {
    "BOT_TIMEZONE": TuningSpec(kind="timezone", default="Asia/Ho_Chi_Minh"),
    "UPDATE_CHECK_ENABLED": TuningSpec(kind="boolean", default=True),
    "UPDATE_CHECK_INTERVAL_MINUTES": TuningSpec(kind="number", default=60, minimum=5, maximum=1440),
    "LLM_MAX_STEPS": TuningSpec(kind="number", default=10, minimum=1, maximum=30),
    "LLM_MAX_OUTPUT_TOKENS": TuningSpec(kind="number", default=16384, minimum=256, maximum=200000),
    "LLM_TURN_TIMEOUT_MS": TuningSpec(kind="number", default=900000, minimum=60000, maximum=3600000),
    "LLM_REASONING_EFFORT": TuningSpec(
        kind="enum",
        default="medium",
        options=(
            "off",
            "low",
            "medium",
            "high",
            "xhigh",
        ),
    ),
    "TOOL_LOOP_SAME_ARGS_BLOCK": TuningSpec(kind="number", default=5, minimum=2, maximum=30),
    "TOOL_LOOP_SAME_TOOL_BLOCK": TuningSpec(kind="number", default=8, minimum=2, maximum=50),
    "TOOL_LOOP_NO_PROGRESS_BLOCK": TuningSpec(kind="number", default=5, minimum=2, maximum=30),
    "LLM_CACHE_SESSION_ENABLED": TuningSpec(kind="boolean", default=True),
    "MID_TURN_INJECTION_ENABLED": TuningSpec(kind="boolean", default=True),
    "BUSY_ACK_AFTER_MS": TuningSpec(kind="number", default=600000, minimum=0, maximum=3600000),
    "HISTORY_CONTEXT_LIMIT": TuningSpec(kind="number", default=20, minimum=1, maximum=200),
    "LLM_CONTEXT_WINDOW": TuningSpec(kind="number", default=128000, minimum=4000, maximum=2000000),
    "HISTORY_IMAGE_CONTEXT_LIMIT": TuningSpec(kind="number", default=1, minimum=0, maximum=20),
    "SUMMARY_TRIGGER_MESSAGES": TuningSpec(kind="number", default=30, minimum=5, maximum=500),
    "MEMORY_MAX_FACTS_PER_SUBJECT": TuningSpec(kind="number", default=50, minimum=1, maximum=1000),
    "HISTORY_MAX_MESSAGES_PER_THREAD": TuningSpec(kind="number", default=500, minimum=20, maximum=100000),
    "WEB_SEARCH_MAX_RESULTS": TuningSpec(kind="number", default=5, minimum=1, maximum=10),
    "WEB_FETCH_MAX_CHARS": TuningSpec(kind="number", default=15000, minimum=2000, maximum=100000),
    "DOCUMENT_MAX_PER_HOUR": TuningSpec(kind="number", default=10, minimum=1, maximum=200),
    "VIDEO_MAX_DURATION_MINUTES": TuningSpec(kind="number", default=30, minimum=1, maximum=300),
    "VIDEO_MAX_SIZE_MB": TuningSpec(kind="number", default=100, minimum=1, maximum=2000),
    "VIDEO_MAX_PER_HOUR": TuningSpec(kind="number", default=15, minimum=1, maximum=200),
    "VIDEO_MAX_CONCURRENT": TuningSpec(kind="number", default=1, minimum=1, maximum=8),
    "VIDEO_SOURCE_RETRIES": TuningSpec(kind="number", default=4, minimum=1, maximum=10),
    "VIDEO_RETRY_DELAY_MS": TuningSpec(kind="number", default=1500, minimum=1000, maximum=30000),
    "DOCUMENT_MAX_BLOCKS": TuningSpec(kind="number", default=60, minimum=1, maximum=500),
    "DOCUMENT_MAX_ROWS": TuningSpec(kind="number", default=200, minimum=1, maximum=5000),
    "DOCUMENT_MAX_CHARS": TuningSpec(kind="number", default=20000, minimum=500, maximum=500000),
    "DOCUMENT_MAX_SHEETS": TuningSpec(kind="number", default=10, minimum=1, maximum=50),
    "IMAGE_GEN_MAX_PER_HOUR": TuningSpec(kind="number", default=10, minimum=1, maximum=100),
    "IMAGE_GEN_STALL_MS": TuningSpec(kind="number", default=90000, minimum=30000, maximum=300000),
    "IMAGE_GEN_TIMEOUT_MS": TuningSpec(kind="number", default=600000, minimum=30000, maximum=1800000),
    "IMAGE_GEN_QUALITY": TuningSpec(
        kind="enum",
        default="high",
        options=(
            "auto",
            "low",
            "medium",
            "high",
            "standard",
            "hd",
        ),
    ),
    "ZALO_IMAGE_QUALITY": TuningSpec(
        kind="enum",
        default="normal",
        options=(
            "thumb",
            "normal",
            "hd",
        ),
    ),
    "ZALO_RICH_TEXT_ENABLED": TuningSpec(kind="boolean", default=True),
    "ZALO_RICH_TEXT_MAX_PAYLOAD_BYTES": TuningSpec(kind="number", default=3250, minimum=1000, maximum=3600),
    "ZALO_MAX_MESSAGE_CHARS": TuningSpec(kind="number", default=2000, minimum=500, maximum=4000),
    "ZALO_MAX_MESSAGE_PARTS": TuningSpec(kind="number", default=5, minimum=1, maximum=20),
    "MESSAGE_BATCH_DEBOUNCE_MS": TuningSpec(kind="number", default=2500, minimum=0, maximum=15000),
    "SEND_DELAY_MIN_MS": TuningSpec(kind="number", default=800, minimum=0, maximum=60000),
    "SEND_DELAY_MAX_MS": TuningSpec(kind="number", default=2500, minimum=0, maximum=60000),
    "TYPING_REFRESH_MS": TuningSpec(kind="number", default=3000, minimum=1000, maximum=10000),
    "ZALO_BOT_POLL_TIMEOUT_SECONDS": TuningSpec(kind="number", default=30, minimum=5, maximum=60),
    "AGENT_TRACE_ENABLED": TuningSpec(kind="boolean", default=True),
    "AGENT_TRACE_MAX_CHARS": TuningSpec(kind="number", default=500, minimum=50, maximum=20000),
    "AGENT_TRACE_RETENTION_DAYS": TuningSpec(kind="number", default=7, minimum=1, maximum=365),
    "MEDIA_RETENTION_DAYS": TuningSpec(kind="number", default=7, minimum=1, maximum=365),
    "SCHEDULER_ENABLED": TuningSpec(kind="boolean", default=True),
    "SCHEDULER_TICK_MS": TuningSpec(kind="number", default=30000, minimum=5000, maximum=300000),
    "SCHEDULER_MIN_INTERVAL_MINUTES": TuningSpec(kind="number", default=5, minimum=1, maximum=1440),
    "SCHEDULER_MAX_JOBS_PER_THREAD": TuningSpec(kind="number", default=20, minimum=1, maximum=200),
    "SCHEDULER_MAX_PROACTIVE_PER_DAY": TuningSpec(kind="number", default=10, minimum=1, maximum=100),
    "SCHEDULER_SEND_GAP_MS": TuningSpec(kind="number", default=20000, minimum=0, maximum=300000),
    "SCHEDULER_ONCE_GRACE_MINUTES": TuningSpec(kind="number", default=10, minimum=1, maximum=1440),
    "SCHEDULER_DEFERRED_RUN_HOUR": TuningSpec(kind="number", default=8, minimum=0, maximum=23),
    "SCHEDULER_RUN_LOG_KEEP": TuningSpec(kind="number", default=50, minimum=5, maximum=1000),
    "KB_CHUNK_CHARS": TuningSpec(kind="number", default=1200, minimum=400, maximum=4000),
    "KB_CHUNK_OVERLAP_PERCENT": TuningSpec(kind="number", default=10, minimum=0, maximum=50),
    "KB_TOP_K": TuningSpec(kind="number", default=5, minimum=1, maximum=20),
    "KB_RRF_K": TuningSpec(kind="number", default=20, minimum=5, maximum=100),
    "KB_MAX_RESULT_CHARS": TuningSpec(kind="number", default=8000, minimum=2000, maximum=20000),
    "KB_MAX_FILE_MB": TuningSpec(kind="number", default=20, minimum=1, maximum=100),
    "KB_EXTRACT_TIMEOUT_MS": TuningSpec(kind="number", default=60000, minimum=5000, maximum=600000),
    "KB_EXTRACT_MAX_RAM_MB": TuningSpec(kind="number", default=192, minimum=64, maximum=256),
    "KB_MAX_INGEST_ATTEMPTS": TuningSpec(kind="number", default=2, minimum=1, maximum=5),
    "MCP_ENABLED": TuningSpec(kind="boolean", default=True),
    "MCP_CONNECT_TIMEOUT_MS": TuningSpec(kind="number", default=15000, minimum=1000, maximum=120000),
    "MCP_TOOL_TIMEOUT_MS": TuningSpec(kind="number", default=60000, minimum=1000, maximum=300000),
    "MCP_HEALTH_INTERVAL_MS": TuningSpec(kind="number", default=30000, minimum=5000, maximum=600000),
}
