# ported from: src/shared/current-datetime.ts
"""Current date and time in an IANA time zone. Pure module: it does NOT import env so that
``config/env`` can use ``is_valid_timezone`` at validation time without an import cycle; the caller
passes ``BOT_TIMEZONE`` in.

The weekday is computed by the server: an LLM that infers the weekday from the date is very often wrong,
so the tool returns it ready and tells the model to use it verbatim (learned from GoClaw's datetime tool:
"authoritative, never infer").

Forced deviation: ``Intl.DateTimeFormat`` becomes ``zoneinfo``; the weekday names stay the Vietnamese
ones of the original.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Python weekday(): Monday = 0
WEEKDAY_VI: tuple[str, ...] = ("Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy", "Chủ nhật")


@dataclass(frozen=True)
class DateTimeParts:
    """Date and time pieces split at one instant, in one time zone."""

    date: str
    """e.g. ``25/07/2026``"""
    time: str
    """e.g. ``22:15``"""
    weekday: str
    """e.g. ``Thứ bảy``; computed by the server, never left to the model."""
    timezone: str


def _zone(time_zone: str) -> ZoneInfo | None:
    if not time_zone:
        return None
    try:
        return ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def get_date_time_parts(time_zone: str, now: datetime | None = None) -> DateTimeParts:
    """The zone from env is validated at boot but we still fall back to UTC: one bad value must not kill
    an agent turn."""
    zone = _zone(time_zone)
    tz_name = time_zone if zone is not None else "UTC"
    moment = (now or datetime.now(UTC)).astimezone(zone or UTC)
    return DateTimeParts(
        date=moment.strftime("%d/%m/%Y"),
        time=moment.strftime("%H:%M"),
        weekday=WEEKDAY_VI[moment.weekday()],
        timezone=tz_name,
    )


def current_date_line(time_zone: str, now: datetime | None = None) -> str:
    """Date line for the system prompt: ONLY date and weekday, no time, on purpose. A system prompt that
    changes every minute breaks the provider's prompt cache every minute; date-only keeps the cache alive
    all day (GoClaw pattern). The exact time comes from the ``get_datetime`` tool when really needed."""
    p = get_date_time_parts(time_zone, now)
    return (
        f"Hôm nay là {p.weekday}, ngày {p.date} (giờ Việt Nam). "
        "Cần giờ chính xác thì dùng tool get_datetime, đừng tự đoán."
    )


def is_valid_timezone(time_zone: str) -> bool:
    """Is it a valid IANA zone? Used in the env schema at boot."""
    return _zone(time_zone) is not None
