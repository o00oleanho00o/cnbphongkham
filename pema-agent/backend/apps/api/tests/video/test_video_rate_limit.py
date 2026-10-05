# ported from: src/video/video-rate-limit.ts
"""The original has no test file for this module; this small one (added) checks the wiring that nothing else
watches: the ceiling is read from the ``VIDEO_MAX_PER_HOUR`` tuning parameter WHEN CALLED, and a refund gives
the slot back."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.video.video_rate_limit import check_video_rate_limit, hoan_suat_video, reset_video_rate_limit


@pytest.fixture(autouse=True)
def tuning() -> Iterator[StaticTuningProvider]:
    provider = StaticTuningProvider({"VIDEO_MAX_PER_HOUR": 2})
    install_tuning_provider(provider)
    reset_video_rate_limit()
    yield provider
    reset_video_rate_limit()
    reset_tuning_provider()


def test_video_rate_limit_chan_khi_het_tran_va_noi_so_da_tai_va_so_phut_cho() -> None:
    """đọc trần từ VIDEO_MAX_PER_HOUR, hết trần thì chặn kèm số đã tải và số phút chờ"""
    assert check_video_rate_limit("acc:t1").ok is True
    assert check_video_rate_limit("acc:t1").ok is True
    r = check_video_rate_limit("acc:t1")
    assert r.ok is False
    assert "Đã tải 2 video" in r.reason
    assert "trần 2" in r.reason


def test_video_rate_limit_tran_doi_tren_cau_hinh_an_ngay(tuning: StaticTuningProvider) -> None:
    """trần được đọc LÚC GỌI nên đổi cấu hình là ăn ngay"""
    check_video_rate_limit("acc:t1")
    check_video_rate_limit("acc:t1")
    assert check_video_rate_limit("acc:t1").ok is False
    tuning.replace({"VIDEO_MAX_PER_HOUR": 3})
    assert check_video_rate_limit("acc:t1").ok is True


def test_video_rate_limit_hoan_suat_tra_lai_mot_suat_khi_khong_gui_duoc() -> None:
    """hoàn suất khi video KHÔNG gửi được thì không bị khóa oan"""
    check_video_rate_limit("acc:t1")
    check_video_rate_limit("acc:t1")
    hoan_suat_video("acc:t1")
    assert check_video_rate_limit("acc:t1").ok is True


def test_video_rate_limit_dem_rieng_tung_thread() -> None:
    """đếm theo thread: một người spam không chặn người khác"""
    check_video_rate_limit("acc:t1")
    check_video_rate_limit("acc:t1")
    assert check_video_rate_limit("acc:t1").ok is False
    assert check_video_rate_limit("acc:t2").ok is True
