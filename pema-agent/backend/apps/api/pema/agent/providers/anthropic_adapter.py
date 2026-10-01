# ported from: src/agent/llm-provider.ts (the ``anthropic`` branch; @ai-sdk/anthropic replaced)
"""``ChatModel`` over the official ``anthropic`` SDK (direct call to the vendor, no router).

Forced deviations from zalo-agent:

* ``createAnthropic`` becomes ``AsyncAnthropic`` with ``max_retries=0`` (the retry semantics live in
  ``agent_loop``); SDK exceptions become ``ProviderCallError``; the call streams and returns the finished
  message (``stream.get_final_message()``), so a long answer never sits on a silent connection.
* Message conversion replaces the one of ``@ai-sdk/anthropic``. As in that converter a ``tool`` message and a
  following ``user`` message are merged into ONE ``user`` turn (``groupIntoBlocks``): that is what makes the
  mid-turn injection safe on this path (a user message right after a tool result does not break the "roles
  must alternate" rule).
* Thinking: ``{"anthropic": {"thinking": ..., "effort": ...}}`` (``reasoning_options``) goes out through
  ``extra_body`` (``thinking`` and ``output_config.effort``) so the adapter does not depend on the SDK knowing
  the newest fields. A thinking block of the answer returns in ``ModelCompletion.reasoning_parts`` with its
  signature and the converter writes it back first in the next assistant turn, as the API demands for a tool
  loop with thinking on.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

import anthropic

from pema.agent.model_types import (
    ModelCompletion,
    ModelMessage,
    ModelRequest,
    ModelUsage,
    ToolCallPart,
)
from pema.agent.providers.errors import ProviderCallError
from pema.agent.providers.messages import (
    content_parts,
    tool_output_is_error,
    tool_output_text,
)

DEFAULT_MAX_OUTPUT_TOKENS = 16_384
"""The API requires ``max_tokens``; the engine always passes ``LLM_MAX_OUTPUT_TOKENS`` (default of the
original 16 384), this is only the floor for a direct call without one."""

_STOP_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool-calls",
    "max_tokens": "length",
    "refusal": "content-filter",
}


def to_anthropic_messages(messages: Sequence[ModelMessage]) -> tuple[list[dict[str, Any]], list[str]]:
    """SDK-shaped messages -> Anthropic ``messages`` (system is separate). Returns ``(messages, warnings)``"""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for message in messages:
        role = message.get("role")
        parts = content_parts(message)
        if role in {"user", "tool"}:
            blocks = _user_blocks(parts, warnings)
            if out and out[-1]["role"] == "user":
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": "user", "content": blocks})
        elif role == "assistant":
            out.append({"role": "assistant", "content": _assistant_blocks(parts)})
    return out, warnings


def _user_blocks(parts: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in parts:
        kind = part.get("type")
        if kind == "text":
            blocks.append({"type": "text", "text": str(part.get("text", ""))})
        elif kind in {"file", "image"}:
            media_type = str(part.get("mediaType") or part.get("mimeType") or "")
            if not media_type.startswith("image/"):
                warnings.append(f"unsupported file part ({media_type or 'unknown type'}) dropped")
                continue
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": str(part.get("data") or part.get("image") or ""),
                    },
                }
            )
        elif kind == "tool-result":
            output = part.get("output")
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": str(part.get("toolCallId", "")),
                "content": tool_output_text(output),
            }
            if tool_output_is_error(output):
                block["is_error"] = True
            blocks.append(block)
    return blocks


def _assistant_blocks(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in parts:
        kind = part.get("type")
        if kind == "reasoning":
            signature = cast("dict[str, Any]", part.get("providerOptions") or {}).get("anthropic", {})
            sig = cast("dict[str, Any]", signature).get("signature")
            if isinstance(sig, str):  # an unsigned thinking block would be rejected by the API: drop it
                blocks.append({"type": "thinking", "thinking": str(part.get("text", "")), "signature": sig})
        elif kind == "text":
            text = str(part.get("text", ""))
            if text:
                blocks.append({"type": "text", "text": text})
        elif kind == "tool-call":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(part.get("toolCallId", "")),
                    "name": str(part.get("toolName", "")),
                    "input": part.get("input") or {},
                }
            )
    return blocks or [{"type": "text", "text": "(empty)"}]


def _body_text(body: object) -> str | None:
    if body is None:
        return None
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)


def provider_error_from(exc: Exception) -> ProviderCallError:
    if isinstance(exc, anthropic.APIStatusError):
        error = ProviderCallError(
            str(exc.message),
            status_code=exc.status_code,
            response_headers=dict(exc.response.headers.items()),
            response_body=_body_text(exc.body),
            url=str(exc.request.url),
        )
    elif isinstance(exc, anthropic.APITimeoutError):
        error = ProviderCallError("request timed out", is_retryable=True)
    elif isinstance(exc, anthropic.APIConnectionError):
        error = ProviderCallError(f"connection error: {type(exc).__name__}", is_retryable=True)
    else:
        raise exc
    error.__cause__ = exc
    return error


class AnthropicModel:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        headers: dict[str, str] | None = None,
        http_client: Any | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=0,
            default_headers=dict(headers or {}) or None,
            http_client=http_client,
            base_url=base_url,
        )

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        messages, warnings = to_anthropic_messages(request.messages)
        params: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
        }
        if request.system:
            params["system"] = request.system
        if request.tools:
            params["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": dict(t.parameters)}
                for t in request.tools
            ]
        options = (request.provider_options or {}).get("anthropic")
        if options:
            body: dict[str, Any] = {}
            if "thinking" in options:
                body["thinking"] = options["thinking"]
            if "effort" in options:
                body["output_config"] = {"effort": options["effort"]}
            params["extra_body"] = body
        if request.headers:
            params["extra_headers"] = dict(request.headers)
        if request.timeout_s:
            params["timeout"] = request.timeout_s

        try:
            async with cast("Any", self._client.messages).stream(**params) as stream:
                final: Any = await stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise provider_error_from(exc) from exc
        return _completion_of(final, self._model, warnings)


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _completion_of(final: Any, requested_model: str, warnings: list[str]) -> ModelCompletion:
    text: list[str] = []
    reasoning: list[str] = []
    reasoning_parts: list[dict[str, Any]] = []
    tool_calls: list[ToolCallPart] = []
    block: Any
    for block in list(getattr(final, "content", None) or []):
        kind = getattr(block, "type", "")
        if kind == "text":
            text.append(str(getattr(block, "text", "")))
        elif kind == "thinking":
            thought = str(getattr(block, "thinking", ""))
            reasoning.append(thought)
            signature = getattr(block, "signature", None)
            if isinstance(signature, str):
                reasoning_parts.append(
                    {
                        "type": "reasoning",
                        "text": thought,
                        "providerOptions": {"anthropic": {"signature": signature}},
                    }
                )
        elif kind == "tool_use":
            args = getattr(block, "input", None)
            tool_calls.append(
                ToolCallPart(
                    tool_call_id=str(getattr(block, "id", "")),
                    tool_name=str(getattr(block, "name", "")),
                    input=args if isinstance(args, dict) else {},
                    invalid_input=None if isinstance(args, dict) else "arguments are not a JSON object",
                )
            )
    raw_usage = getattr(final, "usage", None)
    cache_read = _int_or_none(getattr(raw_usage, "cache_read_input_tokens", None))
    cache_write = _int_or_none(getattr(raw_usage, "cache_creation_input_tokens", None))
    fresh = _int_or_none(getattr(raw_usage, "input_tokens", None))
    output = _int_or_none(getattr(raw_usage, "output_tokens", None))
    # Like @ai-sdk/anthropic: the input total INCLUDES the cache read and write parts.
    total_input = None if fresh is None else fresh + (cache_read or 0) + (cache_write or 0)
    usage = ModelUsage(
        input_tokens=total_input,
        output_tokens=output,
        total_tokens=None if total_input is None or output is None else total_input + output,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )
    stop = str(getattr(final, "stop_reason", "") or "")
    finish = _STOP_REASONS.get(stop, "tool-calls" if tool_calls else (stop or "stop"))
    return ModelCompletion(
        text="".join(text),
        reasoning_text="".join(reasoning),
        tool_calls=tool_calls,
        finish_reason=finish,
        usage=usage,
        warnings=list(warnings),
        model_id=str(getattr(final, "model", "") or requested_model),
        reasoning_parts=reasoning_parts,
    )
