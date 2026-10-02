"""The send window: messages are only sent between ``start`` and ``end`` local time (default 08:00-20:00).

New module (not a port). The window is clinic configuration (``clinic.channel_setting.send_window_start`` /
``send_window_end``, read through S's ``ChannelPolicyReader``, see ``ChannelPolicySendWindow``); this module
only does the arithmetic. A message the agent produces outside the window is not dropped: it is queued for
``next_open`` (the start of the next window) through the ``Scheduler`` port.

A window that crosses midnight (22:00-06:00) is supported like in S's ``proactive_send_guard``; ``start ==
end`` means "always open". An invalid time zone falls back to UTC (same rule as ``pema.shared.zone_time``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pema.config.runtime_tuning_settings import bot_time_zone
from pema.scheduler.ports import ChannelPolicyReader

CARE_TIME_ZONE = "Asia/Ho_Chi_Minh"
DEFAULT_WINDOW_START = time(8, 0)
DEFAULT_WINDOW_END = time(20, 0)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


@dataclass(frozen=True)
class SendWindow:
    start: time = DEFAULT_WINDOW_START
    end: time = DEFAULT_WINDOW_END
    time_zone: str = CARE_TIME_ZONE

    def is_open(self, now: datetime) -> bool:
        if self.start == self.end:
            return True
        local = now.astimezone(_zone(self.time_zone)).time().replace(tzinfo=None)
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end

    def next_open(self, now: datetime) -> datetime:
        """``now`` when the window is open, else the start of the next window (UTC)."""
        if self.is_open(now):
            return now
        zone = _zone(self.time_zone)
        local = now.astimezone(zone)
        day = local.date()
        candidate = datetime.combine(day, self.start, tzinfo=zone)
        if candidate <= local:
            candidate = datetime.combine(day + timedelta(days=1), self.start, tzinfo=zone)
        return candidate.astimezone(UTC)


DEFAULT_SEND_WINDOW = SendWindow()


def _parse_hhmm(value: str) -> time | None:
    try:
        hours, minutes = value.split(":")[:2]
        return time(int(hours), int(minutes))
    except ValueError:
        return None


class ChannelPolicySendWindow:
    """``SendWindowProvider`` over the clinic-wide switchboard of one channel kind: the window of that
    row, the default 08:00-20:00 when the clinic has no row or left the window empty."""

    def __init__(self, reader: ChannelPolicyReader, channel_kind: str) -> None:
        self._reader = reader
        self._channel_kind = channel_kind

    async def get(self, clinic_id: UUID) -> SendWindow:
        zone = bot_time_zone()
        policy = await self._reader.get_channel_policy(clinic_id, self._channel_kind)
        if policy is None or policy.send_window_start is None or policy.send_window_end is None:
            return SendWindow(time_zone=zone)
        start = _parse_hhmm(policy.send_window_start)
        end = _parse_hhmm(policy.send_window_end)
        if start is None or end is None:
            return SendWindow(time_zone=zone)
        return SendWindow(start=start, end=end, time_zone=zone)
