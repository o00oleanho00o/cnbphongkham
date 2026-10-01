# ported from: src/agent/streaming-model-test-helper.ts (+ the fixtures of run-agent-turn.test.ts)
"""A fake model for tests (no network), and the fixtures that describe ONE answer of the model.

In zalo-agent the helper turned a ``doGenerate`` result into a ``doStream`` result, because the loop went
through
``streamText`` and the SDK's ``MockLanguageModelV4`` only streamed. Here the model seam is
``ChatModel.complete``
(``pema.agent.model_types``), which already returns the finished answer, so what remains of the helper is the
useful part: the FIXTURES (``tra_loi``, ``goi_tool``, ``rong``) that describe one answer of the model as the
cheapest way to read a test, and ``ScriptedModel``, which plays them in order and records every request so a
test can inspect the Nth call (did the wrap-up call carry tools? what was in the prompt?).

Test-only: nothing in production imports this module.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pema.agent.model_types import ModelCompletion, ModelRequest, ModelUsage, ToolCallPart

type Scripted = Callable[[], ModelCompletion | Exception]
"""One scripted step: a callable returning the answer, or an exception to raise (an HTTP error, a crash)."""

KHONG_TOKEN = ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0)
CO_TOKEN = ModelUsage(input_tokens=120, output_tokens=30, total_tokens=150)


def tra_loi(text: str, usage: ModelUsage = CO_TOKEN) -> ModelCompletion:
    """One answer of the model: plain text (empty text = an empty answer)."""
    return ModelCompletion(text=text, finish_reason="stop", usage=usage, model_id="test-model")


def goi_tool(
    tool_name: str = "get_datetime",
    input: dict[str, Any] | None = None,
    *,
    call_id: str = "call-1",
    text: str = "",
    usage: ModelUsage = CO_TOKEN,
) -> ModelCompletion:
    """One answer that calls a tool (``get_datetime`` is a pure tool: running it for real is harmless)."""
    return ModelCompletion(
        text=text,
        tool_calls=[ToolCallPart(tool_call_id=call_id, tool_name=tool_name, input=input or {})],
        finish_reason="tool-calls",
        usage=usage,
        model_id="test-model",
    )


def rong() -> ModelCompletion:
    """Signature of the router glitch: HTTP 200 but empty, 0 tokens."""
    return tra_loi("", KHONG_TOKEN)


@dataclass
class ScriptedModel:
    """Plays ``script`` in order; the LAST element repeats once the list is exhausted (like the original
    mock).

    ``calls`` holds a snapshot of every request; ``count`` is the number of calls made.
    """

    script: Sequence[Scripted]
    calls: list[ModelRequest] = field(default_factory=list[ModelRequest])
    model_id: str = "test-model"

    @property
    def count(self) -> int:
        return len(self.calls)

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        self.calls.append(
            ModelRequest(
                system=request.system,
                messages=list(request.messages),
                tools=list(request.tools),
                max_output_tokens=request.max_output_tokens,
                provider_options=request.provider_options,
                headers=dict(request.headers),
                timeout_s=request.timeout_s,
            )
        )
        step = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        outcome = step()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def prompt_text(call: ModelRequest) -> str:
    """The whole prompt of a call as one string, for substring checks (system first, like ``call.prompt``)."""
    return "\n".join([call.system, *(_content_text(m) for m in call.messages)])


def prompt_tail(call: ModelRequest, n: int) -> str:
    """Only the LAST ``n`` messages: to check the position of the protected tail, not just the presence."""
    return "\n".join(_content_text(m) for m in call.messages[-n:])


def _content_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def tool_keys(call: ModelRequest) -> list[str]:
    return [t.name for t in call.tools]
