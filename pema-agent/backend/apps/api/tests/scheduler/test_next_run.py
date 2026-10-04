# ported from: src/scheduler/next-run.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Pure module, every instant explicit.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime

from pema.scheduler.next_run import DueJob, compute_next_run, decide_due_action, grace_seconds_for
from pema_contracts.scheduler import CronSchedule, EverySchedule, OnceSchedule, ParsedSchedule


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def under_two_process_zones(fn: Callable[[], None]) -> None:
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


# ------------------------------------------------------------------------------ computeNextRun - once


def test_compute_next_run_once_returns_run_at_utc_untouched_independent_of_from_and_now() -> None:
    """trả nguyên runAtUtc, không phụ thuộc from/now"""
    schedule = OnceSchedule(run_at_utc="2026-08-01T08:00:00.000Z")
    assert (
        compute_next_run(schedule, utc("2000-01-01T00:00:00Z"), utc("2099-01-01T00:00:00Z"))
        == "2026-08-01T08:00:00.000Z"
    )


# ------------------------------------------------------------------------------ computeNextRun - every


def test_compute_next_run_every_on_time_next_is_from_plus_interval() -> None:
    """đúng hạn (now = from): mốc kế = from + interval"""
    assert (
        compute_next_run(EverySchedule(minutes=30), utc("2026-08-01T07:00:00Z")) == "2026-08-01T07:30:00.000Z"
    )


def test_compute_next_run_every_missed_3_hours_jumps_to_nearest_future_slot_on_original_grid() -> None:
    """lỡ 3 tiếng với every 30 phút: nhảy thẳng tới mốc tương lai gần nhất trên LƯỚI GỐC, không dồn 6 lượt"""
    schedule = EverySchedule(minutes=30)
    from_ = utc("2026-08-01T07:00:00Z")  # the instant it SHOULD have run
    now = utc("2026-08-01T10:00:00Z")  # the bot just came back, 3 hours late

    next_run = compute_next_run(schedule, from_, now)

    # Still on the 30 minute grid anchored at ``from_`` (07:00, 07:30, 08:00 ... 10:00, 10:30)
    assert next_run == "2026-08-01T10:30:00.000Z"
    # Must be in the FUTURE of ``now``: adding naively from+interval (07:30) would still be in the past and the
    # next tick would see it due again at once, producing a burst
    assert next_run is not None
    assert utc(next_run) > now


def test_compute_next_run_every_now_before_from_does_not_jump_backwards_in_time() -> None:
    """now sớm hơn from (không nên xảy ra) vẫn không nhảy lùi thời gian"""
    next_run = compute_next_run(
        EverySchedule(minutes=10), utc("2026-08-01T07:00:00Z"), utc("2026-08-01T06:00:00Z")
    )
    assert next_run == "2026-08-01T07:10:00.000Z"


# ------------------------------------------------------------------------------ computeNextRun - cron


def test_compute_next_run_cron_7am_in_ho_chi_minh_is_00_00_utc_not_07_00_independent_of_process_tz() -> None:
    """cron "0 7 * * *" với tz=Asia/Ho_Chi_Minh ra mốc UTC 00:00, KHÔNG phải 07:00 - không phụ thuộc TZ tiến trình"""

    def check() -> None:
        schedule = CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh")
        # 2026-08-01T10:00:00Z = 17:00 in Vietnam on 01/08, already past that day's 7:00
        now = utc("2026-08-01T10:00:00Z")
        next_run = compute_next_run(schedule, now)
        assert next_run == "2026-08-02T00:00:00.000Z", "7h sáng VN 02/08 = 00:00 UTC 02/08"
        assert next_run is not None
        assert "T07:00:00" not in next_run, "sai dấu hiệu: lấy nhầm giờ hệ điều hành thay vì tz truyền vào"

    under_two_process_zones(check)


def test_compute_next_run_cron_broken_expression_returns_none_instead_of_raising() -> None:
    """biểu thức hỏng trả về null thay vì ném lỗi (phòng thủ - schedule-parser đã chặn từ trước)"""
    schedule = CronSchedule(expr="khong-hop-le", time_zone="UTC")
    assert compute_next_run(schedule, datetime.now(UTC)) is None


# ------------------------------------------------------------------------------------ graceSecondsFor


def test_grace_seconds_for_once_uses_once_grace_minutes_in_seconds() -> None:
    """once dùng thẳng onceGraceMinutes quy đổi giây"""
    schedule = OnceSchedule(run_at_utc="2026-08-01T00:00:00.000Z")
    assert grace_seconds_for(schedule, 10) == 600


def test_grace_seconds_for_every_half_period_clamped_below_when_the_period_is_too_short() -> None:
    """every: nửa chu kỳ, kẹp trần dưới 120s khi chu kỳ quá ngắn"""
    assert grace_seconds_for(EverySchedule(minutes=2), 10) == 120  # half a period = 60s


def test_grace_seconds_for_every_half_period_clamped_above_when_the_period_is_too_long() -> None:
    """every: nửa chu kỳ, kẹp trần trên 7200s khi chu kỳ quá dài"""
    assert grace_seconds_for(EverySchedule(minutes=1000), 10) == 7200  # half a period = 30000s


def test_grace_seconds_for_every_half_period_inside_the_allowed_range_is_kept() -> None:
    """every: nửa chu kỳ nằm trong khoảng cho phép thì giữ nguyên"""
    assert grace_seconds_for(EverySchedule(minutes=30), 10) == 900  # half a period = 900s


def test_grace_seconds_for_cron_estimates_half_period_from_two_next_slots_daily_cron_clamped_above() -> None:
    """cron: ước lượng nửa chu kỳ từ 2 mốc kế tiếp - cron ngày kẹp trần trên"""
    schedule = CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh")
    # Vietnam has no DST so a daily period is always 86400s -> half 43200s, clamped to 7200
    assert grace_seconds_for(schedule, 10, utc("2026-08-01T00:00:00Z")) == 7200


# ---------------------------------------------------------------------------------------- decideDueAction


def due(schedule: ParsedSchedule, next_run_at: datetime) -> DueJob:
    return DueJob(schedule=schedule, next_run_at=next_run_at, once_grace_minutes=10)


def test_decide_due_action_once_late_inside_grace_runs() -> None:
    """once trễ TRONG grace -> run"""
    next_run_at = utc("2026-08-01T15:00:00Z")
    now = utc("2026-08-01T15:05:00Z")  # 5 minutes late, grace 10 minutes
    schedule = OnceSchedule(run_at_utc="2026-08-01T15:00:00.000Z")
    assert decide_due_action(due(schedule, next_run_at), now) == "run"


def test_decide_due_action_once_2_hours_late_beyond_grace_is_run_late_not_dropped() -> None:
    """once trễ 2 tiếng (QUÁ grace) -> run-late, không phải bị vứt"""
    next_run_at = utc("2026-08-01T15:00:00Z")
    now = utc("2026-08-01T17:00:00Z")  # 120 minutes late, grace 10 minutes
    schedule = OnceSchedule(run_at_utc="2026-08-01T15:00:00.000Z")
    assert decide_due_action(due(schedule, next_run_at), now) == "run-late"


def test_decide_due_action_every_late_inside_grace_runs_catch_up_once() -> None:
    """every trễ TRONG grace -> run (chạy bù 1 lần)"""
    next_run_at = utc("2026-08-01T07:00:00Z")
    now = utc("2026-08-01T07:05:00Z")  # 5 minutes late, grace of every-30m = 15 minutes
    assert decide_due_action(due(EverySchedule(minutes=30), next_run_at), now) == "run"


def test_decide_due_action_every_30_minutes_missed_3_hours_beyond_grace_skips_forward_no_backlog() -> None:
    """every 30 phút lỡ 3 tiếng (QUÁ grace) -> skip-forward, không dồn backlog"""
    next_run_at = utc("2026-08-01T07:00:00Z")
    now = utc("2026-08-01T10:00:00Z")  # 180 minutes late, grace of every-30m = 15 minutes
    assert decide_due_action(due(EverySchedule(minutes=30), next_run_at), now) == "skip-forward"


def test_decide_due_action_cron_missed_several_days_skips_forward_same_group_as_every_not_once() -> None:
    """cron lỡ nhiều ngày (QUÁ grace) -> skip-forward, cùng nhóm với every chứ không phải once"""
    next_run_at = utc("2026-08-01T00:00:00Z")  # 7:00 Vietnam on 01/08
    now = utc("2026-08-05T00:00:00Z")  # 4 days late
    schedule = CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh")
    assert decide_due_action(due(schedule, next_run_at), now) == "skip-forward"
