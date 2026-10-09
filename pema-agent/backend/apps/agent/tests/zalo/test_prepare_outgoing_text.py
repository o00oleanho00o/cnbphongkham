# ported from: src/zalo/prepare-outgoing-text.ts
"""The original has no test file; these tests cover its two functions (names: ``describe_it`` in English).

``rich_text`` is the plugin's setting of the same name (``ZALO_RICH_TEXT_ENABLED`` in the original).
"""

from __future__ import annotations

from plugins.zalo.format.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh


def test_lam_sach_theo_cau_hinh_rich_text_on_keeps_markdown_for_the_translator() -> None:
    """bật định dạng: giữ dấu markdown (bộ dịch sẽ biến thành style), chỉ chạy hai lá chắn"""
    kq = lam_sach_theo_cau_hinh("**đậm** `code`\n[SILENT]", rich_text=True)
    assert kq.text == "**đậm** `code`"
    assert kq.da_sua == ["nhãn [SILENT]"]


def test_lam_sach_theo_cau_hinh_rich_text_off_strips_markdown_the_old_path() -> None:
    """tắt định dạng: đường cũ, xóa markdown"""
    kq = lam_sach_theo_cau_hinh("**đậm** `code`\n[SILENT]", rich_text=False)
    assert kq.text == "đậm code"
    assert kq.da_sua == ["inline code", "in đậm", "nhãn [SILENT]"]


def test_lam_sach_theo_cau_hinh_prompt_leak_is_blocked_on_both_paths() -> None:
    """chặn rò prompt ở cả hai đường"""
    for enabled in (True, False):
        text = "Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ..."
        assert lam_sach_theo_cau_hinh(text, rich_text=enabled).chan is True


def test_dinh_dang_neu_bat_rich_text_on_translates_markdown_into_text_plus_styles() -> None:
    """bật định dạng: dịch markdown thành chữ trần + style"""
    ket = dinh_dang_neu_bat("Giá **45k**", rich_text=True)
    assert ket.text == "Giá 45k"
    assert [(s.start, s.length, s.style) for s in ket.styles] == [(4, 3, "b")]


def test_dinh_dang_neu_bat_rich_text_off_returns_the_text_unchanged_with_no_styles() -> None:
    """tắt định dạng: trả chữ y nguyên, không style"""
    ket = dinh_dang_neu_bat("Giá **45k**", rich_text=False)
    assert ket.text == "Giá **45k**"
    assert ket.styles == []
