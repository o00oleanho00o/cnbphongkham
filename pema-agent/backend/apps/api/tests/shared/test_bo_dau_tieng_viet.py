# ported from: src/shared/bo-dau-tieng-viet.test.ts
from __future__ import annotations

from pema.shared.bo_dau_tieng_viet import bo_dau_tieng_viet


def test_bo_dau_tieng_viet_strips_tone_marks_hats_and_the_letter_d_with_stroke() -> None:
    """bỏ dấu thanh, dấu mũ và chữ đ"""
    assert bo_dau_tieng_viet("Chính sách đổi trả") == "Chinh sach doi tra"
    assert bo_dau_tieng_viet("ĐƯỢC") == "DUOC"


def test_bo_dau_tieng_viet_keeps_unaccented_letters_and_digits() -> None:
    """giữ nguyên chữ và số không dấu"""
    assert bo_dau_tieng_viet("Bao hanh 12 thang") == "Bao hanh 12 thang"
