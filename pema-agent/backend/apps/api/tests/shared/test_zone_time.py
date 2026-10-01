# ported from: src/shared/zone-time.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, every instant explicit: nothing depends on the clock or the zone of the machine running the
tests (the lesson of "a green test that proves nothing" from read-zip-entry).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.shared.zone_time import (
    day_key_of,
    deferred_run_at_utc,
    start_of_day_utc,
    today_key,
    zoned_wall_clock_to_utc,
)

HCM = "Asia/Ho_Chi_Minh"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


# ----------------------------------------------------------------- zonedWallClockToUtc


def test_zoned_wall_clock_to_utc_vn_wall_time_to_utc_offset_plus_7_independent_of_process_tz() -> None:
    """giờ tường VN -> UTC đúng offset +7, không phụ thuộc TZ tiến trình"""
    tzset: Callable[[], None] | None = getattr(time, "tzset", None)  # POSIX only
    if tzset is None:
        pytest.skip("time.tzset unavailable on this platform; the function takes an explicit zone anyway")
    original = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "UTC"
        tzset()
        under_utc = zoned_wall_clock_to_utc("2026-08-01", "15:00", HCM)
        os.environ["TZ"] = "America/New_York"
        tzset()
        under_ny = zoned_wall_clock_to_utc("2026-08-01", "15:00", HCM)
        assert under_utc == "2026-08-01T08:00:00.000Z"
        assert under_ny == "2026-08-01T08:00:00.000Z"
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        tzset()


def test_zoned_wall_clock_to_utc_vn_wall_time_is_plus_7_with_explicit_zone() -> None:
    """(platform-independent twin of the test above) 15:00 Ho Chi Minh is 08:00Z"""
    assert zoned_wall_clock_to_utc("2026-08-01", "15:00", HCM) == "2026-08-01T08:00:00.000Z"


def test_zoned_wall_clock_to_utc_dst_zone_offset_changes_around_spring_forward() -> None:
    """zone có DST (Europe/Paris) hai bên mốc chuyển giờ xuân 2026-03-29: offset đổi theo, không phải hằng số"""
    assert zoned_wall_clock_to_utc("2026-03-28", "12:00", "Europe/Paris") == "2026-03-28T11:00:00.000Z"
    assert zoned_wall_clock_to_utc("2026-03-30", "12:00", "Europe/Paris") == "2026-03-30T10:00:00.000Z"


@pytest.mark.parametrize(
    ("date", "clock", "why"),
    [
        ("2026-13-40", "15:00", "month 13 does not exist"),
        ("2026-02-30", "15:00", "30 Feb does not exist"),
        ("2026-08-01", "25:99", "25:99 is not a valid time"),
        ("khong-phai-ngay", "15:00", "garbage string"),
        ("", "", "empty strings"),
    ],
)
def test_zoned_wall_clock_to_utc_nonexistent_calendar_date_or_time_is_none(
    date: str, clock: str, why: str
) -> None:
    """ngày/giờ không tồn tại trên lịch -> null, không ném lỗi"""
    assert zoned_wall_clock_to_utc(date, clock, HCM) is None, why


def test_zoned_wall_clock_to_utc_invalid_timezone_falls_back_to_utc_instead_of_raising() -> None:
    """timezone hỏng rơi về UTC thay vì throw - không được chết lượt agent/scheduler"""
    assert zoned_wall_clock_to_utc("2026-08-01", "15:00", "Khong/Ton_Tai") == "2026-08-01T15:00:00.000Z"
    assert zoned_wall_clock_to_utc("2026-08-01", "15:00", "") == "2026-08-01T15:00:00.000Z"


# ----------------------------------------------------------------- startOfDayUtc


def test_start_of_day_utc_0300_vn_still_belongs_to_the_vn_day_not_00z() -> None:
    """03:00 sáng giờ VN ngày 31/07 vẫn thuộc mốc đầu ngày 31/07 (VN), KHÔNG phải 00:00Z"""
    now = _utc("2026-07-30T20:00:00Z")
    start = start_of_day_utc(HCM, now)
    assert start == "2026-07-30T17:00:00.000Z"
    assert start != "2026-07-31T00:00:00Z"


def test_start_of_day_utc_invalid_timezone_falls_back_to_utc_calendar_day() -> None:
    """timezone hỏng rơi về UTC: đầu ngày tính thẳng theo lịch UTC"""
    now = _utc("2026-07-30T20:00:00Z")
    assert start_of_day_utc("Khong/Ton_Tai", now) == "2026-07-30T00:00:00.000Z"


def test_start_of_day_utc_without_now_uses_the_system_clock_and_iso_shape() -> None:
    """không truyền now thì lấy giờ hệ thống hiện tại (chỉ kiểm không throw + đúng dạng ISO)"""
    start = start_of_day_utc(HCM)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\.000Z$", start)


# ----------------------------------------------------------------- dayKeyOf


def test_day_key_of_groups_by_vn_day_not_utc_day() -> None:
    """gom theo ngày VN, không phải ngày UTC - đúng lỗi getDailyUsage/overview-stats đang vá"""
    assert day_key_of("2026-07-30T20:00:00.000Z", HCM) == "2026-07-31"
    assert day_key_of("2026-07-30T20:00:00.000Z", "UTC") == "2026-07-30"


def test_day_key_of_exact_vn_midnight_boundary() -> None:
    """đúng ranh giới nửa đêm VN (17:00Z là mốc đổi ngày)"""
    assert day_key_of("2026-07-30T16:59:59.999Z", HCM) == "2026-07-30"
    assert day_key_of("2026-07-30T17:00:00.000Z", HCM) == "2026-07-31"


def test_day_key_of_invalid_timezone_falls_back_to_utc() -> None:
    """timezone hỏng rơi về UTC thay vì throw"""
    assert day_key_of("2026-07-30T20:00:00.000Z", "Khong/Ton_Tai") == "2026-07-30"


def test_day_key_of_invalid_utc_instant_raises() -> None:
    """mốc UTC không hợp lệ ném lỗi rõ ràng - utcIso luôn do hệ thống sinh, hỏng là lỗi lập trình"""
    with pytest.raises(ValueError, match="invalid UTC instant"):
        day_key_of("khong-phai-iso", HCM)


# ----------------------------------------------------------------- deferredRunAtUtc


def test_deferred_run_at_utc_configured_hour_of_tomorrow_not_midnight() -> None:
    """đúng giờ cấu hình của NGÀY MAI, KHÔNG PHẢI 00:00 - mốc trưa giờ VN"""
    now = _utc("2026-08-01T03:00:00.000Z")
    assert deferred_run_at_utc(HCM, 8, now) == "2026-08-02T01:00:00.000Z"


def test_deferred_run_at_utc_always_tomorrow_even_before_todays_hour() -> None:
    """LUÔN là ngày mai dù `now` đã qua giờ cấu hình của HÔM NAY hay chưa - không phải 'lần kế tiếp của giờ đó'"""
    late_night = _utc("2026-08-01T16:50:00.000Z")  # 23:50 Vietnam 01/08
    assert deferred_run_at_utc(HCM, 8, late_night) == "2026-08-02T01:00:00.000Z"
    early_morning = _utc("2026-08-01T18:00:00.000Z")  # 01:00 Vietnam 02/08, before 8:00 of the same day
    assert deferred_run_at_utc(HCM, 8, early_morning) == "2026-08-03T01:00:00.000Z"


def test_deferred_run_at_utc_hour_parameter_has_real_effect() -> None:
    """khác giờ cấu hình cho ra khác mốc - tham số hour có tác dụng thật, không hard-code 8"""
    now = _utc("2026-08-01T03:00:00.000Z")
    assert deferred_run_at_utc(HCM, 0, now) == "2026-08-01T17:00:00.000Z"
    assert deferred_run_at_utc(HCM, 23, now) == "2026-08-02T16:00:00.000Z"


def test_deferred_run_at_utc_invalid_timezone_falls_back_to_utc() -> None:
    """timezone hỏng rơi về UTC thay vì throw"""
    now = _utc("2026-08-01T03:00:00.000Z")
    assert deferred_run_at_utc("Khong/Ton_Tai", 8, now) == "2026-08-02T08:00:00.000Z"


def test_deferred_run_at_utc_dst_zone_adds_one_calendar_day_not_24_hours() -> None:
    """zone có DST (Europe/Paris) vẫn cộng ĐÚNG 1 NGÀY LỊCH qua mốc chuyển giờ, không phải cộng cứng 24 tiếng"""
    now = _utc("2026-03-28T11:00:00.000Z")  # 12:00 Paris (CET +1)
    assert deferred_run_at_utc("Europe/Paris", 8, now) == "2026-03-29T06:00:00.000Z"


# ----------------------------------------------------------------- todayKey


def test_today_key_equals_day_key_of_now() -> None:
    """tương đương dayKeyOf(now.toISOString(), tz) - chỉ là tiện dùng thẳng"""
    now = _utc("2026-07-30T20:00:00Z")
    assert today_key(HCM, now) == "2026-07-31"
    assert today_key("UTC", now) == "2026-07-30"


def test_today_key_without_now_has_the_day_key_shape() -> None:
    """không truyền now thì lấy giờ hệ thống hiện tại (chỉ kiểm đúng dạng khóa ngày)"""
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", today_key(HCM))
