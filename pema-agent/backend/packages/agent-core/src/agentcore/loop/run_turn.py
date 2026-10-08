"""One turn of the agent.

The model is called in a loop and the tools it asks for are run, until it answers without a tool call. When
the step budget runs out, one last call without tools forces an answer. Every assistant message is stored
before its tools run, and every tool call gets exactly one result, so the stored history is always valid to
send back to a provider. The system prompt is the session's frozen one; the per-turn and per-step context
goes at the end of each request and is never stored.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import ValidationError

from agentcore.clock import utc_now
from agentcore.harness.model.errors import ModelError
from agentcore.harness.model.types import AssistantResult, LlmRequest, ModelClient
from agentcore.harness.store.base import SessionStore
from agentcore.harness.tools.registry import ToolRegistry
from agentcore.harness.tools.spec import ToolContext, ToolSpec
from agentcore.messages import Block, Message, TextBlock, ToolResultBlock, ToolUseBlock, Usage
from agentcore.prompt.builder import PromptBuilder, with_context
from agentcore.prompt.sections import StepInfo, TurnInfo
from agentcore.tenancy import DEFAULT_TENANT

ERROR_TEXT_LIMIT: Final = 300
VALIDATION_ERRORS_SHOWN: Final = 3


@dataclass(frozen=True, slots=True)
class LoopPolicy:
    max_steps: int = 6
    max_output_tokens: int = 2048

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")


TurnStop = Literal["completed", "max_steps"]


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    stop: TurnStop
    steps: int
    """Model calls made in this turn, including the final call without tools; retries are not counted."""
    usage: Usage
    new_messages: list[Message]


async def run_turn(
    *,
    session_id: str,
    user_text: str,
    prompt: PromptBuilder,
    model: ModelClient,
    tools: ToolRegistry,
    store: SessionStore,
    policy: LoopPolicy | None = None,
    tenant_id: str = DEFAULT_TENANT,
    channel: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> TurnResult:
    """``clock`` must return an aware datetime; tests pass a fixed one."""
    limits = policy or LoopPolicy()
    ctx = ToolContext(session_id=session_id, tenant_id=tenant_id)
    schemas = tools.schemas()
    new_messages: list[Message] = []
    usage = Usage()
    system = await prompt.system(store, tenant_id, session_id)
    turn_prompt = prompt.start_turn(TurnInfo(now=clock(), channel=channel))

    async def record(message: Message) -> None:
        await store.append(tenant_id, session_id, message)
        new_messages.append(message)

    await record(Message.user(user_text))

    for step in range(1, limits.max_steps + 1):
        history = await store.load(tenant_id, session_id)
        context = turn_prompt.context(StepInfo(step=step, max_steps=limits.max_steps))
        request = LlmRequest(
            system=system,
            messages=with_context(history, context),
            tools=schemas,
            max_output_tokens=limits.max_output_tokens,
        )
        result = await _complete(model, request)
        usage = usage + (result.message.usage or Usage())
        await record(result.message)

        uses = result.message.tool_uses()
        if not uses:
            return TurnResult(
                text=result.message.text(),
                stop="completed",
                steps=step,
                usage=usage,
                new_messages=new_messages,
            )
        for use in uses:
            await record(Message(role="tool", blocks=[await _run_tool(use, tools, ctx)]))

    history = await store.load(tenant_id, session_id)
    context = turn_prompt.context(StepInfo(step=limits.max_steps + 1, max_steps=limits.max_steps, final=True))
    request = LlmRequest(
        system=system,
        messages=with_context(history, context),
        tools=[],
        max_output_tokens=limits.max_output_tokens,
    )
    result = await _complete(model, request)
    usage = usage + (result.message.usage or Usage())
    final = _without_tool_calls(result.message)
    await record(final)
    return TurnResult(
        text=final.text(),
        stop="max_steps",
        steps=limits.max_steps + 1,
        usage=usage,
        new_messages=new_messages,
    )


async def _complete(model: ModelClient, request: LlmRequest) -> AssistantResult:
    """Some gateways sometimes return an empty completion with a success status; one retry is worth it."""
    try:
        return await model.complete(request)
    except ModelError as err:
        if err.kind != "empty_response":
            raise
    return await model.complete(request)


async def _run_tool(use: ToolUseBlock, tools: ToolRegistry, ctx: ToolContext) -> ToolResultBlock:
    spec = tools.get(use.name)
    if spec is None:
        return _error(use, f"Unknown tool: {use.name}")
    if use.raw_args is not None:
        return _error(use, "Arguments are not valid JSON: send a JSON object.")
    try:
        args = spec.args_model.model_validate(use.args)
    except ValidationError as err:
        return _error(use, f"Invalid arguments: {_describe(err)}")
    return await _execute(spec, args, use, ctx)


async def _execute(spec: ToolSpec[Any], args: Any, use: ToolUseBlock, ctx: ToolContext) -> ToolResultBlock:
    try:
        output = await asyncio.wait_for(spec.handler(args, ctx), timeout=spec.timeout_s)
    except TimeoutError:
        return _error(use, f"Tool timed out after {spec.timeout_s:g}s")
    except Exception as err:  # a failing tool must not end the turn: the model sees the error and can recover
        return _error(use, _truncate(f"{type(err).__name__}: {err}", ERROR_TEXT_LIMIT))
    return ToolResultBlock(
        tool_use_id=use.id,
        name=use.name,
        content=_truncate(output.text, spec.max_result_chars),
        is_error=output.is_error,
    )


def _error(use: ToolUseBlock, text: str) -> ToolResultBlock:
    return ToolResultBlock(tool_use_id=use.id, name=use.name, content=text, is_error=True)


def _describe(err: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or '(arguments)'}: {e['msg']}"
        for e in err.errors(include_url=False)[:VALIDATION_ERRORS_SHOWN]
    ]
    return "; ".join(parts)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[truncated {len(text) - limit} chars]"


def _without_tool_calls(message: Message) -> Message:
    """The final call offers no tools; a call the model makes anyway would be left without a result."""
    blocks: list[Block] = [b for b in message.blocks if not isinstance(b, ToolUseBlock)]
    return message.model_copy(update={"blocks": blocks or [TextBlock(text="")]})
