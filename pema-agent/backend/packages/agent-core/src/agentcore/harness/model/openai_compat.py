"""Adapter for any endpoint that speaks the OpenAI Chat Completions API (OpenAI, OpenRouter, LiteLLM, vLLM,
Ollama...).

It always streams and assembles one result: a proxy that has to buffer a long non-streamed answer can drop the
connection before the first byte arrives. ``include_usage`` is requested because some gateways report token
usage only when asked.

DeepSeek returns its chain of thought as ``reasoning_content``. It is kept as a ``ThinkingBlock`` and sent
back on later requests, which DeepSeek requires whenever the request carries tools (otherwise it answers 400).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any, Final, cast
from urllib.parse import urlparse

import openai
from openai import AsyncOpenAI, omit
from openai.types import CompletionUsage
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

from agentcore.harness.model.errors import (
    ModelConfigError,
    ModelError,
    ModelErrorKind,
    mentions_context_overflow,
    retry_after_seconds,
    shorten,
)
from agentcore.harness.model.reasoning import OpenAIDialect, openai_reasoning
from agentcore.harness.model.types import AssistantResult, LlmRequest, StopReason, StreamSink
from agentcore.messages import Block, Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, Usage

DEEPSEEK: Final = "deepseek"

_FINISH_REASONS: Final[dict[str, StopReason]] = {
    "stop": "end",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
}

_ARGS_OBJECT: Final = TypeAdapter(dict[str, Any])


class OpenAICompatConfig(BaseModel):
    model: str
    api_key: str
    base_url: str | None = None
    timeout_s: float = 120.0
    """Longest wait for the next piece of the stream; a stalled stream fails as ``transient``."""
    connect_timeout_s: float = 10.0
    max_retries: int = 0
    """Retries are the turn loop's (``RetryPolicy``), so each one shows in the trace."""
    dialect: OpenAIDialect | None = None
    """None: ``deepseek`` for a DeepSeek host, ``openai`` otherwise."""

    def resolved_dialect(self) -> OpenAIDialect:
        if self.dialect is not None:
            return self.dialect
        host = urlparse(self.base_url or "").hostname or ""
        return "deepseek" if host == "deepseek.com" or host.endswith(".deepseek.com") else "openai"


class OpenAICompatModel:
    def __init__(self, config: OpenAICompatConfig, *, client: AsyncOpenAI | None = None) -> None:
        if not config.model.strip():
            raise ModelConfigError("model", "No model is configured.")
        if not config.api_key.strip():
            raise ModelConfigError("api_key", "No API key is configured for the model.")
        self._config = config
        self._dialect: OpenAIDialect = config.resolved_dialect()
        self._client = client or AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=openai.Timeout(config.timeout_s, connect=config.connect_timeout_s),
            max_retries=config.max_retries,
        )

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        tools = to_openai_tools(request)
        reasoning = openai_reasoning(request.reasoning, self._dialect)
        try:
            stream = await self._client.chat.completions.create(
                model=self._config.model,
                messages=to_openai_messages(request, dialect=self._dialect),
                tools=tools or omit,
                max_tokens=request.max_output_tokens,
                reasoning_effort=reasoning.effort or omit,
                extra_body=reasoning.extra_body,
                stream=True,
                stream_options={"include_usage": True},
            )
            return await assemble_stream(stream, sink=sink, reasoning_provider=self._dialect)
        except openai.APIError as err:
            raise classify_openai_error(err) from err


def to_openai_messages(
    request: LlmRequest, *, dialect: OpenAIDialect = "openai"
) -> list[ChatCompletionMessageParam]:
    out: list[ChatCompletionMessageParam] = []
    if request.system:
        out.append({"role": "system", "content": request.system})
    for message in request.messages:
        if message.role == "user":
            out.append({"role": "user", "content": message.text()})
        elif message.role == "assistant":
            out.append(_assistant_param(message, dialect))
        else:
            out.extend(_tool_params(message))
    return out


def _assistant_param(message: Message, dialect: OpenAIDialect) -> ChatCompletionAssistantMessageParam:
    param: dict[str, Any] = {"role": "assistant", "content": message.text() or None}
    tool_calls = [_tool_call_param(use) for use in message.tool_uses()]
    if tool_calls:
        param["tool_calls"] = tool_calls
    # Chat Completions has no field for reasoning; DeepSeek adds its own and wants its reasoning back.
    reasoning = "".join(
        b.text for b in message.blocks if isinstance(b, ThinkingBlock) and b.provider == DEEPSEEK
    )
    if dialect == "deepseek" and reasoning:
        param["reasoning_content"] = reasoning
    return cast(ChatCompletionAssistantMessageParam, param)


def _tool_call_param(use: ToolUseBlock) -> ChatCompletionMessageFunctionToolCallParam:
    arguments = use.raw_args if use.raw_args is not None else json.dumps(use.args, ensure_ascii=False)
    return {"id": use.id, "type": "function", "function": {"name": use.name, "arguments": arguments}}


def _tool_params(message: Message) -> list[ChatCompletionToolMessageParam]:
    return [
        {"role": "tool", "tool_call_id": block.tool_use_id, "content": block.content}
        for block in message.blocks
        if isinstance(block, ToolResultBlock)
    ]


def to_openai_tools(request: LlmRequest) -> list[ChatCompletionFunctionToolParam]:
    return [
        {
            "type": "function",
            "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
        }
        for tool in request.tools
    ]


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


async def assemble_stream(
    chunks: AsyncIterable[ChatCompletionChunk],
    *,
    sink: StreamSink | None = None,
    reasoning_provider: str | None = None,
) -> AssistantResult:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    partial_calls: dict[int, _PartialCall] = {}
    finish_reason: str | None = None
    usage = Usage()

    async for chunk in chunks:
        if chunk.usage is not None:
            usage = _usage(chunk.usage)
        for choice in chunk.choices:
            delta = choice.delta
            reasoning = getattr(delta, "reasoning_content", None)
            if isinstance(reasoning, str) and reasoning:
                reasoning_parts.append(reasoning)
                if sink is not None:
                    sink.thinking(reasoning)
            if delta.content:
                text_parts.append(delta.content)
                if sink is not None:
                    sink.text(delta.content)
            for part in delta.tool_calls or []:
                call = partial_calls.setdefault(part.index, _PartialCall())
                if part.id and not call.id:
                    call.id = part.id
                if part.function is not None:
                    # Some gateways repeat the name in every chunk; the first one is kept.
                    if part.function.name and not call.name:
                        call.name = part.function.name
                    if part.function.arguments:
                        call.arguments += part.function.arguments
            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

    blocks: list[Block] = []
    reasoning = "".join(reasoning_parts)
    if reasoning:
        blocks.append(ThinkingBlock(text=reasoning, provider=reasoning_provider))
    text = "".join(text_parts)
    if text:
        blocks.append(TextBlock(text=text))
    blocks.extend(_tool_use_block(index, partial_calls[index]) for index in sorted(partial_calls))
    if not text and not partial_calls:
        raise ModelError("empty_response", "The model returned neither text nor a tool call.")

    stop_reason: StopReason = (
        "tool_use" if partial_calls else _FINISH_REASONS.get(finish_reason or "", "other")
    )
    message = Message(role="assistant", blocks=blocks, usage=usage)
    return AssistantResult(message=message, stop_reason=stop_reason)


def _usage(raw: CompletionUsage) -> Usage:
    cached = raw.prompt_tokens_details.cached_tokens if raw.prompt_tokens_details else None
    if cached is None:
        # DeepSeek reports cache hits in its own field.
        hit = (raw.model_extra or {}).get("prompt_cache_hit_tokens")
        cached = hit if isinstance(hit, int) else 0
    reasoning = raw.completion_tokens_details.reasoning_tokens if raw.completion_tokens_details else None
    return Usage(
        input_tokens=raw.prompt_tokens,
        output_tokens=raw.completion_tokens,
        cache_read_tokens=cached or 0,
        reasoning_tokens=reasoning or 0,
    )


def _tool_use_block(index: int, call: _PartialCall) -> ToolUseBlock:
    call_id = call.id or f"call_{index}"
    if not call.arguments.strip():
        return ToolUseBlock(id=call_id, name=call.name)
    try:
        args = _ARGS_OBJECT.validate_json(call.arguments)
    except ValidationError:
        return ToolUseBlock(id=call_id, name=call.name, raw_args=call.arguments)
    return ToolUseBlock(id=call_id, name=call.name, args=args)


def classify_openai_error(err: openai.APIError) -> ModelError:
    kind = _error_kind(err)
    retry_after_s = None
    if kind == "rate_limit" and isinstance(err, openai.APIStatusError):
        retry_after_s = retry_after_seconds(err.response.headers.get("retry-after"))
    message = f"{type(err).__name__}: {shorten(err.message)}"
    return ModelError(kind, message, retry_after_s=retry_after_s)


def _error_kind(err: openai.APIError) -> ModelErrorKind:
    if isinstance(err, openai.AuthenticationError | openai.PermissionDeniedError):
        return "auth"
    if isinstance(err, openai.RateLimitError):
        return "rate_limit"
    if isinstance(err, openai.APIConnectionError):
        return "transient"
    if isinstance(err, openai.APIStatusError):
        if err.status_code >= 500:
            return "transient"
        if 400 <= err.status_code < 500 and mentions_context_overflow(err.message):
            return "context_overflow"
    return "unknown"
