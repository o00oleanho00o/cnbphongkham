# ported from: src/agent/vision-rejection-fallback.ts
"""Trigger condition of the reactive fallback of the agent loop: a turn that carries pixels was rejected by
the provider -> rebuild the input without pixels (describe/blind) and retry. Split from the loop so a pure
test needs no whole agent turn.

Forced deviation: ``APICallError.isInstance`` becomes duck typing over the status code (``ProviderCallError``
or any exception with ``status_code`` / ``statusCode`` / ``status``, read by ``ma_http_cua``); only an
EXCEPTION counts, as only an ``APICallError`` did.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from pema.agent.model_types import ModelMessage
from pema.agent.provider_error_classifier import ma_http_cua


def is_image_rejection_error(err: object) -> bool:
    """The provider REJECTED the request (4xx) - for a turn that carries images the overwhelming likelihood is
    that the model does not accept images (an endpoint outside 9Router does not declare its capability, so
    detection guesses optimistically). NOT counted: 401/403 (wrong key - dropping images would not save it),
    429 (quota - a temporary error), 5xx (the retry of the loop already handles it)."""
    if not isinstance(err, BaseException):
        return False
    status = ma_http_cua(err) or 0
    return 400 <= status < 500 and status not in (401, 403, 429)


def has_image_parts(messages: Sequence[ModelMessage]) -> bool:
    """Does this turn have any image part - the condition for the reactive fallback to dare retry."""
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for part in cast("list[Any]", content):
            if isinstance(part, dict) and cast("dict[str, Any]", part).get("type") == "file":
                return True
    return False
