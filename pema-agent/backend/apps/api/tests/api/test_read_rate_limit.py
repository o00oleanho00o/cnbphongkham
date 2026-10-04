"""``FixedWindowLimiter`` (package ST-S): the per-user budget of the staff picker routes. No database."""

from __future__ import annotations

from pema.api.read_rate_limit import FixedWindowLimiter


def test_a_key_may_call_up_to_the_budget_then_is_refused_until_the_window_passes() -> None:
    """đủ hạn mức thì cho, quá thì từ chối, sang cửa sổ mới thì cho lại"""
    limiter = FixedWindowLimiter(max_hits=3, window_ms=1000)
    assert [limiter.allow("u1", now_ms=0) for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("u1", now_ms=999) is False
    assert limiter.allow("u1", now_ms=1000) is True


def test_keys_do_not_share_a_budget() -> None:
    """mỗi người dùng một hạn mức riêng"""
    limiter = FixedWindowLimiter(max_hits=1, window_ms=1000)
    assert limiter.allow("u1", now_ms=0) is True
    assert limiter.allow("u1", now_ms=1) is False
    assert limiter.allow("u2", now_ms=1) is True


def test_expired_buckets_are_pruned_so_the_map_cannot_grow_for_ever() -> None:
    """không rò bộ nhớ: bucket hết hạn bị dọn khi map đủ lớn"""
    limiter = FixedWindowLimiter(max_hits=1, window_ms=1000, prune_threshold=5)
    for index in range(10):
        limiter.allow(f"u{index}", now_ms=0)
    assert limiter.bucket_count() == 10
    limiter.allow("late", now_ms=5000)
    assert limiter.bucket_count() == 1
    limiter.reset()
    assert limiter.bucket_count() == 0
