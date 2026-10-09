"""``memory``: the agent adds, replaces or removes a note about the work or about the user."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec
from agentcore.memory.service import MemoryChange, MemoryEditError, MemoryKey, MemoryService

STORAGE_TOOL_TIMEOUT_S = 30.0
"""The notes may live in a remote database, which can be slow to reconnect after idling."""

DESCRIPTION = (
    "Keep a note for later sessions. target 'agent': your notes about the work and its environment; "
    "target 'user': notes about the person you are talking to. action 'add' needs content; 'replace' needs "
    "old_text (a unique part of an existing note) and content; 'remove' needs old_text. Saved notes reach "
    "your prompt in the next session."
)


class MemoryArgs(BaseModel):
    action: Literal["add", "replace", "remove"]
    target: Literal["agent", "user"]
    content: str | None = Field(default=None, description="The new note, for add and replace.")
    old_text: str | None = Field(
        default=None, description="A part of the existing note to replace or remove; it must match one note."
    )


def make_memory_tool(service: MemoryService, *, agent: str) -> ToolSpec[MemoryArgs]:
    async def handler(args: MemoryArgs, ctx: ToolContext) -> ToolOutput:
        if args.target == "user" and not ctx.user_id:
            return ToolOutput(text="There is no known user in this conversation.", is_error=True)
        user_id = (ctx.user_id or "") if args.target == "user" else ""
        key = MemoryKey(ctx.tenant_id, agent, args.target, user_id)
        try:
            change = await _apply(service, key, args)
        except MemoryEditError as err:
            return ToolOutput(text=str(err), is_error=True)
        return ToolOutput(text=_describe(args.target, change))

    return ToolSpec(
        name="memory",
        description=DESCRIPTION,
        args_model=MemoryArgs,
        handler=handler,
        timeout_s=STORAGE_TOOL_TIMEOUT_S,
    )


async def _apply(service: MemoryService, key: MemoryKey, args: MemoryArgs) -> MemoryChange:
    if args.action == "add":
        return await service.add(key, _required(args.content, "content"))
    if args.action == "replace":
        return await service.replace(
            key, _required(args.old_text, "old_text"), _required(args.content, "content")
        )
    return await service.remove(key, _required(args.old_text, "old_text"))


def _required(value: str | None, field: str) -> str:
    if value is None:
        raise MemoryEditError(f"This action needs {field}.")
    return value


def _describe(target: str, change: MemoryChange) -> str:
    usage = f"{target} memory: {len(change.entries)} notes, {change.used}/{change.limit} chars"
    if not change.changed:
        return f"Already saved; nothing changed ({usage})."
    return f"Saved ({usage}). It reaches your prompt in the next session."
