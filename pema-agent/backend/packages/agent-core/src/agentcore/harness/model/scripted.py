"""Models that need no provider: ``ScriptedModel`` replays fixed replies (tests), ``EchoModel`` repeats the
user (running the CLI without a key)."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from typing import Any

from agentcore.harness.model.types import AssistantResult, LlmRequest
from agentcore.messages import Block, Message, TextBlock, ToolUseBlock, Usage

ScriptStep = AssistantResult | Callable[[LlmRequest], AssistantResult]

_call_ids = itertools.count(1)


def reply(text: str, *, input_tokens: int = 0, output_tokens: int = 0) -> AssistantResult:
    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    message = Message(role="assistant", blocks=[TextBlock(text=text)], usage=usage)
    return AssistantResult(message=message, stop_reason="end")


def tool_call(
    name: str, args: dict[str, Any] | None = None, *, call_id: str | None = None, raw_args: str | None = None
) -> ToolUseBlock:
    return ToolUseBlock(
        id=call_id or f"call_{next(_call_ids)}", name=name, args=args or {}, raw_args=raw_args
    )


def calls(*uses: ToolUseBlock, text: str = "") -> AssistantResult:
    blocks: list[Block] = [TextBlock(text=text)] if text else []
    blocks.extend(uses)
    return AssistantResult(
        message=Message(role="assistant", blocks=blocks, usage=Usage()), stop_reason="tool_use"
    )


class ScriptedModel:
    """Returns the scripted steps in order; a callable step can inspect the request or raise."""

    def __init__(self, steps: Sequence[ScriptStep]) -> None:
        self._steps = list(steps)
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> AssistantResult:
        self.requests.append(request.model_copy(deep=True))
        if not self._steps:
            raise RuntimeError("ScriptedModel has no step left for this request")
        step = self._steps.pop(0)
        if isinstance(step, AssistantResult):
            return step
        return step(request)


class EchoModel:
    async def complete(self, request: LlmRequest) -> AssistantResult:
        last_user = next((m.text() for m in reversed(request.messages) if m.role == "user"), "")
        return reply(f"(echo) {last_user}")
