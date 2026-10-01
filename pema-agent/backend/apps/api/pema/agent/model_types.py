# ported from: none (replaces the type vocabulary of the Vercel AI SDK ``ai`` package used by src/agent)
"""The shapes the agent engine passes around, in place of the Vercel AI SDK types.

zalo-agent talks to ``ai`` (``ModelMessage``, ``StepResult``, ``streamText`` ...). The port replaces the SDK
by a hand-written tool loop (PLAN-AI01 section 3), so the few SDK shapes the original code READS are kept
here, in Python naming, and every ported module imports them from this one file:

* ``ModelMessage``: a plain ``dict`` in the SDK's own shape, so the ported pure modules (token estimate,
  context trimming, history conversion) keep working on the same structure as the original and the
  translated tests can build messages as literals::

      {"role": "system" | "user" | "assistant" | "tool", "content": str | list[part]}
      text part        {"type": "text", "text": str}
      image/file part  {"type": "file", "data": <base64>, "mediaType": "image/jpeg"}
      reasoning part   {"type": "reasoning", "text": str}
      tool call        {"type": "tool-call", "toolCallId": str, "toolName": str, "input": dict}
      tool result      {"type": "tool-result", "toolCallId": str, "toolName": str,
                        "output": {"type": "text" | "json" | "error-text", "value": ...}}

  The keys keep the SDK's camelCase because they ARE the wire shape of the message list, not Python API.
* ``RawStep`` (+ ``ToolCallPart``, ``ToolResultPart``, ``StepContentPart``, ``ModelUsage``): what the loop
  reads after every step (``onStepFinish`` of the original): the guard counts from it, the observer logs
  from it, ``summarize_step`` turns it into the stored ``StepTrace``.
* ``ChatModel`` / ``ModelRequest`` / ``ModelCompletion``: ONE model call. The SDK's ``LanguageModel`` +
  ``doStream`` become ``ChatModel.complete``. The provider adapters (``pema.agent.providers``) stream
  internally and hand back a finished completion, which is what ``stream-text-result.ts`` achieved for the
  original (stream on the wire because of the 100 s first-byte limit of the proxy, never streamed to Zalo).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

type ModelMessage = dict[str, Any]

type ProviderOptions = dict[str, dict[str, Any]]
"""``providerOptions`` of the SDK: ``{namespace: {key: json}}`` (see ``reasoning_options``)."""


@dataclass(frozen=True)
class ModelUsage:
    """Token usage of ONE model call, flattened the way ``result.totalUsage`` is in the SDK (``None`` = the
    provider did not report the field; ``0`` is a real zero)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    def plus(self, other: ModelUsage) -> ModelUsage:
        """Field-wise sum; a field stays ``None`` only when neither side reported it."""

        def add(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return ModelUsage(
            input_tokens=add(self.input_tokens, other.input_tokens),
            output_tokens=add(self.output_tokens, other.output_tokens),
            total_tokens=add(self.total_tokens, other.total_tokens),
            reasoning_tokens=add(self.reasoning_tokens, other.reasoning_tokens),
            cache_read_tokens=add(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=add(self.cache_write_tokens, other.cache_write_tokens),
        )


@dataclass
class ToolCallPart:
    tool_call_id: str = ""
    tool_name: str = ""
    input: Any = None
    invalid_input: str | None = None
    """Set by an adapter when the arguments were not valid JSON: the loop answers the model with an error
    result (the SDK's ``InvalidToolInputError``) instead of calling the tool."""
    provider_options: dict[str, Any] | None = None
    """Vendor data that MUST travel with the call into the next request (Gemini 3's ``thoughtSignature``:
    ``{"google": {"thoughtSignature": ...}}``). Copied into the ``tool-call`` part of the assistant
    message."""


@dataclass
class ToolResultPart:
    tool_call_id: str = ""
    tool_name: str = ""
    input: Any = None
    output: Any = None


@dataclass
class StepContentPart:
    """One raw part of a step. A tool that RAISED lives here as ``type == "tool-error"`` and NEVER in
    ``tool_results`` (the SDK getter only filters ``type == "tool-result"``); see ``agent_step_trace``."""

    type: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    input: Any = None
    error: Any = None
    text: str | None = None


@dataclass
class RawStep:
    """Minimal shape of an SDK ``StepResult`` that the ported code reads (all fields optional, so tests build
    partial steps like the original ones did).

    ``step_number`` is 0-based exactly like the SDK; ``summarize_step`` converts to the 1-based number that
    log, DB and UI show.
    """

    step_number: int = 0
    text: str = ""
    reasoning_text: str = ""
    tool_calls: list[ToolCallPart] = field(default_factory=list[ToolCallPart])
    tool_results: list[ToolResultPart] = field(default_factory=list[ToolResultPart])
    content: list[StepContentPart] = field(default_factory=list[StepContentPart])
    finish_reason: str = ""
    warnings: list[Any] = field(default_factory=list[Any])
    usage: ModelUsage | None = None
    response_messages: list[ModelMessage] = field(default_factory=list[ModelMessage])
    """Assistant (+ tool) messages this step added to the conversation (``response.messages`` of the SDK)."""


@dataclass(frozen=True)
class ToolSchema:
    """One tool as the model sees it (OpenAI-style function)."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass
class ModelRequest:
    """Everything ONE model call needs. ``tools`` empty = no tools offered (the wrap-up call)."""

    system: str
    messages: list[ModelMessage]
    tools: list[ToolSchema] = field(default_factory=list[ToolSchema])
    max_output_tokens: int | None = None
    provider_options: ProviderOptions | None = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    """Extra HTTP headers (``x-session-id`` for router prompt caching, see ``cache_session_id``)."""
    timeout_s: float | None = None


@dataclass
class ModelCompletion:
    """The finished answer of one model call (what a streamed ``doStream`` aggregates into)."""

    text: str = ""
    reasoning_text: str = ""
    tool_calls: list[ToolCallPart] = field(default_factory=list[ToolCallPart])
    finish_reason: str = "stop"
    usage: ModelUsage = field(default_factory=ModelUsage)
    warnings: list[Any] = field(default_factory=list[Any])
    model_id: str | None = None
    """The model that REALLY answered (a router may route elsewhere silently)."""
    reasoning_parts: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    """Reasoning parts the next request must carry back (Anthropic thinking blocks with their signature:
    ``{"type": "reasoning", "text": ..., "providerOptions": {"anthropic": {"signature": ...}}}``). The loop
    puts them FIRST in the assistant message; adapters that do not need them ignore them."""


class ChatModel(Protocol):
    """Replaces the SDK's ``LanguageModel``. Adapters raise a provider exception (``ProviderCallError`` or
    the SDK's own; ``provider_error_classifier`` reads both by duck typing) and never retry: the retry
    semantics (``maxRetries``) live in the loop so fake models exercise them too."""

    @property
    def model_id(self) -> str: ...

    async def complete(self, request: ModelRequest) -> ModelCompletion: ...
