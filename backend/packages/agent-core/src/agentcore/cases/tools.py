"""``case_done`` and ``case_wait_until``: how the model steers the case of the chat it is in.

The model acts with the plugins' tools and steers the case with these two: say the goal is reached, or say
when to come back. Each only hands a ``Decision`` to the engine's ``DecisionSink`` for the case running in
this chat; outside a case's turn the sink refuses and the tool says so. Neither reaches the network.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import BaseModel, Field

from agentcore.cases.spec import Decision
from agentcore.clock import utc_now
from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec

MAX_WHY_CHARS: Final = 300
TOOL_TIMEOUT_S: Final = 10.0

DONE_DESCRIPTION: Final = (
    "Only during a case (a message starting with [Case): the case's goal is reached. Say in reason how you "
    "know (what you checked)."
)
WAIT_DESCRIPTION: Final = (
    "Only during a case (a message starting with [Case): keep the case open and come back to it later. "
    "wait_for 'customer': when the customer answers (until, if given, is the latest time to look again). "
    "wait_for 'clock': at until. until is an ISO time with its offset, in the future."
)


class DecisionSink(Protocol):
    async def take(self, ctx: ToolContext, decision: Decision) -> str | None:
        """Records the decision for the case running in ``ctx``'s chat; returns why not, or None."""
        ...


class DoneArgs(BaseModel):
    reason: str = Field(
        min_length=1, max_length=MAX_WHY_CHARS, description="How you know the goal is reached."
    )


class WaitArgs(BaseModel):
    wait_for: Literal["customer", "clock"]
    until: datetime | None = Field(
        default=None, description="ISO time with offset, e.g. 2026-10-23T09:00:00+07:00."
    )
    why: str = Field(default="", max_length=MAX_WHY_CHARS)


def _wait_decision(args: WaitArgs, ctx: ToolContext) -> Decision | str:
    if args.until is None:
        if args.wait_for == "clock":
            return "wait_for 'clock' needs until."
        return Decision(wait_for="customer", note=args.why)
    if args.until.tzinfo is None:
        return "until needs its offset (e.g. +07:00)."
    if args.until <= (ctx.now or utc_now()):
        return "until must be in the future."
    return Decision(wait_for=args.wait_for, wake_at=args.until, note=args.why)


def make_case_tools(sink: DecisionSink) -> tuple[ToolSpec[DoneArgs], ToolSpec[WaitArgs]]:
    async def done(args: DoneArgs, ctx: ToolContext) -> ToolOutput:
        refused = await sink.take(ctx, Decision(done=args.reason, note=args.reason))
        if refused is not None:
            return ToolOutput(text=refused, is_error=True)
        return ToolOutput(text="Case closed as done.")

    async def wait(args: WaitArgs, ctx: ToolContext) -> ToolOutput:
        decision = _wait_decision(args, ctx)
        if isinstance(decision, str):
            return ToolOutput(text=decision, is_error=True)
        refused = await sink.take(ctx, decision)
        if refused is not None:
            return ToolOutput(text=refused, is_error=True)
        when = "the customer answers" if decision.wake_at is None else decision.wake_at.isoformat()
        return ToolOutput(text=f"Case waits until {when}.")

    return (
        ToolSpec(
            name="case_done",
            description=DONE_DESCRIPTION,
            args_model=DoneArgs,
            handler=done,
            timeout_s=TOOL_TIMEOUT_S,
        ),
        ToolSpec(
            name="case_wait_until",
            description=WAIT_DESCRIPTION,
            args_model=WaitArgs,
            handler=wait,
            timeout_s=TOOL_TIMEOUT_S,
        ),
    )
