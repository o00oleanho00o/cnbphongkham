# ported from: src/scheduler/proactive-send-counter-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The key is ``scope_key`` (``account:thread`` for ``staff_assistant``) instead of ``(account_id, thread_id)``. The
last group is new: real concurrency on Postgres, the claim that replaces the single SQLite writer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from pema.scheduler.proactive_send_counter_store import ProactiveCounter
from pema.scheduler.testing_env import Env

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
ACC = "acc-1"


def scope(thread: str) -> str:
    return f"{ACC}:{thread}"


async def test_get_proactive_counter_no_row_yet_returns_count_0_notice_not_sent(make_env: EnvMaker) -> None:
    """chưa có dòng nào thì trả count=0, noticeSent=false"""
    env = make_env()
    got = await env.deps.counters.get_proactive_counter(env.clinic_id, scope("t-trong"), "2026-08-01")
    assert got == ProactiveCounter(count=0, notice_sent=False)


async def test_add_proactive_send_count_accumulates_the_amount_over_calls_without_overwriting(
    make_env: EnvMaker,
) -> None:
    """cộng dồn đúng amount qua nhiều lần gọi (không ghi đè)"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-cong-don"), "2026-08-01", 3)
    await store.add_proactive_send_count(env.clinic_id, scope("t-cong-don"), "2026-08-01", 2)
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-cong-don"), "2026-08-01")).count == 5


async def test_add_proactive_send_count_amount_zero_or_negative_is_a_no_op_no_junk_row(
    make_env: EnvMaker,
) -> None:
    """amount <= 0 thì no-op, không tạo dòng rác"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-amount-0"), "2026-08-01", 0)
    await store.add_proactive_send_count(env.clinic_id, scope("t-amount-am"), "2026-08-01", -5)
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-amount-0"), "2026-08-01")).count == 0
    assert env.row("SELECT count(*) FROM agent.proactive_send_counters WHERE clinic_id = :c") == (0,)


async def test_add_proactive_send_count_another_day_key_is_an_independent_counter(make_env: EnvMaker) -> None:
    """khác ngày (day_key khác) là bộ đếm ĐỘC LẬP, không cộng lẫn nhau"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-khac-ngay"), "2026-08-01", 3)
    await store.add_proactive_send_count(env.clinic_id, scope("t-khac-ngay"), "2026-08-02", 1)
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-khac-ngay"), "2026-08-01")).count == 3
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-khac-ngay"), "2026-08-02")).count == 1


async def test_add_proactive_send_count_another_thread_same_account_same_day_is_independent(
    make_env: EnvMaker,
) -> None:
    """khác thread (cùng account, cùng ngày) là bộ đếm ĐỘC LẬP"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-a"), "2026-08-03", 3)
    await store.add_proactive_send_count(env.clinic_id, scope("t-b"), "2026-08-03", 1)
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-a"), "2026-08-03")).count == 3
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-b"), "2026-08-03")).count == 1


async def test_mark_proactive_cap_notice_sent_marks_notice_sent_without_touching_count(
    make_env: EnvMaker,
) -> None:
    """đánh dấu noticeSent=true, không đụng count"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-notice"), "2026-08-04", 5)
    await store.mark_proactive_cap_notice_sent(env.clinic_id, scope("t-notice"), "2026-08-04")
    counter = await store.get_proactive_counter(env.clinic_id, scope("t-notice"), "2026-08-04")
    assert counter.notice_sent is True
    assert counter.count == 5, "mark không được đụng count"


async def test_mark_proactive_cap_notice_sent_before_any_count_row_still_creates_the_row(
    make_env: EnvMaker,
) -> None:
    """mark trước khi có dòng count nào (thread chưa từng gửi) vẫn tạo được dòng"""
    env = make_env()
    store = env.deps.counters
    await store.mark_proactive_cap_notice_sent(env.clinic_id, scope("t-mark-truoc"), "2026-08-05")
    got = await store.get_proactive_counter(env.clinic_id, scope("t-mark-truoc"), "2026-08-05")
    assert got == ProactiveCounter(count=0, notice_sent=True)


async def test_add_proactive_send_count_prunes_rows_older_than_keep_since_day_key(make_env: EnvMaker) -> None:
    """dòng cũ hơn keepSinceDayKey bị xoá, dòng từ hôm đó trở đi vẫn còn"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-prune-cu"), "2026-07-20", 2)
    await store.add_proactive_send_count(env.clinic_id, scope("t-prune-moi"), "2026-08-01", 2)

    await store.add_proactive_send_count(
        env.clinic_id, scope("t-prune-trigger"), "2026-08-10", 1, "2026-07-25"
    )

    assert (await store.get_proactive_counter(env.clinic_id, scope("t-prune-cu"), "2026-07-20")).count == 0
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-prune-moi"), "2026-08-01")).count == 2


async def test_add_proactive_send_count_does_not_prune_when_no_keep_since_day_key_is_given(
    make_env: EnvMaker,
) -> None:
    """KHÔNG dọn gì khi không truyền keepSinceDayKey (tránh mất dữ liệu ngoài ý muốn)"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-khong-don"), "2026-06-01", 4)
    await store.add_proactive_send_count(env.clinic_id, scope("t-khong-don-2"), "2026-08-11", 1)
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-khong-don"), "2026-06-01")).count == 4


async def test_try_reserve_proactive_slot_no_row_yet_max_1_still_wins_the_insert_branch(
    make_env: EnvMaker,
) -> None:
    """chưa có dòng nào (max=1) vẫn giành được - nhánh INSERT không qua WHERE"""
    env = make_env()
    store = env.deps.counters
    assert (
        await store.try_reserve_proactive_slot(env.clinic_id, scope("t-reserve-moi"), "2026-08-01", 1) is True
    )
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-reserve-moi"), "2026-08-01")).count == 1


async def test_try_reserve_proactive_slot_below_max_wins_and_adds_exactly_1(make_env: EnvMaker) -> None:
    """còn dưới max thì giành được, cộng đúng 1"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-reserve-con-cho"), "2026-08-01", 2)
    assert (
        await store.try_reserve_proactive_slot(env.clinic_id, scope("t-reserve-con-cho"), "2026-08-01", 3)
        is True
    )
    assert (
        await store.get_proactive_counter(env.clinic_id, scope("t-reserve-con-cho"), "2026-08-01")
    ).count == 3


async def test_try_reserve_proactive_slot_already_at_max_does_not_win_count_unchanged(
    make_env: EnvMaker,
) -> None:
    """đã bằng max thì KHÔNG giành được, count không đổi"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-reserve-day"), "2026-08-01", 3)
    assert (
        await store.try_reserve_proactive_slot(env.clinic_id, scope("t-reserve-day"), "2026-08-01", 3)
        is False
    )
    got = await store.get_proactive_counter(env.clinic_id, scope("t-reserve-day"), "2026-08-01")
    assert got.count == 3, "giành hỏng thì KHÔNG được đụng count"


async def test_try_reserve_proactive_slot_another_thread_is_independent(make_env: EnvMaker) -> None:
    """khác thread là độc lập - thread A đầy không chặn thread B"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-reserve-day-a"), "2026-08-01", 3)
    assert (
        await store.try_reserve_proactive_slot(env.clinic_id, scope("t-reserve-day-a"), "2026-08-01", 3)
        is False
    )
    assert (
        await store.try_reserve_proactive_slot(env.clinic_id, scope("t-reserve-trong-b"), "2026-08-01", 3)
        is True
    )


async def test_try_reserve_proactive_slot_a_policy_cap_of_zero_never_wins_and_touches_nothing(
    make_env: EnvMaker,
) -> None:
    """(clinic) max_per_day = 0 ('không bao giờ nhắn chủ động') không giành được và không tạo dòng"""
    env = make_env()
    store = env.deps.counters
    assert await store.try_reserve_proactive_slot(env.clinic_id, scope("t-zero"), "2026-08-01", 0) is False
    assert env.row("SELECT count(*) FROM agent.proactive_send_counters WHERE clinic_id = :c") == (0,)


async def test_refund_proactive_slot_subtracts_exactly_1(make_env: EnvMaker) -> None:
    """trừ đúng 1"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-refund-tru"), "2026-08-01", 5)
    await store.refund_proactive_slot(env.clinic_id, scope("t-refund-tru"), "2026-08-01")
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-refund-tru"), "2026-08-01")).count == 4


async def test_refund_proactive_slot_is_floored_at_0_even_with_no_row(make_env: EnvMaker) -> None:
    """kẹp sàn 0 - không xuống âm dù chưa có dòng nào"""
    env = make_env()
    store = env.deps.counters
    await store.refund_proactive_slot(env.clinic_id, scope("t-refund-chua-co-dong"), "2026-08-01")
    assert (
        await store.get_proactive_counter(env.clinic_id, scope("t-refund-chua-co-dong"), "2026-08-01")
    ).count == 0


async def test_reset_all_proactive_counters_wipes_every_row_of_the_clinic(make_env: EnvMaker) -> None:
    """xoá sạch mọi dòng của mọi account/thread/ngày"""
    env = make_env()
    store = env.deps.counters
    await store.add_proactive_send_count(env.clinic_id, scope("t-reset-1"), "2026-08-01", 3)
    await store.add_proactive_send_count(env.clinic_id, "acc-khac:t-reset-2", "2026-08-01", 5)

    await store.reset_all_proactive_counters(env.clinic_id)

    assert (await store.get_proactive_counter(env.clinic_id, scope("t-reset-1"), "2026-08-01")).count == 0
    assert (await store.get_proactive_counter(env.clinic_id, "acc-khac:t-reset-2", "2026-08-01")).count == 0


async def test_try_reserve_proactive_slot_race_of_many_concurrent_reservers_wins_exactly_the_cap(
    make_env: EnvMaker,
) -> None:
    """(Postgres) 30 giành chỗ ĐỒNG THỜI, trần 7: đúng 7 bên thắng - bằng chứng cho 'trần đếm nguyên tử'"""
    env = make_env()
    store = env.deps.counters
    results = await asyncio.gather(
        *(
            store.try_reserve_proactive_slot(env.clinic_id, scope("t-race"), "2026-08-01", 7)
            for _ in range(30)
        )
    )
    assert sum(results) == 7
    assert (await store.get_proactive_counter(env.clinic_id, scope("t-race"), "2026-08-01")).count == 7


async def test_try_reserve_cap_notice_exactly_one_of_many_concurrent_callers_wins_the_right(
    make_env: EnvMaker,
) -> None:
    """(Mục 1, vòng 3) N job cùng bị chặn cùng lúc: chỉ ĐÚNG 1 bên giành được quyền báo trần; revert trả quyền lại"""
    env = make_env()
    store = env.deps.counters
    results = await asyncio.gather(
        *(
            store.try_reserve_cap_notice(env.clinic_id, scope("t-notice-race"), "2026-08-01")
            for _ in range(12)
        )
    )
    assert sum(results) == 1
    await store.revert_cap_notice(env.clinic_id, scope("t-notice-race"), "2026-08-01")
    assert await store.try_reserve_cap_notice(env.clinic_id, scope("t-notice-race"), "2026-08-01") is True
