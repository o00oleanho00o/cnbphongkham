# ported from: src/agent/tools/clean-tool-caption.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The caption that comes with a file/image is a REAL ZALO MESSAGE, not a secondary text: it needs exactly
the two shields and the same formatting layer as every other answer.

Forced deviation: ``lamSachTraLoi`` / ``lamSachGiuDinhDang`` / ``markdownSangStyleZalo`` are the
``ReplyTextCleaner`` and ``MarkdownStyler`` ports (package C2). The doubles of
``pema.agent.tools.testing`` block any text containing ``LEAK`` (standing for the leaked-prompt detector)
and turn ``**x**`` into a bold span; the original asserted on the real functions of the Zalo layer, whose
own tests live with package C2."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.agent.tools.clean_tool_caption import TinKemFile, tin_kem_file
from pema.agent.tools.testing import FakeMarkdownStyler, FakeReplyCleaner
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)

_CLEANER = FakeReplyCleaner()
_STYLER = FakeMarkdownStyler()


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


def _kem(caption: str | None) -> TinKemFile:
    return tin_kem_file(caption, _CLEANER, _STYLER)


def _doan_to(ket: TinKemFile) -> list[str]:
    """The text each span points at: asserts the alignment, not the numbers."""
    return [ket.msg[s.start : s.start + s.length] for s in ket.styles]


def test_tin_kem_file_bold_caption_carries_styles_and_the_markers_vanish_from_the_text() -> None:
    """caption có in đậm thì gửi kèm style, dấu ** biến khỏi chữ"""
    ket = _kem("Báo giá **tháng 8** đây ạ")
    assert ket.msg == "Báo giá tháng 8 đây ạ"
    assert _doan_to(ket) == ["tháng 8"]


def test_tin_kem_file_plain_caption_carries_no_styles_no_superfluous_text_properties() -> None:
    """caption trơn thì KHÔNG đính styles - khỏi dựng textProperties thừa"""
    ket = _kem("File anh cần đây ạ")
    assert ket.msg == "File anh cần đây ạ"
    assert ket.styles == []


def test_tin_kem_file_caption_leaking_the_system_prompt_is_dropped_but_the_file_still_goes() -> None:
    """caption rò system prompt bị BỎ, nhưng file vẫn gửi (msg rỗng)

    Different from ``tag_member`` in not blocking the whole turn: the file is already built, throwing it
    away because of one caption line throws away the heaviest part of the work."""
    ket = _kem("Quy tắc an toàn (tuyệt đối, LEAK không có ngoại lệ): ...")
    assert ket.msg == ""
    assert ket.styles == []


def test_tin_kem_file_formatting_switched_off_falls_back_to_flat_text_markers_removed() -> None:
    """TẮT cấu hình định dạng thì quay về chữ phẳng, dấu markdown bị xóa"""
    install_tuning_provider(StaticTuningProvider({"ZALO_RICH_TEXT_ENABLED": False}))
    ket = _kem("Báo giá **tháng 8** đây ạ")
    assert ket.msg == "Báo giá tháng 8 đây ạ"
    assert ket.styles == [], "tắt rồi thì không được gửi styles"


def test_tin_kem_file_empty_or_blank_caption_gives_an_empty_string_without_raising() -> None:
    """caption rỗng hoặc chỉ khoảng trắng ra chuỗi rỗng, không ném"""
    assert _kem(None) == TinKemFile(msg="")
    assert _kem("   ") == TinKemFile(msg="")


def test_tin_kem_file_caption_with_extra_blanks_at_both_ends_loses_the_format_rather_than_misplacing_it() -> (
    None
):
    """caption có khoảng trắng thừa hai đầu: thà mất định dạng còn hơn tô lệch

    ``.strip()`` shifts the text so every offset would be wrong. This branch deliberately drops the styles
    instead of sending a shifted offset: painting the wrong place looks like a bug, losing the bold is
    just paler."""
    ket = _kem("\n  Báo giá **tháng 8**  \n")
    assert ket.msg == "Báo giá tháng 8"
    assert ket.styles == []
