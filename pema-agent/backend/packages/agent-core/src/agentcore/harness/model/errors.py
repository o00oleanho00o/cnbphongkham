"""Errors of a model call, classified so the loop knows whether retrying can help."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Final, Literal

MAX_RETRY_AFTER_S: Final = 60.0
ERROR_MESSAGE_LIMIT: Final = 300

# Providers report an over-long prompt as a generic 400; only the message tells it apart.
CONTEXT_OVERFLOW_MARKERS: Final = (
    "context length",
    "context_length",
    "context window",
    "maximum context",
    "too many tokens",
    "prompt is too long",
    "reduce the length",
    "exceeds the maximum",
)

ModelErrorKind = Literal[
    "config",
    "auth",
    "rate_limit",
    "context_overflow",
    "transient",
    "empty_response",
    "unknown",
]


class ModelError(Exception):
    def __init__(self, kind: ModelErrorKind, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.kind: ModelErrorKind = kind
        self.retry_after_s = retry_after_s


class ModelConfigError(ModelError):
    """Configuration is missing, so no request was made and retrying cannot help."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__("config", message)
        self.field = field


def mentions_context_overflow(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CONTEXT_OVERFLOW_MARKERS)


def retry_after_seconds(header: str | None) -> float | None:
    """A ``Retry-After`` value (seconds or an HTTP date), capped at ``MAX_RETRY_AFTER_S``."""
    if header is None:
        return None
    try:
        seconds = float(header)
    except ValueError:
        try:
            when = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - datetime.now(UTC)).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)


def shorten(text: str) -> str:
    return text if len(text) <= ERROR_MESSAGE_LIMIT else text[:ERROR_MESSAGE_LIMIT] + "..."
