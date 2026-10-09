"""Hook points around model and tool calls: where guides and sensors plug into the turn.

``pre_tool`` hooks are policy: a hook that fails or times out blocks the tool (fail closed). The other points
are advisory: a failing hook is logged and skipped (fail open). Hooks run in the order they were added; the
first ``Deny`` ends the ``pre_tool`` chain.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from agentcore.harness.model.types import AssistantResult, LlmRequest
from agentcore.harness.tools.spec import ToolSpec
from agentcore.messages import ToolResultBlock, ToolUseBlock

DEFAULT_HOOK_TIMEOUT_S: Final = 5.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HookContext:
    tenant_id: str
    session_id: str
    user_id: str | None
    step: int


@dataclass(frozen=True, slots=True)
class Allow:
    pass


@dataclass(frozen=True, slots=True)
class Deny:
    reason: str
    hook: str = ""
    """Filled in by the HookSet: the name of the hook that refused."""


@dataclass(frozen=True, slots=True)
class Rewrite:
    args: dict[str, Any]


ToolDecision = Allow | Deny | Rewrite
ALLOW: Final = Allow()


@dataclass(frozen=True, slots=True)
class PreModelHook:
    name: str
    run: Callable[[LlmRequest, HookContext], Awaitable[LlmRequest]]
    timeout_s: float = DEFAULT_HOOK_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class PostModelHook:
    name: str
    run: Callable[[AssistantResult, HookContext], Awaitable[AssistantResult]]
    timeout_s: float = DEFAULT_HOOK_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class PreToolHook:
    name: str
    run: Callable[[ToolUseBlock, ToolSpec[Any], HookContext], Awaitable[ToolDecision]]
    timeout_s: float = DEFAULT_HOOK_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class PostToolHook:
    name: str
    run: Callable[
        [ToolUseBlock, ToolSpec[Any] | None, ToolResultBlock, HookContext], Awaitable[ToolResultBlock]
    ]
    timeout_s: float = DEFAULT_HOOK_TIMEOUT_S


Hook = PreModelHook | PostModelHook | PreToolHook | PostToolHook


@dataclass(slots=True)
class HookSet:
    pre_model: list[PreModelHook] = field(default_factory=list[PreModelHook])
    post_model: list[PostModelHook] = field(default_factory=list[PostModelHook])
    pre_tool: list[PreToolHook] = field(default_factory=list[PreToolHook])
    post_tool: list[PostToolHook] = field(default_factory=list[PostToolHook])

    @classmethod
    def of(cls, hooks: Iterable[Hook]) -> HookSet:
        hook_set = cls()
        for hook in hooks:
            hook_set.add(hook)
        return hook_set

    def add(self, hook: Hook) -> None:
        if isinstance(hook, PreModelHook):
            self.pre_model.append(hook)
        elif isinstance(hook, PostModelHook):
            self.post_model.append(hook)
        elif isinstance(hook, PreToolHook):
            self.pre_tool.append(hook)
        else:
            self.post_tool.append(hook)

    async def before_model(self, request: LlmRequest, ctx: HookContext) -> LlmRequest:
        for hook in self.pre_model:
            request = await _advisory(hook.name, hook.timeout_s, hook.run(request, ctx), request)
        return request

    async def after_model(self, result: AssistantResult, ctx: HookContext) -> AssistantResult:
        for hook in self.post_model:
            result = await _advisory(hook.name, hook.timeout_s, hook.run(result, ctx), result)
        return result

    async def before_tool(
        self, use: ToolUseBlock, spec: ToolSpec[Any], ctx: HookContext
    ) -> ToolUseBlock | Deny:
        """The call to run (its arguments possibly rewritten), or the first refusal."""
        for hook in self.pre_tool:
            try:
                decision = await asyncio.wait_for(hook.run(use, spec, ctx), timeout=hook.timeout_s)
            except Exception as err:  # fail closed: a broken guard must not let the call through
                logger.warning(
                    "pre_tool hook %s failed (%s); %s blocked", hook.name, type(err).__name__, use.name
                )
                return Deny(f"guard {hook.name} failed ({type(err).__name__})", hook.name)
            if isinstance(decision, Deny):
                return Deny(f"{hook.name}: {decision.reason}", hook.name)
            if isinstance(decision, Rewrite):
                use = use.model_copy(update={"args": decision.args})
        return use

    async def after_tool(
        self, use: ToolUseBlock, spec: ToolSpec[Any] | None, result: ToolResultBlock, ctx: HookContext
    ) -> ToolResultBlock:
        for hook in self.post_tool:
            result = await _advisory(hook.name, hook.timeout_s, hook.run(use, spec, result, ctx), result)
        return result


async def _advisory[T](name: str, timeout_s: float, work: Awaitable[T], fallback: T) -> T:
    try:
        return await asyncio.wait_for(work, timeout=timeout_s)
    except Exception as err:  # fail open: an advisory hook never breaks the turn
        logger.warning("hook %s failed (%s); skipped", name, type(err).__name__)
        return fallback
