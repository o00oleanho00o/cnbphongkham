# ported from: src/shared/logger.ts
"""Structured logger with turn context, safe errors and PII redaction.

Forced deviation: pino (+ pino-pretty, pino-roll) becomes stdlib ``logging``. The original behaviour is
kept:

* two destinations at two levels: console at ``LOG_LEVEL``; a daily rotating file at ``trace``/DEBUG
  level when ``LOG_FILE_ENABLED`` (the file must be COMPLETE: when you need it the incident already
  happened and you cannot go back and enable debug);
* the fields of the running turn (``account_id``, ``thread_id``, ``turn_id``, see
  ``turn_log_context``) are attached to EVERY line, also from modules that create their own logger;
* ``err`` goes through ``serialize_error_safely`` (never the raw exception attributes).

Each record carries ITS OWN fields: the shared turn context is copied per record, never mutated. This
is the regression covered by ``logger-turn-fields.test.ts`` (pino's mixin merge once wrote into the
shared object, so each line leaked the fields of the previous ones).

Additions for the clinic (not in the original): any field whose key is in ``REDACTED_KEYS`` is replaced
by ``[redacted]``. Rule from AGENT.md: never log PII. Loggers log ids, counts and codes; message text,
names and phone numbers do not belong in a log even by accident.

Usage: ``log = create_logger("scheduler")`` then ``log.info("job fired", job_id=job.id)`` and
``log.error("send failed", err=exc, thread_id=tid)``.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pema.shared.safe_error_serializer import serialize_error_safely
from pema.shared.turn_log_context import current_turn_log_context

REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "content",
        "message_text",
        "body",
        "masked_text",
        "sender_name",
        "display_name",
        "full_name",
        "phone",
        "email",
        "address",
        "birth_date",
        "national_id",
        "token",
        "password",
        "api_key",
        "secret",
        "authorization",
        "headers",
        "cookie",
        "credential",
        # package G (SECURITY-REVIEW-AI01 SEC-05): other names a patient's words or a secret travel under
        "caption",
        "draft_text",
        "final_text",
        "raw_text",
        "prompt",
        "system_prompt",
        "reply",
        "summary",
        "fact",
        "query",
        "quote",
        "patient_name",
        "credentials",
        "api_secret",
        "set_cookie",
        "set-cookie",
        "x-api-key",
    }
)
"""Field keys never written to a log. Matching is case-insensitive."""

REDACTED_SUFFIXES: tuple[str, ...] = (
    "_token",
    "_secret",
    "_password",
    "_api_key",
    "_cookie",
    "_credential",
    "_credentials",
    "_phone",
    "_email",
    "_text",
    "_body",
)
"""A key that ENDS with one of these is redacted as well (``bot_token``, ``refresh_token``, ``masked_body``).
Not a substring match on purpose: ``tokens_in`` or ``max_output_tokens`` are counters and stay readable."""


def is_redacted_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in REDACTED_KEYS or lowered.endswith(REDACTED_SUFFIXES)


REDACTED = "[redacted]"

_ROOT_NAME = "pema"
_RESERVED = "pema_fields"


class _TurnContextFilter(logging.Filter):
    """Copies the running turn's fields into the record, per record (never shared)."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = current_turn_log_context()
        fields: dict[str, Any] = dict(getattr(record, _RESERVED, {}))
        if context is not None:
            fields = {
                "account_id": context.account_id,
                "thread_id": context.thread_id,
                "turn_id": context.turn_id,
                **fields,
            }
        setattr(record, _RESERVED, fields)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "scope": record.name.removeprefix(f"{_ROOT_NAME}."),
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, _RESERVED, {}))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ScopedLogger:
    """``log.info("msg", key=value)``: keyword fields, redacted, with ``err=`` serialised safely."""

    def __init__(self, scope: str) -> None:
        self._logger = logging.getLogger(f"{_ROOT_NAME}.{scope}")
        self.scope = scope

    def _log(self, level: int, msg: str, fields: dict[str, Any]) -> None:
        if not self._logger.isEnabledFor(level):
            return
        clean: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "err":
                clean["err"] = serialize_error_safely(value)
            elif is_redacted_key(key):
                clean[key] = REDACTED
            else:
                clean[key] = value
        self._logger.log(level, msg, extra={_RESERVED: clean})

    def debug(self, msg: str, **fields: Any) -> None:
        self._log(logging.DEBUG, msg, fields)

    def info(self, msg: str, **fields: Any) -> None:
        self._log(logging.INFO, msg, fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._log(logging.WARNING, msg, fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._log(logging.ERROR, msg, fields)


def create_logger(scope: str) -> ScopedLogger:
    return ScopedLogger(scope)


def configure_logging(
    level: str = "INFO",
    *,
    file_enabled: bool = False,
    log_dir: Path | None = None,
    keep_days: int = 14,
) -> None:
    """Install the handlers on the ``pema`` logger. Call once at process start.

    Console at ``level``; file (daily rotation, ``keep_days`` files) at DEBUG when ``file_enabled``.
    The root level of the ``pema`` logger is as low as the lowest handler so debug lines are not
    blocked before the file handler sees them.
    """
    root = logging.getLogger(_ROOT_NAME)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for existing in list(root.filters):
        root.removeFilter(existing)

    console_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(JsonFormatter())
    console.addFilter(_TurnContextFilter())
    root.addHandler(console)

    lowest = console_level
    if file_enabled and log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / "bot.log", when="midnight", backupCount=keep_days, encoding="utf-8", utc=True
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(_TurnContextFilter())
        root.addHandler(file_handler)
        lowest = logging.DEBUG

    root.setLevel(lowest)
    root.propagate = False
