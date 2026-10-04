# ported from: src/zalo/prepare-outgoing-text.ts
"""The original has no test file; these tests cover its two functions (names: ``describe_it`` in English).

``ZALO_RICH_TEXT_ENABLED`` is switched through the tuning provider and reset after every test.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.channels.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)


@pytest.fixture(autouse=True)
def _reset_tuning() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


def _rich(enabled: bool) -> None:
    install_tuning_provider(StaticTuningProvider({"ZALO_RICH_TEXT_ENABLED": enabled}))


def test_lam_sach_theo_cau_hinh_rich_text_on_keeps_markdown_for_the_translator() -> None:
    """bật định dạng: giữ dấu markdown (bộ dịch sẽ biến thành style), chỉ chạy hai lá chắn"""
    _rich(True)
    kq = lam_sach_theo_cau_hinh("**đậm** `code`\n[SILENT]")
    assert kq.text == "**đậm** `code`"
    assert kq.da_sua == ["nhãn [SILENT]"]


def test_lam_sach_theo_cau_hinh_rich_text_off_strips_markdown_the_old_path() -> None:
    """tắt định dạng: đường cũ, xóa markdown"""
    _rich(False)
    kq = lam_sach_theo_cau_hinh("**đậm** `code`\n[SILENT]")
    assert kq.text == "đậm code"
    assert kq.da_sua == ["inline code", "in đậm", "nhãn [SILENT]"]


def test_lam_sach_theo_cau_hinh_prompt_leak_is_blocked_on_both_paths() -> None:
    """chặn rò prompt ở cả hai đường"""
    for enabled in (True, False):
        _rich(enabled)
        assert lam_sach_theo_cau_hinh("Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ...").chan is True


def test_lam_sach_theo_cau_hinh_default_is_rich_text_on() -> None:
    """mặc định ZALO_RICH_TEXT_ENABLED = true"""
    assert lam_sach_theo_cau_hinh("**đậm**").text == "**đậm**"


def test_dinh_dang_neu_bat_rich_text_on_translates_markdown_into_text_plus_styles() -> None:
    """bật định dạng: dịch markdown thành chữ trần + style"""
    _rich(True)
    ket = dinh_dang_neu_bat("Giá **45k**")
    assert ket.text == "Giá 45k"
    assert [(s.start, s.length, s.style) for s in ket.styles] == [(4, 3, "b")]


def test_dinh_dang_neu_bat_rich_text_off_returns_the_text_unchanged_with_no_styles() -> None:
    """tắt định dạng: trả chữ y nguyên, không style"""
    _rich(False)
    ket = dinh_dang_neu_bat("Giá **45k**")
    assert ket.text == "Giá **45k**"
    assert ket.styles == []
