# ported from: src/server/overview-stats.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Kịch bản đúng bug đã vá (mục 11 thiết kế scheduler): xem dashboard lúc trước 07:00 sáng giờ VN, "Tin hôm nay" phải
khớp đếm tay theo ngày VN - đo bằng mốc cố định thay vì phụ thuộc giờ chạy test thật để không rơi vào loại "test xanh
vô nghĩa" (chỉ đúng tình cờ vì test chạy giữa trưa).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pema.conversation.overview_stats import OverviewAccountStats, OverviewStats, get_system_info
from pema.conversation.pg_testing import ClinicEnv

START_OF_VN_31 = "2026-07-30T17:00:00.000Z"


async def _insert_message_at(env: ClinicEnv, account_id: str, created_at: str) -> None:
    """Chèn thẳng để ép được created_at, mô phỏng tin gửi ở một mốc cụ thể."""
    await env.execute(
        "INSERT INTO agent.history (clinic_id, account_id, thread_id, role, content, created_at) "
        "VALUES (:c, :a, 't-1', 'user', 'nội dung', :at)",
        c=env.clinic_id,
        a=account_id,
        at=created_at,
    )


@pytest.mark.db
async def test_get_account_stats_message_at_2am_vn_counts_as_today_when_the_start_is_the_right_vn_day(
    env: ClinicEnv,
) -> None:
    """getAccountStats - messagesToday theo mốc ràng buộc (ngày VN): tin lúc 02:00 sáng giờ VN vẫn tính là 'hôm nay'"""
    # 19:00Z 30/07 = 02:00 31/07 giờ VN. Mốc đầu ngày VN 31/07 = 17:00Z 30/07 (đúng giá trị start_of_day_utc trả
    # ra) - route thật tính bằng start_of_day_utc(tz).
    await _insert_message_at(env, "acc-1", "2026-07-30T19:00:00.000Z")
    stats = await OverviewStats(env.db).get_account_stats(env.clinic_id, "acc-1", START_OF_VN_31)
    assert stats.messages_today == 1


@pytest.mark.db
async def test_get_account_stats_message_at_11pm_the_evening_before_vn_is_not_today(env: ClinicEnv) -> None:
    """getAccountStats - messagesToday theo mốc ràng buộc (ngày VN): tin lúc 23:00 tối hôm trước giờ VN KHÔNG tính là 'hôm nay'"""
    # 16:00Z 30/07 = 23:00 30/07 giờ VN - trước mốc đầu ngày VN 31/07 1 tiếng.
    await _insert_message_at(env, "acc-2", "2026-07-30T16:00:00.000Z")
    stats = await OverviewStats(env.db).get_account_stats(env.clinic_id, "acc-2", START_OF_VN_31)
    assert stats.messages_today == 0


@pytest.mark.db
async def test_get_account_stats_messages_total_counts_everything_messages_today_only_after_the_start(
    env: ClinicEnv,
) -> None:
    """getAccountStats - messagesToday theo mốc ràng buộc (ngày VN): messagesTotal đếm mọi tin, messagesToday chỉ đếm tin sau mốc truyền vào"""
    await _insert_message_at(env, "acc-1", "2026-07-30T19:00:00.000Z")  # hôm nay (VN)
    await _insert_message_at(env, "acc-1", "2020-01-01T00:00:00.000Z")  # tin rất cũ
    stats = await OverviewStats(env.db).get_account_stats(env.clinic_id, "acc-1", START_OF_VN_31)
    assert stats.messages_total == 2
    assert stats.messages_today == 1


@pytest.mark.db
async def test_get_account_stats_account_without_messages_returns_zeros_without_error(env: ClinicEnv) -> None:
    """getAccountStats - messagesToday theo mốc ràng buộc (ngày VN): account chưa có tin nào trả về 0, không lỗi"""
    stats = await OverviewStats(env.db).get_account_stats(env.clinic_id, "acc-trong", START_OF_VN_31)
    assert stats == OverviewAccountStats(
        threads=0, contacts=0, memories=0, messages_total=0, messages_today=0
    )


@dataclass
class _Llm:
    provider: str
    model: str
    base_url: str
    api_key: str
    has_override: bool = False


def test_get_system_info_llm_is_configured_only_with_key_model_and_a_base_url_when_needed() -> None:
    """(thêm) daCauHinh: đủ key + model (+ base URL cho openai-compatible) mới là đã cấu hình"""
    ok = get_system_info(_Llm("openai-compatible", "qwen3-8b", "http://localhost:11434/v1", "k"))
    no_url = get_system_info(_Llm("openai-compatible", "qwen3-8b", "", "k"))
    vendor = get_system_info(_Llm("anthropic", "claude-x", "", "k"))
    no_key = get_system_info(_Llm("anthropic", "claude-x", "", ""))

    assert ok.llm is not None
    assert ok.llm.configured is True
    assert no_url.llm is not None
    assert no_url.llm.configured is False
    assert vendor.llm is not None
    assert vendor.llm.configured is True
    assert no_key.llm is not None
    assert no_key.llm.configured is False
    assert get_system_info().llm is None
    assert ok.uptime_seconds >= 0
