"""The tool executor: hook chain around each call, parallel read-only batches, call order and the per-step cap."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from agentcore import ToolContext, ToolOutput, ToolRegistry, ToolResultBlock, ToolSpec, ToolUseBlock
from agentcore.harness.hooks import (
    ALLOW,
    Deny,
    HookContext,
    HookSet,
    PostToolHook,
    PreToolHook,
    Rewrite,
    ToolDecision,
)
from agentcore.harness.model.scripted import tool_call
from agentcore.harness.tools.executor import ToolExecutor

CTX = ToolContext(session_id="s", tenant_id="t", user_id="u1")


class TextArgs(BaseModel):
    text: str = ""


def _tool(name: str, handler: Any, *, read_only: bool = False, timeout_s: float = 5.0) -> ToolSpec[TextArgs]:
    return ToolSpec(
        name=name,
        description=name,
        args_model=TextArgs,
        handler=handler,
        read_only=read_only,
        timeout_s=timeout_s,
    )


async def _echo(args: TextArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text=args.text)


def _contents(results: list[ToolResultBlock]) -> list[str]:
    return [r.content for r in results]


async def test_read_only_calls_really_run_at_the_same_time() -> None:
    both_started = asyncio.Barrier(2)

    async def meet(args: TextArgs, ctx: ToolContext) -> ToolOutput:
        await both_started.wait()  # would time out if the calls ran one after the other
        return ToolOutput(text=args.text)

    tools = ToolRegistry([_tool("meet", meet, read_only=True, timeout_s=1.0)])
    uses = [tool_call("meet", {"text": "a"}), tool_call("meet", {"text": "b"})]

    results = await ToolExecutor(tools).run(uses, CTX, step=1)

    assert _contents(results) == ["a", "b"]
    assert [r.tool_use_id for r in results] == [u.id for u in uses]


async def test_parallel_calls_are_bounded_by_max_parallel() -> None:
    running = 0
    peak = 0

    async def busy(args: TextArgs, ctx: ToolContext) -> ToolOutput:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return ToolOutput(text=args.text)

    tools = ToolRegistry([_tool("busy", busy, read_only=True)])
    uses = [tool_call("busy", {"text": str(i)}) for i in range(5)]

    results = await ToolExecutor(tools, max_parallel=2).run(uses, CTX, step=1)

    assert _contents(results) == ["0", "1", "2", "3", "4"]
    assert peak == 2


async def test_a_write_runs_alone_and_splits_the_read_only_batches() -> None:
    log: list[str] = []

    def logged(kind: str) -> Any:
        async def handler(args: TextArgs, ctx: ToolContext) -> ToolOutput:
            log.append(f"start {args.text}")
            await asyncio.sleep(0)
            log.append(f"end {args.text}")
            return ToolOutput(text=f"{kind} {args.text}")

        return handler

    tools = ToolRegistry([_tool("read", logged("read"), read_only=True), _tool("write", logged("write"))])
    uses = [
        tool_call("read", {"text": "r1"}),
        tool_call("read", {"text": "r2"}),
        tool_call("write", {"text": "w1"}),
        tool_call("write", {"text": "w2"}),
        tool_call("read", {"text": "r3"}),
    ]

    results = await ToolExecutor(tools).run(uses, CTX, step=1)

    assert _contents(results) == ["read r1", "read r2", "write w1", "write w2", "read r3"]
    assert log[:2] == ["start r1", "start r2"]  # the two reads overlap
    assert log[4:] == ["start w1", "end w1", "start w2", "end w2", "start r3", "end r3"]


async def test_calls_past_the_cap_get_an_error_and_never_run() -> None:
    ran: list[str] = []

    async def record(args: TextArgs, ctx: ToolContext) -> ToolOutput:
        ran.append(args.text)
        return ToolOutput(text=args.text)

    tools = ToolRegistry([_tool("record", record)])
    uses = [tool_call("record", {"text": str(i)}) for i in range(3)]

    results = await ToolExecutor(tools, max_calls_per_step=2).run(uses, CTX, step=1)

    assert ran == ["0", "1"]
    assert results[2].is_error
    assert "Too many tool calls in one step: at most 2" in results[2].content


async def test_a_denied_call_is_not_run_and_the_model_sees_why() -> None:
    ran: list[str] = []

    async def record(args: TextArgs, ctx: ToolContext) -> ToolOutput:
        ran.append(args.text)
        return ToolOutput(text="ran")

    async def deny(use: ToolUseBlock, spec: ToolSpec[Any], ctx: HookContext) -> ToolDecision:
        return Deny("not today") if use.args.get("text") == "no" else ALLOW

    tools = ToolRegistry([_tool("record", record)])
    hooks = HookSet.of([PreToolHook("policy", deny)])
    uses = [tool_call("record", {"text": "no"}), tool_call("record", {"text": "yes"})]

    results = await ToolExecutor(tools, hooks).run(uses, CTX, step=1)

    assert ran == ["yes"]
    assert (results[0].is_error, results[0].content) == (True, "blocked by policy: not today")


async def test_a_rewrite_changes_the_arguments_before_they_are_checked() -> None:
    async def lower(use: ToolUseBlock, spec: ToolSpec[Any], ctx: HookContext) -> ToolDecision:
        return Rewrite({"text": str(use.args["text"]).lower()})

    hooks = HookSet.of([PreToolHook("lower", lower)])

    results = await ToolExecutor(ToolRegistry([_tool("echo", _echo)]), hooks).run(
        [tool_call("echo", {"text": "LOUD"})], CTX, step=1
    )

    assert _contents(results) == ["loud"]


async def test_a_broken_or_slow_pre_tool_guard_blocks_the_call() -> None:
    async def broken(use: ToolUseBlock, spec: ToolSpec[Any], ctx: HookContext) -> ToolDecision:
        raise RuntimeError("boom")

    async def slow(use: ToolUseBlock, spec: ToolSpec[Any], ctx: HookContext) -> ToolDecision:
        await asyncio.sleep(1)
        return ALLOW

    tools = ToolRegistry([_tool("echo", _echo)])
    use = tool_call("echo", {"text": "x"})

    (failed,) = await ToolExecutor(tools, HookSet.of([PreToolHook("broken", broken)])).run([use], CTX, step=1)
    (timed_out,) = await ToolExecutor(tools, HookSet.of([PreToolHook("slow", slow, timeout_s=0.01)])).run(
        [use], CTX, step=1
    )

    assert failed.content == "blocked by guard broken failed (RuntimeError)"
    assert timed_out.content == "blocked by guard slow failed (TimeoutError)"


async def test_post_tool_hooks_see_every_result_and_a_broken_one_is_skipped() -> None:
    seen: list[str] = []

    async def watch(
        use: ToolUseBlock, spec: ToolSpec[Any] | None, result: ToolResultBlock, ctx: HookContext
    ) -> ToolResultBlock:
        seen.append(f"{use.name}:{spec is not None}:{ctx.step}")
        return result

    async def broken(
        use: ToolUseBlock, spec: ToolSpec[Any] | None, result: ToolResultBlock, ctx: HookContext
    ) -> ToolResultBlock:
        raise RuntimeError("boom")

    hooks = HookSet.of([PostToolHook("broken", broken), PostToolHook("watch", watch)])
    uses = [tool_call("echo", {"text": "x"}), tool_call("missing")]

    results = await ToolExecutor(ToolRegistry([_tool("echo", _echo)]), hooks).run(uses, CTX, step=3)

    assert _contents(results) == ["x", "Unknown tool: missing"]
    assert seen == ["echo:True:3", "missing:False:3"]
