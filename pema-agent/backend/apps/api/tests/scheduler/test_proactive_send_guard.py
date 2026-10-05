# ported from: src/scheduler/proactive-send-guard.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The test environment sets ``SCHEDULER_MAX_PROACTIVE_PER_DAY=3`` and ``SCHEDULER_SEND_GAP_MS=30`` (a low cap and
a short gap to run fast, not the real 20 s). The scope key is ``account:thread`` (``staff_assistant``). The last
groups are new: the clinic-wide channel switchboard, the cap key chosen by the policy hook, and the contract
``ProactiveSendGuard`` implementation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.scheduler.proactive_send_guard import PgProactiveSendGuard, default_scope_key
from pema.scheduler.testing_env import ACC, Env
from pema.shared.zone_time import today_key
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyProfileKey,
    ProactiveCap,
)

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
TZ = "Asia/Ho_Chi_Minh"
CAP = 3
TUNING: dict[str, str | int | float | bool] = {
    "SCHEDULER_MAX_PROACTIVE_PER_DAY": CAP,
    "SCHEDULER_SEND_GAP_MS": 30,
}


def make_thread(env: Env, thread_id: str) -> None:
    env.make_thread(thread_id)


def scope(thread: str) -> str:
    return default_scope_key(ACC, thread)


NOW = datetime(2026, 8, 1, 1, 0, tzinfo=UTC)

# ------------------------------------------------------------------------- checkAccountAndThreadReady


async def test_check_account_and_thread_ready_account_not_running_blocks(make_env: EnvMaker) -> None:
    """account không chạy thì chặn"""
    env = make_env(tuning=TUNING, online=False)
    result = await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-bat-ky", NOW)
    assert result.ok is False
    assert "không chạy" in result.reason


async def test_check_account_and_thread_ready_running_account_and_valid_thread_passes(
    make_env: EnvMaker,
) -> None:
    """account chạy + thread hợp lệ (tồn tại + bot_enabled) thì qua"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-preflight-ok")
    result = await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-preflight-ok", NOW)
    assert result.ok is True


# ------------------------------------------------------------------- checkProactiveSendGuard - the 3 conditions


async def test_check_proactive_send_guard_account_never_attached_is_blocked_at_the_first_condition(
    make_env: EnvMaker,
) -> None:
    """account chưa từng attach (không chạy) thì chặn ngay ở điều kiện đầu tiên"""
    env = make_env(tuning=TUNING, online=False)
    r = await env.deps.guard.check_proactive_send_guard(
        env.clinic_id, ACC, "t-bat-ky", scope("t-bat-ky"), TZ, NOW, CAP
    )
    assert r.ok is False
    assert "không chạy" in r.reason


async def test_check_proactive_send_guard_running_account_but_thread_never_seen_is_blocked(
    make_env: EnvMaker,
) -> None:
    """account chạy nhưng thread chưa từng ghi nhận trong hệ thống thì chặn"""
    env = make_env(tuning=TUNING)
    r = await env.deps.guard.check_proactive_send_guard(
        env.clinic_id, ACC, "t-chua-tung-thay", scope("t-chua-tung-thay"), TZ, NOW, CAP
    )
    assert r.ok is False
    assert "chưa từng ghi nhận" in r.reason


async def test_check_proactive_send_guard_thread_exists_but_bot_disabled_is_blocked(
    make_env: EnvMaker,
) -> None:
    """thread tồn tại nhưng bot_enabled=0 (tắt trên dashboard) thì chặn"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-tat-bot")
    env.set_bot_enabled("t-tat-bot", False)
    r = await env.deps.guard.check_proactive_send_guard(
        env.clinic_id, ACC, "t-tat-bot", scope("t-tat-bot"), TZ, NOW, CAP
    )
    assert r.ok is False
    assert "đang tắt" in r.reason


async def test_check_proactive_send_guard_running_valid_thread_under_the_cap_passes(
    make_env: EnvMaker,
) -> None:
    """account chạy + thread hợp lệ + chưa chạm trần thì cho qua"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-hop-le")
    r = await env.deps.guard.check_proactive_send_guard(
        env.clinic_id, ACC, "t-hop-le", scope("t-hop-le"), TZ, NOW, CAP
    )
    assert r.ok is True


# ------------------------------------------------------------------- the daily cap (3 in the test)


async def test_daily_cap_counts_per_message_not_per_call(make_env: EnvMaker) -> None:
    """đếm THEO SỐ TIN (count truyền vào recordProactiveSend), không phải theo số lần gọi"""
    env = make_env(tuning=TUNING)
    thread = "t-dem-theo-tin"
    make_thread(env, thread)
    now = datetime(2026, 8, 1, 1, 0, tzinfo=UTC)
    # 1 record but 3 messages (1 long answer cut into 3 parts)
    await env.deps.guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 3, now)
    r = await env.deps.guard.check_proactive_send_guard(
        env.clinic_id, ACC, thread, scope(thread), TZ, now, CAP
    )
    assert r.ok is False, "3 tin trong 1 lần gọi phải tính đủ 3, chạm trần 3 ngay"


async def test_daily_cap_message_n_plus_1_is_blocked_check_does_not_mark_notified(make_env: EnvMaker) -> None:
    """tin thứ N+1 (N=trần) bị chặn; check KHÔNG tự ghi 'đã báo' - phải gọi markProactiveCapNotified mới tính là đã báo"""
    env = make_env(tuning=TUNING)
    thread = "t-cham-tran"
    make_thread(env, thread)
    now = datetime(2026, 8, 1, 1, 0, tzinfo=UTC)
    guard = env.deps.guard

    for i in range(CAP):
        r = await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, now, CAP)
        assert r.ok is True, f"tin thứ {i + 1} (trong trần) phải qua được"
        await guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 1, now)

    # ``check`` is PURE READ (the fix: the "Run now" page checks first and may not send for real, writing inside
    # the check would swallow the notice of the REAL cap hit later)
    first = await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, now, CAP)
    second = await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, now, CAP)
    assert first.ok is False
    assert second.ok is False
    assert "chạm trần" in first.reason
    assert first.notify_cap_hit_once is True, "check không mark thì vẫn phải báo true"
    assert second.notify_cap_hit_once is True, "gọi check nhiều lần không mark - vẫn true, không tự đổi"

    await guard.mark_proactive_cap_notified(env.clinic_id, scope(thread), TZ, now)
    after = await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, now, CAP)
    assert after.ok is False
    assert after.notify_cap_hit_once is False, "đã mark rồi thì không báo lại trong cùng ngày"


async def test_daily_cap_a_new_day_in_vietnam_resets_the_cap_to_0(make_env: EnvMaker) -> None:
    """qua NGÀY MỚI (theo giờ VN) thì trần được reset về 0"""
    env = make_env(tuning=TUNING)
    thread = "t-qua-ngay"
    make_thread(env, thread)
    guard = env.deps.guard
    day1 = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
    await guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 3, day1)
    assert (
        await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, day1, CAP)
    ).ok is False

    day2 = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
    assert (
        await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, day2, CAP)
    ).ok is True


async def test_daily_cap_the_day_flips_at_00_00_vietnam_time_not_00_00_utc(make_env: EnvMaker) -> None:
    """mốc lật ngày là 00:00 GIỜ VN, không phải 00:00 UTC - đúng vá zone-time đã trị ở phase 01"""
    env = make_env(tuning=TUNING)
    thread = "t-lech-mui-gio"
    make_thread(env, thread)
    guard = env.deps.guard
    # 16:00Z 31/07 = 23:00 VN 31/07 (UTC+7) - still the VN day 31/07
    before_midnight = datetime(2026, 7, 31, 16, 0, tzinfo=UTC)
    await guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 3, before_midnight)
    blocked = await guard.check_proactive_send_guard(
        env.clinic_id, ACC, thread, scope(thread), TZ, before_midnight, CAP
    )
    assert blocked.ok is False

    # 18:00Z 31/07 = 01:00 VN 01/08 - SAME UTC day (31/07) but ALREADY the new VN day
    after_midnight = datetime(2026, 7, 31, 18, 0, tzinfo=UTC)
    reset = await guard.check_proactive_send_guard(
        env.clinic_id, ACC, thread, scope(thread), TZ, after_midnight, CAP
    )
    assert reset.ok is True, "phải reset dù còn cùng ngày UTC, vì đã sang ngày VN mới"


async def test_reset_proactive_send_counters_brings_every_counter_to_0(make_env: EnvMaker) -> None:
    """đưa mọi bộ đếm về 0 - dùng để cô lập các ca test với nhau"""
    env = make_env(tuning=TUNING)
    thread = "t-reset"
    make_thread(env, thread)
    guard = env.deps.guard
    await guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 3, NOW)
    assert (
        await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, NOW, CAP)
    ).ok is False
    await guard.reset_proactive_send_counters(env.clinic_id)
    assert (
        await guard.check_proactive_send_guard(env.clinic_id, ACC, thread, scope(thread), TZ, NOW, CAP)
    ).ok is True


# ---------------------------------------------------------------------- enqueueProactiveSend - spaced global queue


async def test_enqueue_proactive_send_two_sends_run_in_sequence_at_least_the_gap_apart(
    make_env: EnvMaker,
) -> None:
    """2 lần gửi (dù khác thread) vẫn chạy tuần tự, cách nhau tối thiểu SCHEDULER_SEND_GAP_MS"""
    env = make_env(tuning=TUNING)
    stamps: list[float] = []

    async def task() -> None:
        stamps.append(time.monotonic())

    await asyncio.gather(
        env.deps.queue.enqueue_proactive_send(task), env.deps.queue.enqueue_proactive_send(task)
    )
    assert len(stamps) == 2
    # test gap = 30ms; leave a 5ms margin for the timer jitter of the operating system
    assert (stamps[1] - stamps[0]) * 1000 >= 25, (
        f"2 lần gửi phải cách nhau gần đúng gap ({(stamps[1] - stamps[0]) * 1000:.0f}ms)"
    )


async def test_enqueue_proactive_send_one_failing_send_does_not_wedge_the_queue(make_env: EnvMaker) -> None:
    """1 lần gửi lỗi không làm kẹt hàng đợi - lần kế tiếp vẫn chạy được"""
    env = make_env(tuning=TUNING)
    ran_second = False

    async def boom() -> None:
        raise RuntimeError("gửi hỏng")

    async def second() -> None:
        nonlocal ran_second
        ran_second = True

    with pytest.raises(RuntimeError, match="gửi hỏng"):
        await env.deps.queue.enqueue_proactive_send(boom)
    await env.deps.queue.enqueue_proactive_send(second)

    assert ran_second is True, "hàng đợi phải sống tiếp sau 1 lần lỗi"


# ------------------------------------------------------------------------ checkProactiveDailyCap - PURE READ


async def test_check_proactive_daily_cap_room_left_passes_and_does_not_add_to_the_count(
    make_env: EnvMaker,
) -> None:
    """còn chỗ thì cho qua, KHÔNG cộng count (khác reserveProactiveSlot)"""
    env = make_env(tuning=TUNING)
    thread = "t-doc-thuan"
    make_thread(env, thread)
    guard = env.deps.guard
    assert (await guard.check_proactive_daily_cap(env.clinic_id, scope(thread), TZ, NOW, CAP)).ok is True
    assert (await guard.check_proactive_daily_cap(env.clinic_id, scope(thread), TZ, NOW, CAP)).ok is True
    counter = await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), today_key(TZ, NOW))
    assert counter.count == 0


async def test_check_proactive_daily_cap_at_the_cap_is_false_with_the_right_notify_flag(
    make_env: EnvMaker,
) -> None:
    """đã chạm trần (do reserveProactiveSlot/recordProactiveSend ghi trước) thì báo false, kèm notifyCapHitOnce đúng"""
    env = make_env(tuning=TUNING)
    thread = "t-doc-cham-tran"
    make_thread(env, thread)
    await env.deps.guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 3, NOW)
    r = await env.deps.guard.check_proactive_daily_cap(env.clinic_id, scope(thread), TZ, NOW, CAP)
    assert r.ok is False
    assert "chạm trần" in r.reason
    assert r.notify_cap_hit_once is True


# --------------------------------------------------------------- reserveProactiveSlot - ATOMIC, a real reservation


async def test_reserve_proactive_slot_room_left_wins_and_adds_1_at_once(make_env: EnvMaker) -> None:
    """còn chỗ thì giành được VÀ CỘNG NGAY 1 vào count (khác checkProactiveDailyCap)"""
    env = make_env(tuning=TUNING)
    thread = "t-reserve-cong-ngay"
    make_thread(env, thread)
    day_key = today_key(TZ, NOW)
    before = (await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), day_key)).count
    r = await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)
    assert r.ok is True
    after = (await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), day_key)).count
    assert after == before + 1, "giành chỗ phải cộng NGAY, không đợi caller tự ghi"


async def test_reserve_proactive_slot_at_the_cap_the_4th_slot_is_not_won(make_env: EnvMaker) -> None:
    """đủ trần (test=3) thì suất thứ 4 KHÔNG giành được, count không đổi"""
    env = make_env(tuning=TUNING)
    thread = "t-reserve-day-tran"
    make_thread(env, thread)
    for i in range(CAP):
        assert (
            await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)
        ).ok is True, f"suất thứ {i + 1} phải giành được"
    r = await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)
    assert r.ok is False
    assert "chạm trần" in r.reason


async def test_reserve_proactive_slot_race_of_two_concurrent_calls_with_one_slot_left_only_one_wins(
    make_env: EnvMaker,
) -> None:
    """race giữa 2 lần gọi ĐỒNG THỜI khi CHỈ CÒN ĐÚNG 1 CHỖ: chỉ 1 bên giành được - đây là điểm chặn race Mục 4"""
    env = make_env(tuning=TUNING)
    thread = "t-reserve-race"
    make_thread(env, thread)
    # take 2/3 slots first (test cap = 3) - exactly 1 slot left
    await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)
    await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)

    a, b = await asyncio.gather(
        env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP),
        env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP),
    )
    assert [a.ok, b.ok].count(True) == 1, "chỉ đúng 1 trong 2 lần gọi được giành suất cuối cùng"


# -------------------------------------------------------- refundProactiveSlot - give back a slot that did not send


async def test_refund_proactive_slot_reserve_then_refund_returns_the_count_to_where_it_was(
    make_env: EnvMaker,
) -> None:
    """hoàn đúng 1 suất - reserve rồi refund thì count trở lại như trước"""
    env = make_env(tuning=TUNING)
    thread = "t-refund"
    make_thread(env, thread)
    day_key = today_key(TZ, NOW)
    await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, NOW, CAP)
    after_reserve = (
        await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), day_key)
    ).count
    await env.deps.guard.refund_proactive_slot(env.clinic_id, scope(thread), TZ, NOW)
    after_refund = (
        await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), day_key)
    ).count
    assert after_refund == after_reserve - 1


async def test_refund_proactive_slot_goes_back_to_the_day_that_was_taken_one_day_off_loses_the_slot_forever(
    make_env: EnvMaker,
) -> None:
    """hoàn suất phải trả về ĐÚNG NGÀY đã giành - lệch một ngày là suất mất vĩnh viễn

    The worst hole of the bug "missing ``now``": the job becomes due at 23:59:50, ``reserve`` takes a slot of day
    D, the send takes 20 s then fails; a refund that reads the REAL clock subtracts day D+1: day D keeps the slot
    forever and day D+1 is silently floored. The cap is the shield against an account lock."""
    env = make_env(tuning=TUNING)
    thread = "t-refund-qua-nua-dem"
    make_thread(env, thread)
    reserved_at = datetime(2026, 8, 1, 16, 59, 50, tzinfo=UTC)  # 23:59:50 VN
    refunded_at = datetime(2026, 8, 1, 17, 0, 10, tzinfo=UTC)  # 00:00:10 VN, next day
    reserved_day = today_key(TZ, reserved_at)
    refunded_day = today_key(TZ, refunded_at)
    assert reserved_day != refunded_day, "hai mốc phải nằm hai ngày khác nhau thì ca này mới có nghĩa"

    await env.deps.guard.reserve_proactive_slot(env.clinic_id, scope(thread), TZ, reserved_at, CAP)
    counters = env.deps.counters
    assert (await counters.get_proactive_counter(env.clinic_id, scope(thread), reserved_day)).count == 1

    # refund with the EXACT instant of the run (the instant of the reserve), NOT the instant the send failed
    await env.deps.guard.refund_proactive_slot(env.clinic_id, scope(thread), TZ, reserved_at)

    assert (await counters.get_proactive_counter(env.clinic_id, scope(thread), reserved_day)).count == 0, (
        "suất của ngày ĐÃ GIÀNH phải được trả lại"
    )
    assert (await counters.get_proactive_counter(env.clinic_id, scope(thread), refunded_day)).count == 0, (
        "ngày hôm sau KHÔNG được bị trừ oan"
    )


async def test_record_proactive_send_does_not_prune_the_row_it_just_wrote_retention_follows_the_run_now(
    make_env: EnvMaker,
) -> None:
    """cộng đếm KHÔNG được dọn mất chính dòng vừa ghi (retention tính theo `now` của lượt)"""
    env = make_env(tuning=TUNING)
    thread = "t-ghi-khong-tu-xoa"
    make_thread(env, thread)
    # an instant deliberately FAR from the real day the test runs - exactly what exposed the bug
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)
    day_key = today_key(TZ, now)
    await env.deps.guard.record_proactive_send(env.clinic_id, scope(thread), TZ, 2, now)
    got = await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), day_key)
    assert got.count == 2, "dòng vừa ghi phải còn - dọn theo giờ thật sẽ xóa mất chính nó"


async def test_refund_proactive_slot_with_count_at_0_floors_at_0_never_negative(make_env: EnvMaker) -> None:
    """refund khi count đang 0 thì kẹp sàn ở 0, không xuống âm"""
    env = make_env(tuning=TUNING)
    thread = "t-refund-am"
    make_thread(env, thread)
    await env.deps.guard.refund_proactive_slot(env.clinic_id, scope(thread), TZ, NOW)
    got = await env.deps.counters.get_proactive_counter(env.clinic_id, scope(thread), today_key(TZ, NOW))
    assert got.count == 0


# ------------------------------------------------------------------------------- clinic additions (new)


def _channel_setting(env: Env, **cols: object) -> None:
    columns = {
        "enabled": True,
        "kill_switch_on": False,
        "daily_cap": None,
        "send_window_start": None,
        "send_window_end": None,
        **cols,
    }
    env.execute(
        "INSERT INTO clinic.channel_setting (clinic_id, channel, enabled, kill_switch_on, daily_cap, "
        "send_window_start, send_window_end) VALUES (:c, 'zalo_personal', :enabled, :kill_switch_on, :daily_cap, "
        "CAST(:send_window_start AS time), CAST(:send_window_end AS time))",
        **columns,
    )


async def test_preflight_a_clinic_without_a_channel_setting_row_has_no_clinic_wide_restriction(
    make_env: EnvMaker,
) -> None:
    """(clinic) không có dòng channel_setting thì không có hạn chế toàn phòng khám (hành vi gốc)"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-1")
    assert (await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-1", NOW)).ok is True


async def test_preflight_the_kill_switch_blocks_every_proactive_send(make_env: EnvMaker) -> None:
    """(clinic) công tắc dừng khẩn cấp của kênh chặn mọi tin chủ động"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-1")
    _channel_setting(env, kill_switch_on=True)
    result = await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-1", NOW)
    assert result.ok is False
    assert "dừng khẩn cấp" in result.reason


async def test_preflight_a_disabled_channel_blocks(make_env: EnvMaker) -> None:
    """(clinic) kênh chưa bật cho phòng khám thì chặn"""
    env = make_env(tuning=TUNING)
    make_thread(env, "t-1")
    _channel_setting(env, enabled=False)
    result = await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-1", NOW)
    assert result.ok is False
    assert "chưa được bật" in result.reason


async def test_preflight_the_send_window_blocks_outside_and_allows_inside_in_vietnam_time(
    make_env: EnvMaker,
) -> None:
    """(clinic) khung giờ gửi 08:00-21:00 giờ VN: 22:00 VN bị chặn, 10:00 VN qua"""
    env = make_env(tuning={**TUNING, "BOT_TIMEZONE": TZ})
    make_thread(env, "t-1")
    _channel_setting(env, send_window_start="08:00", send_window_end="21:00")
    inside = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)  # 10:00 VN
    outside = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)  # 22:00 VN
    assert (await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-1", inside)).ok is True
    blocked = await env.deps.guard.check_account_and_thread_ready(env.clinic_id, ACC, "t-1", outside)
    assert blocked.ok is False
    assert "khung giờ" in blocked.reason


async def test_effective_cap_the_clinic_wide_daily_cap_can_only_lower_the_cap(make_env: EnvMaker) -> None:
    """(clinic) trần của channel_setting chỉ có thể HẠ trần mặc định, không nâng"""
    env = make_env(tuning=TUNING)
    _channel_setting(env, daily_cap=2)
    ctx = _ctx(env, PolicyProfileKey.STAFF_ASSISTANT)
    cap = await env.deps.guard.effective_cap(ctx, PermissivePolicyHooks())
    assert cap.max_per_day == 2
    assert cap.scope_key == f"{ACC}:t-1"


async def test_effective_cap_a_hook_with_no_cap_still_gets_the_default_never_unlimited(
    make_env: EnvMaker,
) -> None:
    """(clinic) hook trả max_per_day=None vẫn nhận trần mặc định - trần là lá chắn chống khoá nick, không tắt âm thầm"""
    env = make_env(tuning=TUNING)

    class NoCapHooks(PermissivePolicyHooks):
        async def proactive_cap(self, ctx: PolicyContext, default_max_per_day: int | None) -> ProactiveCap:
            return ProactiveCap(scope_key=f"patient:{ctx.account_id}", max_per_day=None)

    cap = await env.deps.guard.effective_cap(_ctx(env, PolicyProfileKey.PATIENT_CHANNEL), NoCapHooks())
    assert cap.max_per_day == CAP
    assert cap.scope_key == f"patient:{ACC}"


async def test_pg_proactive_send_guard_implements_the_contract_over_the_same_counter(
    make_env: EnvMaker,
) -> None:
    """(clinic) PgProactiveSendGuard theo hợp đồng ProactiveSendGuard: reserve/refund/notice dùng CHUNG bộ đếm"""
    env = make_env(tuning=TUNING)
    guard = PgProactiveSendGuard(env.deps.counters, env.clinic_id)
    first = await guard.reserve_slot("patient:P025:acc", "2026-08-01", 1)
    second = await guard.reserve_slot("patient:P025:acc", "2026-08-01", 1)
    assert (first.reserved, first.count, first.cap) == (True, 1, 1)
    assert (second.reserved, second.count) == (False, 1)
    await guard.refund_slot("patient:P025:acc", "2026-08-01")
    assert (await guard.reserve_slot("patient:P025:acc", "2026-08-01", 1)).reserved is True

    assert await guard.reserve_cap_notice("patient:P025:acc", "2026-08-01") is True
    assert await guard.reserve_cap_notice("patient:P025:acc", "2026-08-01") is False
    await guard.revert_cap_notice("patient:P025:acc", "2026-08-01")
    assert await guard.reserve_cap_notice("patient:P025:acc", "2026-08-01") is True


def _ctx(env: Env, profile: PolicyProfileKey) -> PolicyContext:
    return PolicyContext(
        clinic_id=env.clinic_id,
        account_id=ACC,
        agent_id="agent-s",
        channel=ChannelKind.ZALO_PERSONAL,
        thread_id="t-1",
        profile=DEFAULT_PROFILES[profile],
    )
