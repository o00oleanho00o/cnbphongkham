"""Adapter for the Anthropic Messages API. Provisional: built and tested against fakes only, no live key yet.

The frozen system prompt, the tool list and the newest message carry cache breakpoints, so the provider can
reuse the prompt prefix between calls. Tool results travel in a user message, merged with the context block
that may follow them. Thinking blocks go back only when Anthropic produced them, with their signature.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, cast

import anthropic
from anthropic import AsyncAnthropic, omit
from anthropic.lib.streaming import TextEvent
from anthropic.types import Message as AnthropicMessage
from anthropic.types import (
    MessageParam,
    RawContentBlockDeltaEvent,
    TextBlockParam,
    ThinkingConfigParam,
    ThinkingDelta,
    ToolParam,
)
from anthropic.types import RedactedThinkingBlock as AnthropicRedactedThinking
from anthropic.types import TextBlock as AnthropicText
from anthropic.types import ThinkingBlock as AnthropicThinking
from anthropic.types import ToolUseBlock as AnthropicToolUse
from pydantic import BaseModel

from agentcore.harness.model.errors import (
    ModelConfigError,
    ModelError,
    ModelErrorKind,
    mentions_context_overflow,
    retry_after_seconds,
    shorten,
)
from agentcore.harness.model.reasoning import AnthropicReasoning, anthropic_reasoning
from agentcore.harness.model.types import AssistantResult, LlmRequest, StopReason, StreamSink
from agentcore.messages import Block, Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, Usage

ANTHROPIC: Final = "anthropic"
EMPTY_REPLY: Final = "(no reply)"
_EPHEMERAL: Final = {"type": "ephemeral"}
_STOP_REASONS: Final[dict[str, StopReason]] = {
    "end_turn": "end",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
}


class AnthropicConfig(BaseModel):
    model: str
    api_key: str
    base_url: str | None = None
    timeout_s: float = 120.0
    """Longest wait for the next piece of the stream; a stalled stream fails as ``transient``."""
    connect_timeout_s: float = 10.0
    max_retries: int = 0
    """Retries are the turn loop's (``RetryPolicy``), so each one shows in the trace."""


class AnthropicModel:
    def __init__(self, config: AnthropicConfig, *, client: AsyncAnthropic | None = None) -> None:
        if not config.model.strip():
            raise ModelConfigError("model", "No model is configured: set LLM_MODEL or the profile's model.")
        if not config.api_key.strip():
            raise ModelConfigError("api_key", "No API key is configured: set LLM_API_KEY.")
        self._config = config
        self._client = client or AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=anthropic.Timeout(config.timeout_s, connect=config.connect_timeout_s),
            max_retries=config.max_retries,
        )

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        reasoning = anthropic_reasoning(request.reasoning)
        tools = to_anthropic_tools(request)
        try:
            async with self._client.messages.stream(
                model=self._config.model,
                max_tokens=request.max_output_tokens,
                system=to_anthropic_system(request) or omit,
                messages=to_anthropic_messages(request.messages),
                tools=tools or omit,
                thinking=_thinking(reasoning) or omit,
                output_config={"effort": reasoning.effort} if reasoning.effort else omit,
            ) as stream:
                async for event in stream:
                    if sink is None:
                        continue
                    if isinstance(event, TextEvent):
                        sink.text(event.text)
                    elif isinstance(event, RawContentBlockDeltaEvent) and isinstance(
                        event.delta, ThinkingDelta
                    ):
                        sink.thinking(event.delta.thinking)
                final = await stream.get_final_message()
        except anthropic.APIError as err:
            raise classify_anthropic_error(err) from err
        return to_result(final)


def _thinking(reasoning: AnthropicReasoning) -> ThinkingConfigParam | None:
    if reasoning.thinking == "adaptive":
        return {"type": "adaptive"}
    if reasoning.thinking == "disabled":
        return {"type": "disabled"}
    return None


def to_anthropic_system(request: LlmRequest) -> list[TextBlockParam]:
    if not request.system:
        return []
    return [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}]


def to_anthropic_tools(request: LlmRequest) -> list[ToolParam]:
    tools: list[ToolParam] = [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in request.tools
    ]
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


def to_anthropic_messages(messages: Sequence[Message]) -> list[MessageParam]:
    """Tool results become user content; consecutive same-role messages are merged into one."""
    out: list[dict[str, Any]] = []
    for message in messages:
        role = "assistant" if message.role == "assistant" else "user"
        content = _assistant_content(message) if role == "assistant" else _user_content(message)
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(content)
        else:
            out.append({"role": role, "content": content})
    for entry in out:
        if not entry["content"]:
            entry["content"].append({"type": "text", "text": EMPTY_REPLY})
    if out:
        out[-1]["content"][-1]["cache_control"] = dict(_EPHEMERAL)
    return cast(list[MessageParam], out)


def _user_content(message: Message) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in message.blocks:
        if isinstance(block, ToolResultBlock):
            content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.tool_use_id,
                    "content": block.content,
                    "is_error": block.is_error,
                }
            )
        elif isinstance(block, TextBlock) and block.text.strip():
            content.append({"type": "text", "text": block.text})
    return content


def _assistant_content(message: Message) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in message.blocks:
        if isinstance(block, ThinkingBlock) and block.provider == ANTHROPIC:
            if block.redacted_data is not None:
                content.append({"type": "redacted_thinking", "data": block.redacted_data})
            elif block.signature:
                content.append({"type": "thinking", "thinking": block.text, "signature": block.signature})
        elif isinstance(block, TextBlock) and block.text.strip():
            content.append({"type": "text", "text": block.text})
        elif isinstance(block, ToolUseBlock):
            content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.args})
    return content


def to_result(final: AnthropicMessage) -> AssistantResult:
    blocks: list[Block] = []
    for part in final.content:
        if isinstance(part, AnthropicThinking):
            blocks.append(ThinkingBlock(text=part.thinking, signature=part.signature, provider=ANTHROPIC))
        elif isinstance(part, AnthropicRedactedThinking):
            blocks.append(ThinkingBlock(text="", redacted_data=part.data, provider=ANTHROPIC))
        elif isinstance(part, AnthropicText):
            blocks.append(TextBlock(text=part.text))
        elif isinstance(part, AnthropicToolUse):
            blocks.append(ToolUseBlock(id=part.id, name=part.name, args=dict(part.input)))
    has_tools = any(isinstance(b, ToolUseBlock) for b in blocks)
    if not has_tools and not any(isinstance(b, TextBlock) and b.text for b in blocks):
        raise ModelError("empty_response", "The model returned neither text nor a tool call.")
    stop: StopReason = "tool_use" if has_tools else _STOP_REASONS.get(final.stop_reason or "", "other")
    message = Message(role="assistant", blocks=blocks, usage=_usage(final))
    return AssistantResult(message=message, stop_reason=stop)


def _usage(final: AnthropicMessage) -> Usage:
    raw = final.usage
    cache_read = raw.cache_read_input_tokens or 0
    cache_write = raw.cache_creation_input_tokens or 0
    details = raw.output_tokens_details
    return Usage(
        # Anthropic's input_tokens leaves out the cached part.
        input_tokens=raw.input_tokens + cache_read + cache_write,
        output_tokens=raw.output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=(details.thinking_tokens or 0) if details else 0,
    )


def classify_anthropic_error(err: anthropic.APIError) -> ModelError:
    kind = _error_kind(err)
    retry_after_s = None
    if kind == "rate_limit" and isinstance(err, anthropic.APIStatusError):
        retry_after_s = retry_after_seconds(err.response.headers.get("retry-after"))
    return ModelError(kind, f"{type(err).__name__}: {shorten(err.message)}", retry_after_s=retry_after_s)


def _error_kind(err: anthropic.APIError) -> ModelErrorKind:
    if isinstance(err, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "auth"
    if isinstance(err, anthropic.RateLimitError):
        return "rate_limit"
    if isinstance(err, anthropic.RequestTooLargeError):
        return "context_overflow"
    if isinstance(err, anthropic.APIConnectionError):
        return "transient"
    if isinstance(err, anthropic.APIStatusError):
        if err.status_code >= 500:
            return "transient"
        if 400 <= err.status_code < 500 and mentions_context_overflow(err.message):
            return "context_overflow"
    return "unknown"
