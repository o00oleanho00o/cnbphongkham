# ported from: src/conversation/usage-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring."""

from __future__ import annotations

import pytest

from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.usage_store import UsageStoreImpl
from pema_contracts.agent_turn import TokenUsage, TurnSource

pytestmark = pytest.mark.db


async def _record_turn(
    usage: UsageStoreImpl, env: ClinicEnv, account_id: str, thread_id: str, u: TokenUsage
) -> int:
    """Lượt trọn vẹn: mở rồi chốt - hai bước tách rời đúng như production."""
    turn_id = await usage.open_agent_turn(env.clinic_id, account_id, thread_id)
    await usage.finish_agent_turn(env.clinic_id, turn_id, u)
    return turn_id


def _tokens(input_tokens: int, output_tokens: int, total_tokens: int, steps: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens, steps=steps
    )


async def test_usage_store_open_agent_turn_defaults_source_to_message(env: ClinicEnv) -> None:
    """openAgentTurn không truyền source thì cột source ghi 'message' - lời gọi cũ không phải sửa"""
    usage = UsageStoreImpl(env.db)
    turn_id = await usage.open_agent_turn(env.clinic_id, "acc-source", "t-1")
    source = await env.scalar("SELECT source FROM agent.usage WHERE id = :id", id=turn_id)
    assert source == "message"


async def test_usage_store_open_agent_turn_with_schedule_source_stores_that_value(env: ClinicEnv) -> None:
    """openAgentTurn truyền source='schedule' thì ghi đúng giá trị đó"""
    usage = UsageStoreImpl(env.db)
    turn_id = await usage.open_agent_turn(env.clinic_id, "acc-source", "t-1", TurnSource.SCHEDULE)
    source = await env.scalar("SELECT source FROM agent.usage WHERE id = :id", id=turn_id)
    assert source == "schedule"


async def test_usage_store_records_and_totals_usage_per_thread(env: ClinicEnv) -> None:
    """ghi và tổng hợp usage theo thread"""
    usage = UsageStoreImpl(env.db)
    await _record_turn(usage, env, "acc-1", "t-1", _tokens(100, 20, 120, 1))
    await _record_turn(usage, env, "acc-1", "t-1", _tokens(200, 30, 230, 3))
    await _record_turn(usage, env, "acc-1", "t-khac", _tokens(50, 5, 55, 1))

    totals = await usage.get_thread_usage_totals(env.clinic_id, "acc-1", "t-1")
    assert totals.turns == 2
    assert totals.total_tokens == 350


async def test_usage_store_thread_without_turns_totals_zero(env: ClinicEnv) -> None:
    """thread chưa có lượt nào trả về 0"""
    usage = UsageStoreImpl(env.db)
    totals = await usage.get_thread_usage_totals(env.clinic_id, "acc-1", "t-trong")
    assert (totals.turns, totals.total_tokens) == (0, 0)


async def test_usage_store_daily_stats_group_correctly_and_filter_by_account(env: ClinicEnv) -> None:
    """thống kê theo ngày gộp đúng và lọc theo account"""
    usage = UsageStoreImpl(env.db)
    await _record_turn(usage, env, "acc-daily", "t-1", _tokens(10, 1, 11, 1))
    await _record_turn(usage, env, "acc-daily", "t-2", _tokens(20, 2, 22, 1))
    await _record_turn(usage, env, "acc-1", "t-1", _tokens(999, 9, 1008, 1))  # another account: not counted

    days = await usage.get_daily_usage(env.clinic_id, "acc-daily", "2000-01-01", "Asia/Ho_Chi_Minh")
    assert len(days) == 1  # cùng ngày hôm nay
    assert days[0].turns == 2
    assert days[0].input_tokens == 30
    assert days[0].output_tokens == 3

    # Mốc since ở tương lai -> không có gì
    assert await usage.get_daily_usage(env.clinic_id, "acc-daily", "2999-01-01", "Asia/Ho_Chi_Minh") == []


async def test_usage_store_groups_by_vietnam_day_not_utc_day(env: ClinicEnv) -> None:
    """gom theo ngày VN, không phải ngày UTC - đúng bug overview đang vá"""
    # Chèn thẳng (không qua open_agent_turn) để ép created_at về đúng mốc 20:00Z 30/07 = 03:00 sáng 31/07 giờ VN.
    # ``substr(created_at,1,10)`` kiểu cũ sẽ gom vào '2026-07-30'; ``day_key_of`` phải gom đúng vào ngày VN
    # '2026-07-31'.
    await env.execute(
        "INSERT INTO agent.usage (clinic_id, account_id, thread_id, input_tokens, output_tokens, total_tokens, "
        "steps, created_at) VALUES (:c, 'acc-vn-boundary', 't-1', 5, 1, 6, 1, '2026-07-30T20:00:00.000Z')",
        c=env.clinic_id,
    )
    usage = UsageStoreImpl(env.db)

    days_vn = await usage.get_daily_usage(env.clinic_id, "acc-vn-boundary", "2000-01-01", "Asia/Ho_Chi_Minh")
    assert len(days_vn) == 1
    assert days_vn[0].day == "2026-07-31"

    days_utc = await usage.get_daily_usage(env.clinic_id, "acc-vn-boundary", "2000-01-01", "UTC")
    assert days_utc[0].day == "2026-07-30"


async def test_usage_store_daily_stats_are_newest_day_first(env: ClinicEnv) -> None:
    """(thêm) giữ thứ tự DESC (mới nhất trước) như hành vi cũ của câu SQL"""
    for created_at in ("2026-07-29T05:00:00.000Z", "2026-07-31T05:00:00.000Z", "2026-07-30T05:00:00.000Z"):
        await env.execute(
            "INSERT INTO agent.usage (clinic_id, account_id, thread_id, created_at) "
            "VALUES (:c, 'acc-order', 't-1', :at)",
            c=env.clinic_id,
            at=created_at,
        )
    days = await UsageStoreImpl(env.db).get_daily_usage(env.clinic_id, "acc-order", "2000-01-01", "UTC")
    assert [d.day for d in days] == ["2026-07-31", "2026-07-30", "2026-07-29"]


async def test_usage_store_account_stats_count_today_from_the_given_start_instant(env: ClinicEnv) -> None:
    """(thêm) get_account_stats: mốc 'hôm nay' là tham số (đầu ngày VN = 17:00Z hôm trước), không phải 00:00 UTC"""
    for created_at in (
        "2026-07-30T16:00:00.000Z",
        "2026-07-30T19:00:00.000Z",
    ):  # 23:00 hôm trước / 02:00 hôm nay (VN)
        await env.execute(
            "INSERT INTO agent.usage (clinic_id, account_id, thread_id, total_tokens, created_at) "
            "VALUES (:c, 'acc-stats', 't-1', 10, :at)",
            c=env.clinic_id,
            at=created_at,
        )
    stats = await UsageStoreImpl(env.db).get_account_stats(
        env.clinic_id, "acc-stats", "2026-07-30T17:00:00.000Z"
    )
    assert stats.account_id == "acc-stats"
    assert (stats.turns_today, stats.tokens_today) == (1, 10)
