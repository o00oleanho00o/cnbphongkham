"""Errors of a model call, classified so the loop knows whether retrying can help."""

from __future__ import annotations

from typing import Literal

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
