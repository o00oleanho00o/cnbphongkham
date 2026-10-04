# ported from: none (replaces the message converters of the three @ai-sdk providers)
"""Shared helpers of the three provider adapters: read the SDK-shaped ``ModelMessage`` parts.

The engine speaks the Vercel ``ModelMessage`` shape (see ``pema.agent.model_types``); each adapter converts it
to its vendor wire format. What is common lives here: normalising ``content`` to a list of parts, turning a
tool-result ``output`` into the string the models read, and decoding tool arguments.
"""

from __future__ import annotations

import json
from typing import Any, cast

from pema.agent.model_types import ModelMessage


def content_parts(message: ModelMessage) -> list[dict[str, Any]]:
    """``content`` of a message as a list of parts (a plain string becomes one text part)."""
    content: object = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        items = cast("list[object]", content)
        return [cast("dict[str, Any]", p) for p in items if isinstance(p, dict)]
    return []


def tool_output_text(output: object) -> str:
    """The text a tool result is shown to the model as: the SDK wrappers ``{"type": "text"|"json", "value"}``
    (also "error-text") are unwrapped, any other value is JSON-encoded."""
    value: object = output
    if isinstance(output, dict):
        wrapper = cast("dict[str, Any]", output)
        if "type" in wrapper and "value" in wrapper:
            value = wrapper["value"]
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def tool_output_is_error(output: object) -> bool:
    if not isinstance(output, dict):
        return False
    return cast("dict[str, Any]", output).get("type") in {"error-text", "error-json"}


def parse_tool_arguments(raw: str) -> tuple[dict[str, Any], str | None]:
    """Decode the JSON arguments a model streamed for a tool call. Returns ``(input, invalid_reason)``: empty
    string means "no arguments" (a tool without parameters); invalid JSON or a non-object is reported so the
    loop answers the model with an error instead of calling the tool (the SDK's ``InvalidToolInputError``)."""
    if not raw.strip():
        return {}, None
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "arguments are not valid JSON"
    if not isinstance(parsed, dict):
        return {}, "arguments are not a JSON object"
    return cast("dict[str, Any]", parsed), None
