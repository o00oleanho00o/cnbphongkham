"""One turn of the agent.

The model is called in a loop and the tools it asks for are run, until it answers without a tool call. When
the step budget runs out, one last call without tools forces an answer. Every assistant message is stored
before its tools run, and every tool call gets exactly one result, so the stored history is always valid to
send back to a provider. The system prompt is the session's frozen one; the per-turn and per-step context
goes at the end of each request and is never stored. With a context manager, a request over the budget first
compacts older turns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Protocol
from uuid import uuid4

from agentcore.clock import utc_now
from agentcore.context.compaction import ContextManager
from agentcore.harness.hooks.base import HookContext, HookSet
from agentcore.harness.model.errors import ModelError
from agentcore.harness.model.types import (
    AssistantResult,
    LlmRequest,
    ModelClient,
    ReasoningEffort,
    StreamSink,
    ToolSchema,
)
from agentcore.harness.store.base import SessionStore
from agentcore.harness.tools.executor import (
    DEFAULT_MAX_CALLS_PER_STEP,
    DEFAULT_MAX_PARALLEL,
    ToolExecutor,
    ToolRun,
)
from agentcore.harness.tools.registry import ToolRegistry
from agentcore.harness.tools.spec import ToolContext
from agentcore.messages import Block, Message, TextBlock, ToolResultBlock, ToolUseBlock, Usage
from agentcore.prompt.builder import CONTEXT_CLOSE, CONTEXT_OPEN, PromptBuilder, with_context
from agentcore.prompt.sections import StepInfo, TurnInfo
from agentcore.tenancy import DEFAULT_TENANT
from agentcore.trace import TraceEvent, Tracer, TraceStop, TurnTrace, usage_detail

MEMORY_TOOL: Final = "memory"
FLUSH_STEPS: Final = 2
FLUSH_NOTE: Final = (
    "The conversation above is about to be summarised and its details dropped. If it holds something worth "
    "remembering in later sessions (the user's preferences or corrections, lasting facts), save it now with "
    "the memory tool. Otherwise reply: nothing to save."
)
TRACE_WRITE_TIMEOUT_S: Final = 10.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoopPolicy:
    max_steps: int = 6
    max_output_tokens: int = 2048
    reasoning: ReasoningEffort | None = None
    """None leaves the provider's default (DeepSeek thinks at ``high`` by default, which is slow)."""
    max_parallel_tools: int = DEFAULT_MAX_PARALLEL
    max_tool_calls_per_step: int = DEFAULT_MAX_CALLS_PER_STEP

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")
        if self.max_parallel_tools < 1 or self.max_tool_calls_per_step < 1:
            raise ValueError("max_parallel_tools and max_tool_calls_per_step must be at least 1")

    def executor(self, tools: ToolRegistry, hooks: HookSet | None) -> ToolExecutor:
        return ToolExecutor(
            tools,
            hooks,
            max_parallel=self.max_parallel_tools,
            max_calls_per_step=self.max_tool_calls_per_step,
        )


class TurnObserver(Protocol):
    """Follows a turn while it runs: the reply as it streams, and each tool call and result."""

    def text(self, delta: str) -> None: ...

    def thinking(self, delta: str) -> None: ...

    def tool_call(self, use: ToolUseBlock) -> None: ...

    def tool_result(self, result: ToolResultBlock) -> None: ...


TurnStop = Literal["completed", "max_steps"]


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    stop: TurnStop
    steps: int
    """Model calls made in this turn, including the final call without tools; retries are not counted."""
    usage: Usage
    new_messages: list[Message]
    compactions: int = 0
    duration_s: float = 0.0
    turn_id: str = ""


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
    user_id: str | None = None,
    channel: str | None = None,
    context: ContextManager | None = None,
    observer: TurnObserver | None = None,
    hooks: HookSet | None = None,
    tracer: Tracer | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> TurnResult:
    """``clock`` must return an aware datetime; tests pass a fixed one. Without ``context`` nothing is
    compacted. ``user_id`` names the person the session talks to; the caller sets it, never the model. The
    ``tracer`` gets one trace per turn, also when the turn fails; a tracer error never fails the turn."""
    started = time.perf_counter()
    started_at = clock()
    turn_id = str(uuid4())
    limits = policy or LoopPolicy()
    guards = hooks or HookSet()
    executor = limits.executor(tools, guards)
    ctx = ToolContext(session_id=session_id, tenant_id=tenant_id, user_id=user_id)
    schemas = tools.schemas()
    new_messages: list[Message] = []
    events: list[TraceEvent] = []
    usage = Usage()
    compactions = 0
    turn_start = 0
    system = ""
    turn_prompt = prompt.start_turn(TurnInfo(now=started_at, channel=channel))

    async def record(message: Message) -> None:
        await store.append(tenant_id, session_id, message)
        new_messages.append(message)

    async def build(step: StepInfo, offered: list[ToolSchema]) -> LlmRequest:
        history = await store.load(tenant_id, session_id)
        compaction = await store.load_compaction(tenant_id, session_id)
        visible = history[compaction.first_kept :] if compaction else history
        return LlmRequest(
            system=system,
            messages=with_context(visible, turn_prompt.context(step)),
            tools=offered,
            max_output_tokens=limits.max_output_tokens,
            reasoning=limits.reasoning,
        )

    async def request_for(step: StepInfo, offered: list[ToolSchema]) -> LlmRequest:
        nonlocal system, usage, compactions
        request = await build(step, offered)
        if context is None or not context.over_budget(request):
            return request

        async def flush(messages: Sequence[Message]) -> Usage:
            flush_started = time.perf_counter()
            used = await flush_memory(
                model=model,
                tools=tools,
                ctx=ctx,
                system=system,
                messages=messages,
                max_output_tokens=limits.max_output_tokens,
                hooks=guards,
            )
            elapsed = time.perf_counter() - flush_started
            if tools.get(MEMORY_TOOL) is not None:
                events.append(TraceEvent("memory_flush", step.step, elapsed, detail=usage_detail(used)))
            return used

        compact_started = time.perf_counter()
        outcome = await context.compact(
            store=store,
            tenant_id=tenant_id,
            session_id=session_id,
            keep_from=turn_start,
            max_output_tokens=limits.max_output_tokens,
            before_summary=flush,
        )
        if outcome is None:
            return request
        detail = {
            "compacted_messages": outcome.compacted_messages,
            "fallback": outcome.fallback,
            **usage_detail(outcome.usage),
        }
        events.append(
            TraceEvent("compaction", step.step, time.perf_counter() - compact_started, detail=detail)
        )
        compactions += 1
        usage = usage + outcome.usage
        system = await prompt.system(store, tenant_id, session_id, user_id=user_id, refresh=True)
        return await build(step, offered)

    async def call_model(step: StepInfo, offered: list[ToolSchema]) -> AssistantResult:
        hook_ctx = HookContext(tenant_id=tenant_id, session_id=session_id, user_id=user_id, step=step.step)
        request = await guards.before_model(await request_for(step, offered), hook_ctx)
        call_started = time.perf_counter()
        try:
            result = await _complete(model, request, observer)
        except ModelError as err:
            elapsed = time.perf_counter() - call_started
            events.append(
                TraceEvent("model_call", step.step, elapsed, is_error=True, detail={"error_kind": err.kind})
            )
            raise
        detail = {"stop_reason": result.stop_reason, **usage_detail(result.message.usage or Usage())}
        events.append(TraceEvent("model_call", step.step, time.perf_counter() - call_started, detail=detail))
        return await guards.after_model(result, hook_ctx)

    def finished(text: str, stop: TurnStop, steps: int) -> TurnResult:
        return TurnResult(
            text=text,
            stop=stop,
            steps=steps,
            usage=usage,
            new_messages=new_messages,
            compactions=compactions,
            duration_s=time.perf_counter() - started,
            turn_id=turn_id,
        )

    async def turn() -> TurnResult:
        nonlocal system, turn_start, usage
        system = await prompt.system(store, tenant_id, session_id, user_id=user_id)
        turn_start = len(await store.load(tenant_id, session_id))
        await record(Message.user(user_text))

        for step in range(1, limits.max_steps + 1):
            result = await call_model(StepInfo(step=step, max_steps=limits.max_steps), schemas)
            usage = usage + (result.message.usage or Usage())
            await record(result.message)

            uses = result.message.tool_uses()
            if not uses:
                return finished(result.message.text(), "completed", step)
            for run in await executor.execute(uses, ctx, step=step, observer=observer):
                events.append(_tool_event(step, run))
                await record(Message(role="tool", blocks=[run.result]))

        final_step = StepInfo(step=limits.max_steps + 1, max_steps=limits.max_steps, final=True)
        result = await call_model(final_step, [])
        usage = usage + (result.message.usage or Usage())
        final = _without_tool_calls(result.message)
        await record(final)
        return finished(final.text(), "max_steps", limits.max_steps + 1)

    def trace_of(stop: TraceStop, steps: int, duration_s: float, error_kind: str | None) -> TurnTrace:
        return TurnTrace(
            turn_id=turn_id,
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            started_at=started_at,
            duration_s=duration_s,
            stop=stop,
            steps=steps,
            usage=usage,
            compactions=compactions,
            error_kind=error_kind,
            events=tuple(events),
        )

    try:
        outcome = await turn()
    except Exception as err:
        kind = err.kind if isinstance(err, ModelError) else type(err).__name__
        steps = sum(1 for e in events if e.kind == "model_call")
        await _write_trace(tracer, trace_of("error", steps, time.perf_counter() - started, kind))
        raise
    await _write_trace(tracer, trace_of(outcome.stop, outcome.steps, outcome.duration_s, None))
    return outcome


async def flush_memory(
    *,
    model: ModelClient,
    tools: ToolRegistry,
    ctx: ToolContext,
    system: str,
    messages: Sequence[Message],
    max_output_tokens: int,
    hooks: HookSet | None = None,
) -> Usage:
    """Before older turns are summarised, the model gets one chance (at most two calls, only the memory tool)
    to save what should outlive them. Nothing it says is stored; a model error skips the flush. The writes go
    through the same guards as any other tool call."""
    memory = tools.get(MEMORY_TOOL)
    if memory is None or not messages:
        return Usage()
    only_memory = ToolRegistry([memory])
    executor = ToolExecutor(only_memory, hooks)
    conversation = with_context(messages, f"{CONTEXT_OPEN}\n{FLUSH_NOTE}\n{CONTEXT_CLOSE}")
    used = Usage()
    for _ in range(FLUSH_STEPS):
        request = LlmRequest(
            system=system,
            messages=conversation,
            tools=only_memory.schemas(),
            max_output_tokens=max_output_tokens,
            reasoning="off",
        )
        try:
            result = await model.complete(request)
        except ModelError as err:
            logger.warning("memory flush skipped (%s)", err.kind)
            return used
        used = used + (result.message.usage or Usage())
        uses = result.message.tool_uses()
        if not uses:
            return used
        outcomes = await executor.run(uses, ctx, step=0)
        results = [Message(role="tool", blocks=[outcome]) for outcome in outcomes]
        conversation = [*conversation, result.message, *results]
    return used


async def _complete(model: ModelClient, request: LlmRequest, sink: StreamSink | None) -> AssistantResult:
    """Some gateways sometimes return an empty completion with a success status; one retry is worth it."""
    try:
        return await model.complete(request, sink=sink)
    except ModelError as err:
        if err.kind != "empty_response":
            raise
    return await model.complete(request, sink=sink)


def _tool_event(step: int, run: ToolRun) -> TraceEvent:
    detail: dict[str, Any] = {"call_id": run.result.tool_use_id, "result_chars": len(run.result.content)}
    if run.blocked_by:
        detail["blocked_by"] = run.blocked_by
    return TraceEvent(
        "tool_call", step, run.duration_s, name=run.result.name, is_error=run.result.is_error, detail=detail
    )


async def _write_trace(tracer: Tracer | None, trace: TurnTrace) -> None:
    if tracer is None:
        return
    try:
        await asyncio.wait_for(tracer.record(trace), timeout=TRACE_WRITE_TIMEOUT_S)
    except Exception as err:  # the reply is already stored; a lost trace must not fail the turn
        logger.warning("trace of turn %s not saved (%s)", trace.turn_id, type(err).__name__)


def _without_tool_calls(message: Message) -> Message:
    """The final call offers no tools; a call the model makes anyway would be left without a result."""
    blocks: list[Block] = [b for b in message.blocks if not isinstance(b, ToolUseBlock)]
    return message.model_copy(update={"blocks": blocks or [TextBlock(text="")]})
