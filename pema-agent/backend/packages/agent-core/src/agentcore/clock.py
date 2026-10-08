"""Time helpers shared by tools and prompt sections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Fixed English names: strftime("%A") would follow the process locale.
WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def utc_now() -> datetime:
    return datetime.now(UTC)


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ValueError(f"Unknown time zone: {name}") from err


def describe_time(moment: datetime, timezone: str) -> str:
    """``2026-10-08T14:00:00+07:00 (Thursday, Asia/Ho_Chi_Minh)``; ``moment`` must be aware."""
    local = moment.astimezone(zone(timezone))
    return f"{local.isoformat(timespec='seconds')} ({WEEKDAYS[local.weekday()]}, {timezone})"
