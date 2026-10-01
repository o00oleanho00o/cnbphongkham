# ported from: src/scheduler/schedule-parser.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, no setup needed. Every instant is explicit through ``now`` (the lesson of "a green test that
proves nothing" learned with read-zip-entry).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.scheduler.schedule_parser import (
    ParseScheduleError,
    ParseScheduleParams,
    ParseScheduleResult,
    parse_schedule,
)
from pema_contracts.scheduler import (
    CronInput,
    CronSchedule,
    EveryInput,
    EverySchedule,
    OnceAtInput,
    OnceInMinutesInput,
    OnceSchedule,
    ParsedSchedule,
)

NOW = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
HCM = "Asia/Ho_Chi_Minh"


def under_two_process_zones(fn: Callable[[], None]) -> None:
    """Run ``fn`` under two different PROCESS zones and require the same result: the parser must not shift
    with the clock of the machine running it. Where ``time.tzset`` does not exist (Windows) the function
    runs once: it takes an explicit zone anyway, so the platform-independent twin of each test covers it."""
    tzset: Callable[[], None] | None = getattr(time, "tzset", None)
    if tzset is None:
        fn()
        return
    original = os.environ.get("TZ")
    try:
        for zone in ("UTC", "America/New_York"):
            os.environ["TZ"] = zone
            tzset()
            fn()
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        tzset()


def ok(result: ParseScheduleResult) -> ParsedSchedule:
    if isinstance(result, ParseScheduleError):
        raise AssertionError(result.error)
    return result.schedule


def loi(result: ParseScheduleResult) -> str:
    assert isinstance(result, ParseScheduleError), "kỳ vọng bị từ chối"
    return result.error


def params(time_zone: str = "UTC", minimum: int = 5) -> ParseScheduleParams:
    return ParseScheduleParams(time_zone=time_zone, min_interval_minutes=minimum, now=NOW)


# ------------------------------------------------------------------------------------------- once


def test_parse_schedule_once_date_time_converts_to_right_utc_independent_of_process_tz() -> None:
    """date+time quy đổi đúng UTC, không phụ thuộc TZ tiến trình - test quan trọng nhất phase"""

    def check() -> None:
        result = parse_schedule(OnceAtInput(date="2026-08-01", time="15:00"), params(HCM))
        assert ok(result) == OnceSchedule(run_at_utc="2026-08-01T08:00:00.000Z")

    under_two_process_zones(check)


def test_parse_schedule_once_in_minutes_counts_from_the_given_now_without_timezone() -> None:
    """inMinutes tính từ `now` truyền vào, không dính timezone"""
    result = parse_schedule(OnceInMinutesInput(in_minutes=30), params(HCM))
    assert ok(result) == OnceSchedule(run_at_utc="2026-07-31T00:30:00.000Z")


@pytest.mark.parametrize("in_minutes", [0, -5, 1.5])
def test_parse_schedule_once_in_minutes_zero_negative_or_fractional_is_rejected(in_minutes: float) -> None:
    """inMinutes <= 0 hoặc không nguyên bị từ chối"""
    raw = OnceInMinutesInput.model_construct(in_minutes=in_minutes)  # bypass the type to carry the bad value
    assert "số nguyên dương" in loi(parse_schedule(raw, params()))


def test_parse_schedule_once_invalid_date_gives_readable_vietnamese_error_without_throwing() -> None:
    """ngày/giờ không hợp lệ -> lỗi tiếng Việt đọc được (không throw)"""
    result = parse_schedule(OnceAtInput(date="2026-02-30", time="15:00"), params(HCM))
    assert "không hợp lệ" in loi(result)


def test_parse_schedule_once_a_time_in_the_past_is_rejected() -> None:
    """mốc đã ở quá khứ bị từ chối - job không tồn tại thì không có gì để bù trễ"""
    result = parse_schedule(OnceAtInput(date="2026-07-30", time="08:00"), params(HCM))
    assert "quá khứ" in loi(result)


# ------------------------------------------------------------------------------------------- every


def test_parse_schedule_every_one_minute_is_rejected_with_explanation_the_1440_messages_a_day_case() -> None:
    """every 1 phút bị từ chối kèm giải thích - đúng ca 1440 tin/ngày"""
    assert "tối thiểu mỗi 5 phút" in loi(parse_schedule(EveryInput(minutes=1), params()))


def test_parse_schedule_every_exactly_the_threshold_is_accepted_inclusive_boundary() -> None:
    """đúng bằng ngưỡng thì được chấp nhận (biên bao gồm)"""
    assert ok(parse_schedule(EveryInput(minutes=5), params())) == EverySchedule(minutes=5)


@pytest.mark.parametrize("minutes", [0, -10, 2.5])
def test_parse_schedule_every_non_positive_or_fractional_is_rejected(minutes: float) -> None:
    """số không dương hoặc không nguyên bị từ chối"""
    raw = EveryInput.model_construct(minutes=minutes)
    assert "số nguyên dương" in loi(parse_schedule(raw, params()))


# -------------------------------------------------------------------------------------------- cron


def test_parse_schedule_cron_every_minute_is_rejected_with_explanation_must_die_at_validation() -> None:
    """ "* * * * *" bị từ chối kèm giải thích - phải chết ở bước validate, không đợi lúc gửi"""

    def check() -> None:
        result = parse_schedule(CronInput(expr="* * * * *"), params(HCM))
        assert "quá dày" in loi(result)

    under_two_process_zones(check)


def test_parse_schedule_cron_valid_schedule_is_accepted_keeping_expr_and_time_zone() -> None:
    """lịch hợp lệ được chấp nhận, giữ nguyên expr + timeZone"""
    result = parse_schedule(CronInput(expr="0 7 * * *"), params(HCM))
    assert ok(result) == CronSchedule(expr="0 7 * * *", time_zone=HCM)


@pytest.mark.parametrize("expr", ["khong-phai-cron", "", "   ", "* * * * * * * *"])
def test_parse_schedule_cron_garbage_or_empty_is_rejected_without_raising(expr: str) -> None:
    """biểu thức rác hoặc rỗng bị từ chối, không ném lỗi ra ngoài"""
    raw = CronInput.model_construct(expr=expr)  # CronInput itself forbids "" (min_length)
    assert isinstance(parse_schedule(raw, params()), ParseScheduleError)
