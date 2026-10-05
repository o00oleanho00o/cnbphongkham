# ported from: src/shared/hourly-rate-limit.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import time

from pema.shared.hourly_rate_limit import (
    HourlyRateLimit,
    RateReasonInfo,
    create_hourly_rate_limit,
)

HOUR = 60 * 60 * 1000


def _make(limit: int) -> HourlyRateLimit:
    return create_hourly_rate_limit(
        limit=lambda: limit,
        build_reason=lambda info: f"dùng {info.used}/{info.limit}, chờ {info.wait_minutes} phút",
    )


def _now() -> float:
    return time.time() * 1000


# ------------------------------------------------------------------ createHourlyRateLimit


def test_create_hourly_rate_limit_allows_up_to_the_ceiling_then_blocks() -> None:
    """cho tới đúng trần rồi mới chặn"""
    rl = _make(3)
    for i in range(1, 4):
        assert rl.check("t1").ok is True, f"lần {i}"
    assert rl.check("t1").ok is False


def test_create_hourly_rate_limit_counts_each_key_separately() -> None:
    """đếm riêng từng key"""
    rl = _make(2)
    rl.check("t1")
    rl.check("t1")
    assert rl.check("t1").ok is False
    assert rl.check("t2").ok is True


def test_create_hourly_rate_limit_sliding_window_old_use_frees_a_slot() -> None:
    """cửa sổ TRƯỢT: lần cũ rơi khỏi 1 giờ là có thêm suất, không phải chờ hết cả giờ"""
    rl = _make(3)
    t0 = _now()
    rl.check("t1", t0)
    rl.check("t1", t0 + 30 * 60_000)
    rl.check("t1", t0 + 40 * 60_000)
    assert rl.check("t1", t0 + 50 * 60_000).ok is False
    assert rl.check("t1", t0 + HOUR + 1000).ok is True


def test_create_hourly_rate_limit_build_reason_gets_used_limit_and_wait_minutes() -> None:
    """buildReason nhận đúng số đã dùng, trần và số phút phải chờ"""
    rl = _make(3)
    t0 = _now()
    for _ in range(3):
        rl.check("t1", t0)
    blocked = rl.check("t1", t0 + 20 * 60_000)
    assert blocked.ok is False
    assert blocked.reason == "dùng 3/3, chờ 40 phút"


def test_create_hourly_rate_limit_minimum_wait_is_one_minute() -> None:
    """số phút chờ tối thiểu là 1 - không bao giờ nói 'chờ 0 phút'"""
    rl = _make(1)
    t0 = _now()
    rl.check("t1", t0)
    # Right at the edge of the window: less than 1 minute left
    blocked = rl.check("t1", t0 + HOUR - 1000)
    assert blocked.ok is False
    assert "chờ 1 phút" in blocked.reason


def test_create_hourly_rate_limit_cold_keys_are_swept_from_memory() -> None:
    """key nguội bị dọn khỏi bộ nhớ (hồi quy rò rỉ Map ở V2.4)"""
    rl = _make(3)
    t0 = _now()
    for i in range(500):
        rl.check(f"cu-{i}", t0)
    assert rl.so_key_dang_giu() == 500

    rl.check("moi", t0 + HOUR + 1000)
    assert rl.so_key_dang_giu() == 1, "500 key nguội phải bị dọn, chỉ còn key vừa dùng"

    for i in range(1, 4):
        assert rl.check("cu-0", t0 + HOUR + 2000).ok is True, f"suất {i} sau khi dọn"


def test_create_hourly_rate_limit_ceiling_is_read_at_call_time() -> None:
    """trần đọc lúc GỌI chứ không phải lúc tạo - env đổi là ăn ngay"""
    state = {"max": 1}
    rl = create_hourly_rate_limit(limit=lambda: state["max"], build_reason=lambda _info: "hết")
    assert rl.check("t1").ok is True
    assert rl.check("t1").ok is False
    state["max"] = 5
    assert rl.check("t1").ok is True, "nới trần thì lần tiếp theo đi lọt"


def test_create_hourly_rate_limit_reset_clears_all_counting_state() -> None:
    """reset xóa sạch trạng thái đếm"""
    rl = _make(1)
    rl.check("t1")
    assert rl.check("t1").ok is False
    rl.reset()
    assert rl.check("t1").ok is True


def test_create_hourly_rate_limit_two_limiters_are_independent() -> None:
    """hai bộ đếm độc lập nhau - tool này đầy không chặn tool kia"""
    a = _make(1)
    b = _make(1)
    a.check("t1")
    assert a.check("t1").ok is False
    assert b.check("t1").ok is True


def test_reason_info_is_a_plain_value() -> None:
    """RateReasonInfo là giá trị thuần (Python: dataclass bất biến)"""
    info = RateReasonInfo(used=1, limit=2, wait_minutes=3)
    assert (info.used, info.limit, info.wait_minutes) == (1, 2, 3)


# ------------------------------------------------------- hoanSuat - give a slot back on failure


def test_hoan_suat_refunded_slot_can_be_used_again() -> None:
    """hoàn xong thì suất đó dùng lại được"""
    rl = _make(1)
    assert rl.check("t1").ok is True
    assert rl.check("t1").ok is False, "trần 1, lần 2 phải bị chặn"

    rl.hoan_suat("t1")
    assert rl.check("t1").ok is True, "việc hỏng mà vẫn ăn suất là khóa người dùng vì thứ họ chưa nhận được"


def test_hoan_suat_refunding_n_times_returns_exactly_n_slots() -> None:
    """hoàn N lần thì trả đúng N suất, không hơn"""
    rl = _make(3)
    rl.check("t1")
    rl.check("t1")
    rl.check("t1")

    rl.hoan_suat("t1")
    rl.hoan_suat("t1")
    assert rl.check("t1").ok is True, "suất 1"
    assert rl.check("t1").ok is True, "suất 2"
    assert rl.check("t1").ok is False, "hoàn 2 mà mở 3 là trần rò"


def test_hoan_suat_superfluous_calls_never_make_the_count_negative() -> None:
    """gọi thừa KHÔNG làm số đếm âm - trần vẫn giữ đúng"""
    rl = _make(2)
    # 5 refunds on an empty counter. If the count went negative, more than the ceiling would pass after.
    for _ in range(5):
        rl.hoan_suat("t1")

    assert rl.check("t1").ok is True
    assert rl.check("t1").ok is True
    assert rl.check("t1").ok is False, "gọi hoàn thừa mà nới được trần là lỗ hổng"


def test_hoan_suat_refund_of_one_key_does_not_touch_another() -> None:
    """hoàn của key này không đụng key kia"""
    rl = _make(1)
    rl.check("t1")
    rl.check("t2")

    rl.hoan_suat("t1")
    assert rl.check("t1").ok is True
    assert rl.check("t2").ok is False, "hoàn nhầm key là một người mở khoá cho người khác"


def test_hoan_suat_on_a_key_of_only_expired_stamps_also_sweeps_the_key() -> None:
    """hoàn trên key toàn mốc QUÁ HẠN thì DỌN LUÔN key khỏi bộ nhớ

    The earlier version of this case asserted "the ceiling is still 1 after refunding an expired stamp" and
    that was an EMPTY assertion: ``check`` re-filters with its own cutoff, so the count does not change
    whether ``hoan_suat`` filters or not. What the filter really protects is MEMORY: without it ``hoan_suat``
    writes the dead stamps back into the map and the key lives forever. It needs TWO stamps or more: with one,
    both paths delete the key (``pop()`` empties the list either way).
    """
    rl = _make(3)
    t0 = 1_000_000
    rl.check("t1", t0)
    rl.check("t1", t0 + 1)
    rl.check("t1", t0 + 2)
    assert rl.so_key_dang_giu() == 1

    rl.hoan_suat("t1", t0 + HOUR + 10)
    assert rl.so_key_dang_giu() == 0, (
        "không lọc thì `pop()` chỉ bỏ MỘT mốc chết, hai mốc chết còn lại ghi ngược vào Map và key sống mãi"
    )


def test_hoan_suat_does_not_create_a_credit_for_the_future() -> None:
    """hoàn KHÔNG tạo ra suất bù cho tương lai"""
    rl = _make(1)
    t0 = 1_000_000
    assert rl.check("t1", t0).ok is True
    rl.hoan_suat("t1", t0 + HOUR + 1)

    assert rl.check("t1", t0 + HOUR + 2).ok is True
    assert rl.check("t1", t0 + HOUR + 3).ok is False, "trần phải vẫn là 1"
