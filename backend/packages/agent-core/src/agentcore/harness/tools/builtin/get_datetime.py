"""``get_datetime``: the current date and time in a time zone."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field

from agentcore.clock import describe_time, utc_now, zone
from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec


class GetDatetimeArgs(BaseModel):
    timezone: str | None = Field(
        default=None,
        description="IANA time zone such as 'Asia/Ho_Chi_Minh' or 'UTC'. Omit it for the agent's default.",
    )


def make_get_datetime_tool(
    *, default_timezone: str = "UTC", clock: Callable[[], datetime] = utc_now
) -> ToolSpec[GetDatetimeArgs]:
    """``clock`` must return an aware datetime; tests pass a fixed one."""
    zone(default_timezone)

    async def handler(args: GetDatetimeArgs, ctx: ToolContext) -> ToolOutput:
        name = args.timezone or default_timezone
        try:
            return ToolOutput(text=describe_time(clock(), name))
        except ValueError:
            return ToolOutput(text=f"Unknown time zone: {name}", is_error=True)

    return ToolSpec(
        name="get_datetime",
        description="Current date and time, with the weekday, in a time zone.",
        args_model=GetDatetimeArgs,
        handler=handler,
        timeout_s=5.0,
        read_only=True,
    )
