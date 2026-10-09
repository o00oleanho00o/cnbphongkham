"""Runs the tool calls of one model reply.

Calls are checked (known tool, JSON arguments, ``pre_tool`` guards, argument schema), run with their own
timeout, truncated and passed through ``post_tool`` hooks. Consecutive read-only calls run at the same time;
anything that changes state runs alone, in order. Results always come back in call order, one per call, so the
history stays valid for every provider. Calls beyond ``max_calls_per_step`` get an error result instead.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import ValidationError

from agentcore.harness.hooks.base import Deny, HookContext, HookSet
from agentcore.harness.tools.registry import ToolRegistry
from agentcore.harness.tools.spec import ToolContext, ToolSpec
from agentcore.messages import ToolResultBlock, ToolUseBlock

ERROR_TEXT_LIMIT: Final = 300
VALIDATION_ERRORS_SHOWN: Final = 3
DEFAULT_MAX_PARALLEL: Final = 4
DEFAULT_MAX_CALLS_PER_STEP: Final = 8


class ToolObserver(Protocol):
    def tool_call(self, use: ToolUseBlock) -> None: ...

    def tool_result(self, result: ToolResultBlock) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolRun:
    result: ToolResultBlock
    duration_s: float
    blocked_by: str | None = None


class ToolExecutor:
    def __init__(
        self,
        tools: ToolRegistry,
        hooks: HookSet | None = None,
        *,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
        max_calls_per_step: int = DEFAULT_MAX_CALLS_PER_STEP,
    ) -> None:
        if max_parallel < 1 or max_calls_per_step < 1:
            raise ValueError("max_parallel and max_calls_per_step must be at least 1")
        self._tools = tools
        self._hooks = hooks or HookSet()
        self._max_parallel = max_parallel
        self._max_calls = max_calls_per_step

    async def run(
        self,
        uses: Sequence[ToolUseBlock],
        ctx: ToolContext,
        *,
        step: int,
        observer: ToolObserver | None = None,
    ) -> list[ToolResultBlock]:
        return [run.result for run in await self.execute(uses, ctx, step=step, observer=observer)]

    async def execute(
        self,
        uses: Sequence[ToolUseBlock],
        ctx: ToolContext,
        *,
        step: int,
        observer: ToolObserver | None = None,
    ) -> list[ToolRun]:
        """Like ``run``, with how long each call took and the guard that blocked it."""
        hook_ctx = HookContext(
            tenant_id=ctx.tenant_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            step=step,
            channel=ctx.channel,
        )
        allowed, refused = list(uses[: self._max_calls]), list(uses[self._max_calls :])
        runs: list[ToolRun] = []
        limit = asyncio.Semaphore(self._max_parallel)

        async def bounded(use: ToolUseBlock) -> ToolRun:
            async with limit:
                return await self._run_one(use, ctx, hook_ctx)

        for batch in self._batches(allowed):
            if observer is not None:
                for use in batch:
                    observer.tool_call(use)
            done = await asyncio.gather(*(bounded(use) for use in batch))
            runs.extend(done)
            if observer is not None:
                for run in done:
                    observer.tool_result(run.result)
        for use in refused:
            result = _error(
                use, f"Too many tool calls in one step: at most {self._max_calls}. Call it again later."
            )
            runs.append(ToolRun(result, 0.0))
            if observer is not None:
                observer.tool_result(result)
        return runs

    def _batches(self, uses: Sequence[ToolUseBlock]) -> list[list[ToolUseBlock]]:
        """Consecutive read-only calls share a batch; every other call is a batch of its own."""
        batches: list[list[ToolUseBlock]] = []
        for use in uses:
            spec = self._tools.get(use.name)
            parallel = spec is not None and spec.read_only
            if parallel and batches and batches[-1] and self._is_read_only(batches[-1][-1]):
                batches[-1].append(use)
            else:
                batches.append([use])
        return batches

    def _is_read_only(self, use: ToolUseBlock) -> bool:
        spec = self._tools.get(use.name)
        return spec is not None and spec.read_only

    async def _run_one(self, use: ToolUseBlock, ctx: ToolContext, hook_ctx: HookContext) -> ToolRun:
        started = time.perf_counter()
        spec = self._tools.get(use.name)
        result, blocked_by = await self._checked(use, spec, ctx, hook_ctx)
        result = await self._hooks.after_tool(use, spec, result, hook_ctx)
        return ToolRun(result, time.perf_counter() - started, blocked_by)

    async def _checked(
        self, use: ToolUseBlock, spec: ToolSpec[Any] | None, ctx: ToolContext, hook_ctx: HookContext
    ) -> tuple[ToolResultBlock, str | None]:
        if spec is None:
            return _error(use, f"Unknown tool: {use.name}"), None
        if use.raw_args is not None:
            return _error(use, "Arguments are not valid JSON: send a JSON object."), None
        checked = await self._hooks.before_tool(use, spec, hook_ctx)
        if isinstance(checked, Deny):
            return _error(use, f"blocked by {checked.reason}"), checked.hook
        try:
            args = spec.args_model.model_validate(checked.args)
        except ValidationError as err:
            return _error(use, f"Invalid arguments: {_describe(err)}"), None
        return await _execute(spec, args, use, ctx), None


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
    """Keeps the start and the end: errors and totals usually sit at the end of long output."""
    if len(text) <= limit:
        return text
    head = (limit + 1) // 2
    tail = limit - head
    return f"{text[:head]}\n…[{len(text) - limit} chars omitted]…\n{text[len(text) - tail :]}"
