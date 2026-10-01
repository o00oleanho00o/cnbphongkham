# ported from: src/images/image-rate-limit.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.images.image_rate_limit import check_image_rate_limit, reset_image_rate_limit


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    # Hai trần đặt LỆCH nhau: cắm nhầm biến env là test đổ ngay
    install_tuning_provider(StaticTuningProvider({"IMAGE_GEN_MAX_PER_HOUR": 2, "DOCUMENT_MAX_PER_HOUR": 9}))
    reset_image_rate_limit()
    yield
    reset_image_rate_limit()
    reset_tuning_provider()


def test_check_image_rate_limit_reads_the_ceiling_from_image_gen_max_per_hour() -> None:
    """đọc trần từ IMAGE_GEN_MAX_PER_HOUR chứ không phải trần của tool tạo file"""
    assert check_image_rate_limit("acc:t1").ok is True
    assert check_image_rate_limit("acc:t1").ok is True
    blocked = check_image_rate_limit("acc:t1")
    assert blocked.ok is False, "trần là 2 (IMAGE_GEN), không phải 9 (DOCUMENT)"
    assert "trần 2" in blocked.reason


def test_check_image_rate_limit_message_says_how_long_to_wait_and_suggests_describing() -> None:
    """câu báo nói rõ phải chờ bao lâu và gợi ý mô tả bằng lời"""
    t0 = time.time() * 1000
    check_image_rate_limit("acc:t1", t0)
    check_image_rate_limit("acc:t1", t0 + 60_000)
    blocked = check_image_rate_limit("acc:t1", t0 + 20 * 60_000)
    assert "khoảng 40 phút" in blocked.reason
    assert "mô tả" in blocked.reason.lower(), "chạm trần thì bot vẫn giúp được bằng lời"


def test_check_image_rate_limit_counts_each_thread_separately() -> None:
    """đếm riêng từng thread"""
    check_image_rate_limit("acc:t1")
    check_image_rate_limit("acc:t1")
    assert check_image_rate_limit("acc:t1").ok is False
    assert check_image_rate_limit("acc:t2").ok is True
