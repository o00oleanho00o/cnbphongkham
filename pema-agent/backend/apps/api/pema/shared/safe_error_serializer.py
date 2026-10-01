# ported from: src/shared/safe-error-serializer.ts
"""Reduce an error to a SAFE shape before it is logged.

Why: a default serializer copies every attribute of an exception. An SDK ``APICallError`` carries
``requestBodyValues`` = the whole body sent to the provider, i.e. the system prompt, the entire
conversation and base64 images. Measured in zalo-agent: a fake 429 with a 400-char base64 image grew a
log line from 17 to 1338 chars, system prompt included. With a real 300 KB image every provider 4xx
would put ~400 KB of private data in plaintext in the logs. In the clinic this would be patient
conversation text, so the rule is hard: errors are logged through THIS function only.

An ALLOW list, not a deny list: a later SDK version that adds a new field holding the body would
silently leak under a deny list, not under this one.

Python mapping of the allow list: JS ``statusCode``/``isRetryable``/``responseHeaders`` have the
snake_case names used by the ``openai``/``httpx`` exceptions (``status_code``, ``code``...); both
spellings are kept so the same function serves SDK errors and Node-bridge errors.
"""

from __future__ import annotations

import json
import traceback
from typing import Any, cast

from pydantic import ValidationError

SAFE_FIELDS: tuple[str, ...] = (
    "message",
    "name",
    "code",
    "errno",
    "syscall",
    "statusCode",
    "status_code",
    "url",
    "isRetryable",
    "is_retryable",
    "responseHeaders",
    "response_headers",
)
"""Fields kept: enough to diagnose, never conversation content. ``TRUONG_AN_TOAN``."""

STACK_MAX = 2000
"""A stack of a thousand chars is normal; cut so one log line does not swallow the screen."""

DEPTH_MAX = 3
"""Nest ``cause`` but never go deep forever (an error can reference itself)."""

type SafeError = dict[str, Any]


def serialize_error_safely(err: object, depth: int = 0) -> SafeError:
    if err is None:
        return {"message": "None"}
    if not isinstance(err, BaseException) and not hasattr(err, "__dict__"):
        return {"message": str(err)}

    out: SafeError = {"type": type(err).__name__}

    attrs = getattr(err, "__dict__", {})
    for key in SAFE_FIELDS:
        if key not in attrs:
            continue
        value = attrs[key]
        # Only small primitives; an unknown field could be a huge object.
        out[key] = _safe_json(cast("object", value)) if isinstance(value, dict | list | tuple) else value

    if isinstance(err, BaseException):
        # ``str(err)`` is the message; it is the thing you most need to read. EXCEPT a pydantic
        # ``ValidationError``: its text quotes the offending ``input_value`` (a patient's words, a phone
        # number), so it is reduced to the error types and locations (package G, SEC-05).
        message = _validation_summary(err) or str(err)
        out["message"] = message
        out["type"] = type(err).__name__
        stack = "".join(traceback.format_tb(err.__traceback__)) + f"{type(err).__name__}: {message}"
        if stack.strip():
            out["stack"] = stack if len(stack) <= STACK_MAX else f"{stack[:STACK_MAX]}..."
        cause = err.__cause__ or err.__context__
        if cause is not None and depth < DEPTH_MAX:
            out["cause"] = serialize_error_safely(cause, depth + 1)
    elif "cause" in attrs and depth < DEPTH_MAX:
        out["cause"] = serialize_error_safely(attrs["cause"], depth + 1)

    return out


def _validation_summary(err: BaseException) -> str | None:
    """``N validation error(s): <loc> <type>; ...`` for a pydantic ``ValidationError``, else ``None``."""
    if not isinstance(err, ValidationError):
        return None
    parts = [f"{'.'.join(str(p) for p in e['loc'])} {e['type']}" for e in err.errors(include_input=False)]
    return f"{err.error_count()} validation error(s): " + "; ".join(parts[:10])


def _safe_json(value: object) -> object:
    """Small objects keep their content, big ones only their size."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "[object cannot be stringified]"
    return value if len(text) <= 500 else f"[object {len(text)} chars - elided]"
