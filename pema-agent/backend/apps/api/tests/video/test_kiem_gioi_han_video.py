# ported from: src/video/kiem-gioi-han-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import dataclasses
from typing import Any

from pema.video.kiem_gioi_han_video import GioiHanVideo, KetQuaKiemLoi, kiem_gioi_han_video
from pema.video.thong_tin_video import ThongTinVideo

GH = GioiHanVideo(thoi_luong_toi_da=30, dung_luong_toi_da=100)


def _video(**sua: Any) -> ThongTinVideo:
    base = ThongTinVideo(
        video_url="https://cdn/x.mp4",
        thumbnail_url="https://cdn/x.jpg",
        duration_ms=24_000,
        width=576,
        height=1024,
        file_size=3_000_000,
        tac_gia="ai_do",
        nguon="tikwm",
        nen_tang="tiktok",
    )
    return dataclasses.replace(base, **sua)


# ------------------------------------------------------------------ trần thời lượng


def test_tran_thoi_luong_video_ngan_thi_qua() -> None:
    """video ngắn thì qua"""
    assert kiem_gioi_han_video(_video(duration_ms=24_000), GH).ok is True


def test_tran_thoi_luong_dung_bang_tran_thi_qua() -> None:
    """đúng bằng trần thì QUA - trần là 'tối đa', không phải 'nhỏ hơn'"""
    assert kiem_gioi_han_video(_video(duration_ms=30 * 60_000), GH).ok is True


def test_tran_thoi_luong_vuot_tran_du_chi_1ms_thi_chan() -> None:
    """vượt trần dù chỉ 1ms thì chặn"""
    assert kiem_gioi_han_video(_video(duration_ms=30 * 60_000 + 1), GH).ok is False


def test_tran_thoi_luong_cau_tu_choi_co_du_so_de_nguoi_dung_hieu_vi_sao() -> None:
    """câu từ chối có ĐỦ SỐ để người dùng hiểu vì sao"""
    k = kiem_gioi_han_video(_video(duration_ms=45 * 60_000), GH)
    assert isinstance(k, KetQuaKiemLoi)
    assert "45 phút" in k.loi, "phải nói video dài bao nhiêu"
    assert "30 phút" in k.loi, "phải nói mức cho phép là bao nhiêu"
    assert "Cấu hình" in k.loi, "phải chỉ được chỗ chỉnh mức đó"


def test_tran_thoi_luong_duoi_1_phut_thi_noi_bang_giay() -> None:
    """dưới 1 phút thì nói bằng GIÂY - '0,3 phút' đọc không ra"""
    k = kiem_gioi_han_video(_video(duration_ms=20_000), GioiHanVideo(0.2, GH.dung_luong_toi_da))
    assert isinstance(k, KetQuaKiemLoi)
    assert "20 giây" in k.loi


def test_tran_thoi_luong_nguon_khong_noi_thoi_luong_0_thi_cho_qua() -> None:
    """nguồn KHÔNG nói thời lượng (0) thì CHO QUA, không chặn oan"""
    # ``duration_ms = 0`` means missing data, not a 0-second video. Refusing a valid video because the
    # source lacks a field is the worse outcome.
    assert kiem_gioi_han_video(_video(duration_ms=0), GH).ok is True


# ------------------------------------------------------------------ trần dung lượng


def test_tran_dung_luong_nhe_thi_qua() -> None:
    """nhẹ thì qua"""
    assert kiem_gioi_han_video(_video(file_size=3_000_000), GH).ok is True


def test_tran_dung_luong_vuot_tran_thi_chan_va_noi_ro_nang_bao_nhieu() -> None:
    """vượt trần thì chặn, và nói rõ nặng bao nhiêu"""
    k = kiem_gioi_han_video(_video(file_size=150 * 1024 * 1024), GH)
    assert isinstance(k, KetQuaKiemLoi)
    assert "150.0 MB" in k.loi or "150 MB" in k.loi
    assert "100 MB" in k.loi


def test_tran_dung_luong_nguon_khong_noi_dung_luong_null_thi_cho_qua() -> None:
    """nguồn không nói dung lượng (null) thì CHO QUA"""
    # Facebook MEASURED does NOT return ``filesize``. Blocking here blocks every Facebook video: the
    # duration ceiling is still the safety net.
    assert kiem_gioi_han_video(_video(file_size=None), GH).ok is True


def test_tran_dung_luong_dung_luong_0_cung_coi_la_khong_biet() -> None:
    """dung lượng 0 cũng coi là không biết"""
    assert kiem_gioi_han_video(_video(file_size=0), GH).ok is True


# ------------------------------------------------------------------ hai trần cùng lúc


def test_hai_tran_cung_luc_thoi_luong_chan_truoc_dung_luong() -> None:
    """thời lượng chặn TRƯỚC dung lượng - báo đúng lý do đầu tiên gặp"""
    # A video both long and heavy: either reason is true, but it must be CONSISTENT, or the user adjusts the
    # wrong setting.
    k = kiem_gioi_han_video(_video(duration_ms=60 * 60_000, file_size=500 * 1024 * 1024), GH)
    assert isinstance(k, KetQuaKiemLoi)
    assert "dài" in k.loi


def test_hai_tran_cung_luc_thieu_ca_hai_truong_thi_van_cho_qua() -> None:
    """thiếu CẢ HAI trường thì vẫn cho qua"""
    assert kiem_gioi_han_video(_video(duration_ms=0, file_size=None), GH).ok is True
