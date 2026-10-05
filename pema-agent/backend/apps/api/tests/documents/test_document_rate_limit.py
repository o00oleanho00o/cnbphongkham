# ported from: src/documents/document-rate-limit.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``DOCUMENT_MAX_PER_HOUR=3`` comes from a static tuning provider; the counting state is module-level, so it is
reset before every test (``beforeEach`` of the original).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.documents.document_rate_limit import RateCheck, check_document_rate_limit, reset_document_rate_limit

HOUR = 60 * 60 * 1000


@pytest.fixture(autouse=True)
def _limit() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({"DOCUMENT_MAX_PER_HOUR": 3}))
    reset_document_rate_limit()
    yield
    reset_document_rate_limit()
    reset_tuning_provider()


def _now() -> float:
    return time.time() * 1000


def test_check_document_rate_limit_allows_up_to_the_ceiling_then_blocks() -> None:
    """cho tạo tới đúng trần rồi mới chặn"""
    for i in range(1, 4):
        assert check_document_rate_limit("acc:t1") == RateCheck(ok=True), f"lần {i}"
    blocked = check_document_rate_limit("acc:t1")
    assert blocked.ok is False
    assert "trần 3" in blocked.reason


def test_check_document_rate_limit_counts_each_thread_separately() -> None:
    """đếm riêng từng thread - thread này đầy không ảnh hưởng thread khác"""
    for _ in range(3):
        check_document_rate_limit("acc:t1")
    assert check_document_rate_limit("acc:t1").ok is False
    assert check_document_rate_limit("acc:t2").ok is True, "thread khác vẫn tạo được"


def test_check_document_rate_limit_after_the_one_hour_window_creation_is_allowed_again() -> None:
    """qua cửa sổ 1 giờ thì được tạo tiếp"""
    start = _now()
    for _ in range(3):
        check_document_rate_limit("acc:t1", start)
    assert check_document_rate_limit("acc:t1", start).ok is False
    # Nudge past the 1 hour mark
    assert check_document_rate_limit("acc:t1", start + HOUR + 1).ok is True


def test_check_document_rate_limit_message_says_how_many_minutes_are_left() -> None:
    """thông báo nói rõ còn bao nhiêu phút nữa"""
    start = _now()
    for _ in range(3):
        check_document_rate_limit("acc:t1", start)
    # 20 minutes after the first -> ~40 left
    blocked = check_document_rate_limit("acc:t1", start + 20 * 60_000)
    assert blocked.ok is False
    assert "khoảng 40 phút" in blocked.reason


def test_check_document_rate_limit_sliding_window_old_use_frees_a_slot() -> None:
    """cửa sổ trượt: lần cũ hết hạn thì có thêm suất, không phải chờ hết cả giờ"""
    t0 = _now()
    check_document_rate_limit("acc:t1", t0)
    check_document_rate_limit("acc:t1", t0 + 30 * 60_000)
    check_document_rate_limit("acc:t1", t0 + 40 * 60_000)
    assert check_document_rate_limit("acc:t1", t0 + 50 * 60_000).ok is False
    # Once the first use (t0) leaves the window 2 remain -> 1 more slot
    assert check_document_rate_limit("acc:t1", t0 + HOUR + 1000).ok is True


def test_check_document_rate_limit_cold_threads_are_swept_from_memory() -> None:
    """thread nguội bị dọn khỏi bộ nhớ (hồi quy rò rỉ Map)"""
    t0 = _now()
    for i in range(500):
        check_document_rate_limit(f"acc:cu-{i}", t0)
    # One new thread after 1 hour: this check must sweep the 500 old threads clean
    check_document_rate_limit("acc:moi", t0 + HOUR + 1000)
    # The old threads now look as if they never made a file -> all 3 slots again
    for i in range(1, 4):
        assert check_document_rate_limit("acc:cu-0", t0 + HOUR + 2000).ok is True, f"suất {i} sau khi dọn"


def test_check_document_rate_limit_ceiling_is_read_at_call_time() -> None:
    """EXTRA: the ceiling comes from the tuning at CALL time, so a hot change applies at once"""
    assert check_document_rate_limit("acc:t1").ok is True
    install_tuning_provider(StaticTuningProvider({"DOCUMENT_MAX_PER_HOUR": 1}))
    assert check_document_rate_limit("acc:t1").ok is False
    install_tuning_provider(StaticTuningProvider({"DOCUMENT_MAX_PER_HOUR": 5}))
    assert check_document_rate_limit("acc:t1").ok is True
