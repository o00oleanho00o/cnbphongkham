# ported from: src/shared/zone-time.ts
"""Wall clock <-> UTC conversion for IANA time zones. Pure module: no env, no DB, no logger.

Forced deviation: luxon is replaced by ``zoneinfo`` (stdlib, ``tzdata`` installed). Instants are
exchanged as UTC ISO 8601 strings with a ``Z`` suffix and millisecond precision, exactly the shape
of JS ``toISOString()``, because every time column of the original stores that string and the
ported tests compare against it. ``datetime`` objects are used internally; callers on Postgres
convert at the edge.

Why not add a fixed +07:00 offset: Asia/Ho_Chi_Minh has no DST, but the zone is configuration
(``BOT_TIMEZONE``): someone who sets Europe/Paris gets DST at once and a hard-coded offset is wrong
twice a year.

An invalid zone falls back to UTC instead of raising: a misconfigured ``BOT_TIMEZONE`` must not kill
an agent turn or a scheduler tick.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def _safe_zone(time_zone: str) -> ZoneInfo:
    """Invalid zone -> UTC (see module docstring)."""
    if not time_zone:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def to_iso_z(moment: datetime) -> str:
    """UTC ISO string with milliseconds and ``Z`` (JS ``toISOString()``)."""
    utc = moment.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _parse_iso_utc(utc_iso: str) -> datetime | None:
    text = utc_iso.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _wall_to_utc(naive: datetime, zone: ZoneInfo) -> datetime:
    """Wall time in ``zone`` -> UTC instant.

    ``fold=0`` picks the first occurrence of an ambiguous time (DST fall back) and, for a wall time
    that does not exist (DST spring forward), applies the offset before the jump, which lands on the
    same instant luxon gives (it moves forward by the length of the gap).
    """
    return naive.replace(tzinfo=zone, fold=0).astimezone(UTC)


def zoned_wall_clock_to_utc(date: str, time: str, time_zone: str) -> str | None:
    """Wall clock (separate ``date`` and ``time`` in ``time_zone``) -> UTC ISO.

    The one guard against the most dangerous LLM mistake with times: parsing a datetime string that
    carries no zone in the SERVER zone ("3 pm" becomes 22:00 Vietnam time on a UTC VPS). Taking
    ``date`` and ``time`` apart plus an explicit zone leaves no way for the spelling of the string to
    change its meaning.

    Returns ``None`` for an invalid date/time (bad format, 30 Feb, 25:99) so the caller can report it
    properly instead of crashing on a string the model invented.
    """
    if not _DATE_RE.match(date) or not _TIME_RE.match(time):
        return None
    time_text = time if time.count(":") == 2 else f"{time}:00"
    try:
        naive = datetime.fromisoformat(f"{date}T{time_text}")
    except ValueError:
        return None
    return to_iso_z(_wall_to_utc(naive, _safe_zone(time_zone)))


def start_of_day_utc(time_zone: str, now: datetime | None = None) -> str:
    """00:00:00 of "today" in ``time_zone``, as UTC ISO, to compare with ``created_at`` (also UTC).

    Fixes the "today is the UTC day" bug: ``now()`` truncated at 00:00 UTC is 07:00 in Vietnam, wrong in
    both directions depending on when you look.
    """
    zone = _safe_zone(time_zone)
    moment = (now or datetime.now(UTC)).astimezone(zone)
    start = datetime(moment.year, moment.month, moment.day)
    return to_iso_z(_wall_to_utc(start, zone))


def deferred_run_at_utc(time_zone: str, hour: int, now: datetime | None = None) -> str:
    """HH:00:00 of TOMORROW in ``time_zone``: where a 'once' job blocked by the daily cap is moved.

    Deliberately not 00:00:00 (an earlier version was, then corrected): moving to exactly midnight turns
    a 23:50 reminder into a 10-minute postponement and drops every deferred job on one instant just
    after the cap resets, a burst of dozens of messages ``SCHEDULER_SEND_GAP_MS`` apart, exactly the
    rhythm of a bot on a personal account. ``hour`` (``SCHEDULER_DEFERRED_RUN_HOUR``, default 8) spreads
    this away from midnight.

    ALWAYS tomorrow, whether or not ``now`` is past ``hour`` today: one day is added BEFORE the hour is
    set. A job blocked in the morning waits for the whole of tomorrow, as the cap notice promised. It
    adds a CALENDAR day in the zone, not a hard 24 hours (DST zones have 23/25-hour days).
    """
    zone = _safe_zone(time_zone)
    moment = (now or datetime.now(UTC)).astimezone(zone)
    tomorrow = datetime(moment.year, moment.month, moment.day) + timedelta(days=1)
    wall = tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
    return to_iso_z(_wall_to_utc(wall, zone))


def day_key_of(utc_iso: str, time_zone: str) -> str:
    """Day key ``YYYY-MM-DD`` of a UTC instant, read in ``time_zone``.

    The reverse of ``start_of_day_utc``: used to GROUP in application code (usage store) instead of
    cutting the UTC string in SQL, which is only right for the UTC day, not the Vietnamese day.

    ``utc_iso`` is always produced by the system (a DB column or ``to_iso_z``), so an invalid instant is a
    programming error: raise instead of silently returning a bogus key that corrupts a grouping.
    """
    parsed = _parse_iso_utc(utc_iso)
    if parsed is None:
        raise ValueError(f'day_key_of: invalid UTC instant "{utc_iso}"')
    return parsed.astimezone(_safe_zone(time_zone)).strftime("%Y-%m-%d")


def today_key(time_zone: str, now: datetime | None = None) -> str:
    """Day key of "now" in ``time_zone``: for the overview and the scheduler's daily proactive cap."""
    return day_key_of(to_iso_z(now or datetime.now(UTC)), time_zone)
