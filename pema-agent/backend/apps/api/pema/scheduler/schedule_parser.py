# ported from: src/scheduler/schedule-parser.ts
"""Normalise and validate a schedule coming from the LLM tool or the admin UI into a ``ParsedSchedule``.

PURE module: no DB, no env, no logger. ``time_zone`` and ``min_interval_minutes`` arrive as parameters (the
same habit as ``botEnabledForThread`` and ``parseIncomingMessage`` in the original). In exchange it can be
called from the tool, the admin route and the tests without mocking anything.

This is the FIRST line of defence against a bot messaging too densely (the highest risk of getting an account
locked in the whole project): an ``every`` below the threshold and a cron denser than the threshold are both
rejected AT CREATION, not discovered at send time. The daily cap at the delivery layer is the last net, not
the only one.

Forced deviations: ``cron-parser`` becomes ``croniter`` (6-field expressions keep the seconds FIRST, like
cron-parser, through ``second_at_beginning``; 7 fields are rejected as cron-parser does); JS ``Date`` becomes
an aware ``datetime``; the result is a small dataclass pair instead of a TS union. The contract types
(``ParsedSchedule``, ``ScheduleInput``) live in ``pema_contracts.scheduler``; a raw input built with
``model_construct`` (to carry an invalid number) is re-validated here, exactly like the untyped LLM input."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter  # type: ignore[import-untyped]

from pema.shared.zone_time import to_iso_z, zoned_wall_clock_to_utc
from pema_contracts.scheduler import (
    CronInput,
    CronSchedule,
    EveryInput,
    EverySchedule,
    OnceAtInput,
    OnceInMinutesInput,
    OnceSchedule,
    ParsedSchedule,
    ScheduleInput,
)

MAX_SCHEDULE_MINUTES = 525600
"""One year in minutes: the ceiling the original put on ``inMinutes`` and ``every.minutes`` in its zod schema.
Without it ``now + minutes`` overflows the date range (``RangeError`` in JS, ``OverflowError`` here) and the
admin route would answer 500 instead of a readable 400. The contract types (A) have no upper bound, so the
parser enforces it."""

__all__ = [
    "MAX_SCHEDULE_MINUTES",
    "ParseScheduleError",
    "ParseScheduleOk",
    "ParseScheduleParams",
    "ParseScheduleResult",
    "cron_iter_for",
    "parse_schedule",
]


@dataclass(frozen=True)
class ParseScheduleParams:
    time_zone: str
    """Zone used to read ``date``/``time`` of ``once`` and to validate ``cron``."""
    min_interval_minutes: int
    """Threshold that blocks a too dense ``every``/``cron``: pass ``SCHEDULER_MIN_INTERVAL_MINUTES``."""
    now: datetime | None = None
    """"Now"; defaults to the system clock, tests always pass it explicitly."""


@dataclass(frozen=True)
class ParseScheduleOk:
    schedule: ParsedSchedule
    ok: bool = True


@dataclass(frozen=True)
class ParseScheduleError:
    error: str
    ok: bool = False


type ParseScheduleResult = ParseScheduleOk | ParseScheduleError


def cron_iter_for(expr: str, time_zone: str, start: datetime) -> croniter:
    """A croniter positioned at ``start`` in ``time_zone`` (the ``tz`` + ``currentDate`` of cron-parser).

    ``tz`` is MANDATORY: without it the library would use the OS zone of the process (measured in the
    original: not passing ``tz`` gave the same result as the right ``BOT_TIMEZONE`` on a UTC+7 dev machine and
    a 7 hour shift on a UTC VPS). ``start`` is a parameter so the callers stay pure: they do not depend on the
    system clock at the time of the call. Raises ``ValueError`` for an invalid expression (5 or 6 fields
    only)."""
    fields = expr.split()
    if len(fields) not in (5, 6):
        raise ValueError(f"cron expression must have 5 or 6 fields, got {len(fields)}")
    try:
        zone = ZoneInfo(time_zone) if time_zone else ZoneInfo("UTC")
    except (KeyError, ValueError, OSError):
        zone = ZoneInfo("UTC")
    return croniter(expr, start.astimezone(zone), second_at_beginning=True)


def parse_schedule(schedule_input: ScheduleInput, params: ParseScheduleParams) -> ParseScheduleResult:
    now = params.now or datetime.now(UTC)
    if isinstance(schedule_input, OnceAtInput | OnceInMinutesInput):
        return _parse_once(schedule_input, params.time_zone, now)
    if isinstance(schedule_input, EveryInput):
        return _parse_every(schedule_input, params.min_interval_minutes)
    return _parse_cron(schedule_input, params.time_zone, params.min_interval_minutes, now)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _parse_once(
    schedule_input: OnceAtInput | OnceInMinutesInput, time_zone: str, now: datetime
) -> ParseScheduleResult:
    if isinstance(schedule_input, OnceInMinutesInput):
        if not _is_positive_int(schedule_input.in_minutes):
            return ParseScheduleError("Số phút phải là số nguyên dương, ví dụ 30 (nhắc sau 30 phút).")
        if schedule_input.in_minutes > MAX_SCHEDULE_MINUTES:
            return ParseScheduleError(f"Số phút tối đa là {MAX_SCHEDULE_MINUTES} (1 năm).")
        run_at_utc: str | None = to_iso_z(now + timedelta(minutes=schedule_input.in_minutes))
    else:
        run_at_utc = zoned_wall_clock_to_utc(schedule_input.date, schedule_input.time, time_zone)
        if run_at_utc is None:
            return ParseScheduleError(
                f'Ngày hoặc giờ không hợp lệ: "{schedule_input.date} {schedule_input.time}". '
                "Dùng định dạng ngày YYYY-MM-DD và giờ HH:mm."
            )

    # Block at creation instead of letting the job sit forever without ever being picked (Hermes raises
    # ValueError the same way). A job that ALREADY EXISTS and missed its time is another matter: that is the
    # job of ``decide_due_action`` (grace / fast-forward), not of the parser.
    if datetime.fromisoformat(run_at_utc.replace("Z", "+00:00")) <= now:
        return ParseScheduleError("Thời điểm đã chọn nằm trong quá khứ - hãy chọn một mốc trong tương lai.")

    return ParseScheduleOk(OnceSchedule(run_at_utc=run_at_utc))


def _parse_every(schedule_input: EveryInput, min_interval_minutes: int) -> ParseScheduleResult:
    if not _is_positive_int(schedule_input.minutes):
        return ParseScheduleError("Số phút lặp lại phải là số nguyên dương.")
    if schedule_input.minutes > MAX_SCHEDULE_MINUTES:
        return ParseScheduleError(f"Số phút lặp lại tối đa là {MAX_SCHEDULE_MINUTES} (1 năm).")
    # ``every 1m`` = 1440 messages a day into a personal account: exactly the signature that gets a Zalo
    # account locked. Blocking here is much cheaper than blocking at the send cap when the job already ran.
    if schedule_input.minutes < min_interval_minutes:
        return ParseScheduleError(
            f"Lặp lại tối thiểu mỗi {min_interval_minutes} phút để tránh nhắn quá dày, dễ bị Zalo coi là spam."  # noqa: E501
        )
    return ParseScheduleOk(EverySchedule(minutes=schedule_input.minutes))


def _parse_cron(
    schedule_input: CronInput, time_zone: str, min_interval_minutes: int, now: datetime
) -> ParseScheduleResult:
    # cron-parser treats an empty string as valid (it does not throw), so it has to be blocked first.
    if schedule_input.expr.strip() == "":
        return ParseScheduleError("Biểu thức cron không được để trống.")

    try:
        interval = cron_iter_for(schedule_input.expr, time_zone, now)
        first: datetime = interval.get_next(datetime)
        second: datetime = interval.get_next(datetime)
    except Exception:  # croniter raises several types (CroniterBadCronError, ValueError, KeyError)
        return ParseScheduleError(f'Biểu thức cron không hợp lệ: "{schedule_input.expr}".')

    # ``* * * * *`` must die here: the same threshold rule as ``every``, measured as the distance between two
    # consecutive instants instead of guessing from the syntax of the expression.
    gap_minutes = (second - first).total_seconds() / 60
    if gap_minutes < min_interval_minutes:
        gap_text = f"{gap_minutes:g}"
        return ParseScheduleError(
            f"Lịch cron chạy quá dày (hai lần kế tiếp cách nhau {gap_text} phút) - "
            f"tối thiểu {min_interval_minutes} phút để tránh spam."
        )

    return ParseScheduleOk(CronSchedule(expr=schedule_input.expr, time_zone=time_zone))
