# ported from: src/agent/llm-provider.ts (the ``openai-compatible`` branch)
"""``ChatModel`` over the official ``openai`` SDK against any OpenAI-compatible endpoint (Ollama,
llama-server, vLLM, LiteLLM, OpenRouter, a router such as 9Router).

Forced deviations from zalo-agent:

* Vercel ``createOpenAICompatible`` becomes ``AsyncOpenAI``; ``includeUsage: true`` becomes
  ``stream_options={"include_usage": True}``. The original comment stays true: the agent turn goes through the
  STREAMING path (a non-stream request makes a proxy gather the whole answer before the first byte and a CDN
  in front of it cuts the connection at 100 s) and a provider that only reports usage when asked would
  otherwise report 0 for every token of the bot (wrong log, wrong usage table, the token ceiling useless).
  ``complete`` reads the stream to the end and returns a finished ``ModelCompletion``; nothing is streamed to
  the channel.
* ``http_client`` is typed ``Any``: recent ``openai`` releases are built on the ``httpx2`` fork, older ones on
  ``httpx``; the adapter only needs the SDK's own exception types (the SDK wraps every transport error).
* ``max_retries=0`` on the client: the retry semantics (``maxRetries``) live in ``agent_loop`` so a fake model
  exercises them too. SDK exceptions become ``ProviderCallError`` here, so no SDK type leaves the adapter.
* The reasoning option ``{"llmRouter": {"reasoningEffort": ...}}`` (``reasoning_options``) becomes the
  standard ``reasoning_effort`` request field.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

import openai

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
    parse_tool_arguments,
    tool_output_text,
)
from pema.agent.reasoning_options import ROUTER_PROVIDER_OPTIONS_KEY

_FINISH_REASONS = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool-calls",
    "function_call": "tool-calls",
    "content_filter": "content-filter",
}


def to_openai_messages(
    system: str, messages: Sequence[ModelMessage]
) -> tuple[list[dict[str, Any]], list[str]]:
    """``system`` + SDK-shaped messages -> OpenAI chat messages. Returns ``(messages, warnings)``."""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    if system:
        out.append({"role": "system", "content": system})
    for message in messages:
        role = message.get("role")
        parts = content_parts(message)
        if role == "system":
            out.append({"role": "system", "content": "".join(str(p.get("text", "")) for p in parts)})
        elif role == "user":
            out.append(_user_message(parts, warnings))
        elif role == "assistant":
            out.append(_assistant_message(parts))
        elif role == "tool":
            for part in parts:
                if part.get("type") != "tool-result":
                    continue
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(part.get("toolCallId", "")),
                        "content": tool_output_text(part.get("output")),
                    }
                )
    return out, warnings


def _user_message(parts: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
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
            url = f"data:{media_type};base64,{part.get('data') or part.get('image') or ''}"
            blocks.append({"type": "image_url", "image_url": {"url": url}})
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return {"role": "user", "content": blocks[0]["text"]}
    return {"role": "user", "content": blocks}


def _assistant_message(parts: list[dict[str, Any]]) -> dict[str, Any]:
    text = "".join(str(p.get("text", "")) for p in parts if p.get("type") == "text")
    tool_calls = [
        {
            "id": str(p.get("toolCallId", "")),
            "type": "function",
            "function": {
                "name": str(p.get("toolName", "")),
                "arguments": json.dumps(p.get("input") or {}, ensure_ascii=False),
            },
        }
        for p in parts
        if p.get("type") == "tool-call"
    ]
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def provider_error_from(exc: Exception) -> ProviderCallError:
    """Convert an ``openai`` or ``httpx`` exception to ``ProviderCallError`` (the original stays as cause)."""
    if isinstance(exc, openai.APIStatusError):
        headers = dict(exc.response.headers.items())
        error = ProviderCallError(
            str(exc.message),
            status_code=exc.status_code,
            response_headers=headers,
            response_body=_body_text(exc),
            url=str(exc.request.url),
        )
    elif isinstance(exc, openai.APITimeoutError):
        error = ProviderCallError("request timed out", is_retryable=True)
    elif isinstance(exc, openai.APIConnectionError):
        error = ProviderCallError(f"connection error: {type(exc).__name__}", is_retryable=True)
    else:
        raise exc
    error.__cause__ = exc
    return error


def _body_text(exc: openai.APIStatusError) -> str | None:
    body = exc.body
    if body is None:
        return None
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class OpenAICompatibleModel:
    """One configured endpoint + model. Cheap to build: ``resolve_language_model`` builds one per turn."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        headers: dict[str, str] | None = None,
        http_client: Any | None = None,
    ) -> None:
        self._model = model
        self._headers = dict(headers or {})
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            max_retries=0,
            default_headers=self._headers or None,
            http_client=http_client,
        )

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        messages, warnings = to_openai_messages(request.system, request.messages)
        params: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": dict(t.parameters),
                    },
                }
                for t in request.tools
            ]
        if request.max_output_tokens:
            params["max_tokens"] = request.max_output_tokens
        effort = (request.provider_options or {}).get(ROUTER_PROVIDER_OPTIONS_KEY, {}).get("reasoningEffort")
        if isinstance(effort, str):
            params["reasoning_effort"] = effort
        if request.headers:
            params["extra_headers"] = dict(request.headers)
        if request.timeout_s:
            params["timeout"] = request.timeout_s

        try:
            stream = await cast("Any", self._client.chat.completions).create(**params)
            return await _aggregate(stream, self._model, warnings)
        except openai.OpenAIError as exc:
            raise provider_error_from(exc) from exc


def _get(obj: object, name: str) -> Any:
    """Attribute of an SDK chunk object (pydantic models with extras), ``None`` when absent."""
    return getattr(obj, name, None)


def _items(obj: object, name: str) -> list[Any]:
    value = _get(obj, name)
    return list(value) if value else []


async def _aggregate(stream: Any, requested_model: str, warnings: list[str]) -> ModelCompletion:
    """Read the whole chunk stream into one ``ModelCompletion``."""
    text: list[str] = []
    reasoning: list[str] = []
    calls: dict[int, dict[str, str]] = {}
    finish = ""
    usage = ModelUsage()
    model_id: str | None = None

    chunk: Any
    async for chunk in stream:
        model_id = _get(chunk, "model") or model_id
        chunk_usage = _get(chunk, "usage")
        if chunk_usage is not None:
            usage = _usage_of(chunk_usage)
        for choice in _items(chunk, "choices"):
            delta = _get(choice, "delta")
            if delta is not None:
                content = _get(delta, "content")
                if content:
                    text.append(str(content))
                # DeepSeek-style `reasoning_content` (or the `reasoning` spelling of some routers): a pydantic
                # extra of the SDK model, so read it by name.
                piece = _get(delta, "reasoning_content") or _get(delta, "reasoning")
                if isinstance(piece, str) and piece:
                    reasoning.append(piece)
                for tc in _items(delta, "tool_calls"):
                    slot = calls.setdefault(int(_get(tc, "index") or 0), {"id": "", "name": "", "args": ""})
                    if _get(tc, "id"):
                        slot["id"] = str(_get(tc, "id"))
                    fn = _get(tc, "function")
                    if fn is not None:
                        slot["name"] += str(_get(fn, "name") or "")
                        slot["args"] += str(_get(fn, "arguments") or "")
            if _get(choice, "finish_reason"):
                finish = str(_get(choice, "finish_reason"))

    tool_calls: list[ToolCallPart] = []
    for index in sorted(calls):
        slot = calls[index]
        parsed, invalid = parse_tool_arguments(slot["args"])
        tool_calls.append(
            ToolCallPart(
                tool_call_id=slot["id"] or f"call-{index}",
                tool_name=slot["name"],
                input=parsed,
                invalid_input=invalid,
            )
        )
    finish_reason = _FINISH_REASONS.get(finish, "tool-calls" if tool_calls else (finish or "stop"))
    if tool_calls and finish_reason == "stop":
        finish_reason = "tool-calls"
    return ModelCompletion(
        text="".join(text),
        reasoning_text="".join(reasoning),
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
        warnings=list(warnings),
        model_id=model_id or requested_model,
    )


def _usage_of(raw: Any) -> ModelUsage:
    prompt = _int_or_none(_get(raw, "prompt_tokens"))
    completion = _int_or_none(_get(raw, "completion_tokens"))
    total = _int_or_none(_get(raw, "total_tokens"))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    prompt_details = _get(raw, "prompt_tokens_details")
    completion_details = _get(raw, "completion_tokens_details")
    return ModelUsage(
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=total,
        reasoning_tokens=_int_or_none(_get(completion_details, "reasoning_tokens")),
        cache_read_tokens=_int_or_none(_get(prompt_details, "cached_tokens")),
    )
