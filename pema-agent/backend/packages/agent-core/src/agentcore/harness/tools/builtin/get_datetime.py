"""``get_datetime``: the current date and time in a time zone."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec

# Fixed English names: strftime("%A") would follow the process locale.
_WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class GetDatetimeArgs(BaseModel):
    timezone: str | None = Field(
        default=None,
        description="IANA time zone such as 'Asia/Ho_Chi_Minh' or 'UTC'. Omit it for the agent's default.",
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def make_get_datetime_tool(
    *, default_timezone: str = "UTC", clock: Callable[[], datetime] = _utc_now
) -> ToolSpec[GetDatetimeArgs]:
    """``clock`` must return an aware datetime; tests pass a fixed one."""
    _zone(default_timezone)

    async def handler(args: GetDatetimeArgs, ctx: ToolContext) -> ToolOutput:
        name = args.timezone or default_timezone
        try:
            zone = _zone(name)
        except ValueError:
            return ToolOutput(text=f"Unknown time zone: {name}", is_error=True)
        now = clock().astimezone(zone)
        return ToolOutput(text=f"{now.isoformat(timespec='seconds')} ({_WEEKDAYS[now.weekday()]}, {name})")

    return ToolSpec(
        name="get_datetime",
        description="Current date and time, with the weekday, in a time zone.",
        args_model=GetDatetimeArgs,
        handler=handler,
        timeout_s=5.0,
    )


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ValueError(f"Unknown time zone: {name}") from err
