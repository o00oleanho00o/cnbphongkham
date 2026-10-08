"""Adapter for any endpoint that speaks the OpenAI Chat Completions API (OpenAI, OpenRouter, LiteLLM, vLLM,
Ollama...).

It always streams and assembles one result: a proxy that has to buffer a long non-streamed answer can drop the
connection before the first byte arrives. ``include_usage`` is requested because some gateways report token
usage only when asked.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Final

import openai
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

from agentcore.harness.model.errors import ModelConfigError, ModelError, ModelErrorKind
from agentcore.harness.model.types import AssistantResult, LlmRequest, StopReason
from agentcore.messages import Block, Message, TextBlock, ToolResultBlock, ToolUseBlock, Usage

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
    max_retries: int = 2


class OpenAICompatModel:
    def __init__(self, config: OpenAICompatConfig, *, client: AsyncOpenAI | None = None) -> None:
        if not config.model.strip():
            raise ModelConfigError("model", "No model is configured: set LLM_MODEL or the profile's model.")
        if not config.api_key.strip():
            raise ModelConfigError("api_key", "No API key is configured: set LLM_API_KEY.")
        self._config = config
        self._client = client or AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=config.timeout_s,
            max_retries=config.max_retries,
        )

    async def complete(self, request: LlmRequest) -> AssistantResult:
        messages = to_openai_messages(request)
        tools = to_openai_tools(request)
        try:
            if tools:
                stream = await self._client.chat.completions.create(
                    model=self._config.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=request.max_output_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
            else:
                stream = await self._client.chat.completions.create(
                    model=self._config.model,
                    messages=messages,
                    max_tokens=request.max_output_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
            return await assemble_stream(stream)
        except openai.APIError as err:
            raise classify_openai_error(err) from err


def to_openai_messages(request: LlmRequest) -> list[ChatCompletionMessageParam]:
    out: list[ChatCompletionMessageParam] = []
    if request.system:
        out.append({"role": "system", "content": request.system})
    for message in request.messages:
        if message.role == "user":
            out.append({"role": "user", "content": message.text()})
        elif message.role == "assistant":
            out.append(_assistant_param(message))
        else:
            out.extend(_tool_params(message))
    return out


def _assistant_param(message: Message) -> ChatCompletionAssistantMessageParam:
    # Thinking blocks are not sent: Chat Completions has no field for them.
    param: ChatCompletionAssistantMessageParam = {"role": "assistant", "content": message.text() or None}
    tool_calls = [_tool_call_param(use) for use in message.tool_uses()]
    if tool_calls:
        param["tool_calls"] = tool_calls
    return param


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


async def assemble_stream(chunks: AsyncIterable[ChatCompletionChunk]) -> AssistantResult:
    text_parts: list[str] = []
    partial_calls: dict[int, _PartialCall] = {}
    finish_reason: str | None = None
    usage = Usage()

    async for chunk in chunks:
        if chunk.usage is not None:
            usage = Usage(input_tokens=chunk.usage.prompt_tokens, output_tokens=chunk.usage.completion_tokens)
        for choice in chunk.choices:
            delta = choice.delta
            if delta.content:
                text_parts.append(delta.content)
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
    text = "".join(text_parts)
    if text:
        blocks.append(TextBlock(text=text))
    blocks.extend(_tool_use_block(index, partial_calls[index]) for index in sorted(partial_calls))
    if not blocks:
        raise ModelError("empty_response", "The model returned neither text nor a tool call.")

    stop_reason: StopReason = (
        "tool_use" if partial_calls else _FINISH_REASONS.get(finish_reason or "", "other")
    )
    message = Message(role="assistant", blocks=blocks, usage=usage)
    return AssistantResult(message=message, stop_reason=stop_reason)


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
    retry_after_s = _retry_after_s(err) if kind == "rate_limit" else None
    message = f"{type(err).__name__}: {_shorten(err.message)}"
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
        if 400 <= err.status_code < 500 and _mentions_context_overflow(err.message):
            return "context_overflow"
    return "unknown"


def _mentions_context_overflow(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CONTEXT_OVERFLOW_MARKERS)


def _retry_after_s(err: openai.APIError) -> float | None:
    if not isinstance(err, openai.APIStatusError):
        return None
    header = err.response.headers.get("retry-after")
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


def _shorten(text: str) -> str:
    return text if len(text) <= ERROR_MESSAGE_LIMIT else text[:ERROR_MESSAGE_LIMIT] + "..."
