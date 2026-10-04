# ported from: src/zalo/split-long-message.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The last tests are additions of the port: they pin the UTF-16 behaviour (offsets and lengths in UTF-16 units,
never a cut through a surrogate pair), which the JS original gets from ``String`` for free.
"""

from __future__ import annotations

import re

from pema.channels.split_long_message import (
    OVERFLOW_NOTE,
    SplitOptions,
    split_long_message,
    split_long_message_with_offsets,
)
from pema.channels.utf16_text import to_units, utf16_len, utf16_slice

OPTS = SplitOptions(max_chars=100, max_parts=5)


def test_split_long_message_short_text_stays_one_message() -> None:
    """text ngắn giữ nguyên 1 tin"""
    assert split_long_message("Chào anh Hải", OPTS) == ["Chào anh Hải"]


def test_split_long_message_empty_text_returns_empty_list() -> None:
    """text rỗng trả mảng rỗng"""
    assert split_long_message("   \n  ", OPTS) == []


def test_split_long_message_every_part_is_within_the_limit() -> None:
    """mọi đoạn đều nằm trong giới hạn"""
    text = "\n".join(f"Dòng số {i} nội dung vừa phải." for i in range(40))
    parts = split_long_message(text, OPTS)
    assert len(parts) > 1, "phải cắt ra nhiều đoạn"
    for part in parts:
        assert utf16_len(part) <= OPTS.max_chars, f"đoạn dài {utf16_len(part)} vượt {OPTS.max_chars}"


def test_split_long_message_never_cuts_mid_word() -> None:
    """không cắt giữa từ"""
    text = "khoancatgiuatu " * 30
    for part in split_long_message(text, OPTS):
        # Cắt giữa từ sẽ để lại mảnh vụn khác với từ gốc
        for word in part.split():
            assert word == "khoancatgiuatu", f'mảnh vụn "{word}" - đã cắt giữa từ'


def test_split_long_message_prefers_cutting_at_blank_line() -> None:
    """ưu tiên cắt ở dòng trống (ranh giới đoạn văn)"""
    doan_a = "A" + "a" * 58
    doan_b = "B" + "b" * 58
    assert split_long_message(f"{doan_a}\n\n{doan_b}", OPTS) == [doan_a, doan_b]


def test_split_long_message_keeps_each_bullet_whole_when_list_has_no_blank_line() -> None:
    """giữ nguyên từng gạch đầu dòng khi danh sách không có dòng trống"""
    bullets = [f"- Mục thứ {i} của danh sách" for i in range(12)]
    for part in split_long_message("\n".join(bullets), OPTS):
        for line in part.split("\n"):
            assert re.fullmatch(r"- Mục thứ \d+ của danh sách", line), f'dòng bị cắt dở: "{line}"'


def test_split_long_message_rejoined_content_loses_no_text_below_the_part_cap() -> None:
    """ghép lại đủ nội dung, không mất chữ (khi chưa chạm trần số đoạn)"""
    text = " ".join(f"Câu số {i} nói một điều gì đó." for i in range(30))
    parts = split_long_message(text, SplitOptions(max_chars=100, max_parts=20))
    rebuilt = re.sub(r"\s+", " ", " ".join(parts))
    assert rebuilt == re.sub(r"\s+", " ", text)


def test_split_long_message_hard_cut_when_one_word_exceeds_the_window() -> None:
    """cắt cứng khi một từ dài hơn cả cửa sổ (URL khổng lồ)"""
    url = f"https://example.com/{'x' * 250}"
    parts = split_long_message(url, OPTS)
    assert len(parts) > 1
    assert "".join(parts) == url


def test_split_long_message_exceeding_the_part_cap_appends_overflow_note_to_the_last_part() -> None:
    """vượt trần số đoạn thì đoạn cuối kèm ghi chú còn nữa"""
    text = "Nội dung rất dài. " * 200
    parts = split_long_message(text, SplitOptions(max_chars=100, max_parts=3))
    assert len(parts) == 3
    assert parts[2].endswith(OVERFLOW_NOTE), "đoạn cuối phải có ghi chú"
    assert utf16_len(parts[2]) <= 100


def test_split_long_message_exactly_at_the_cap_has_no_note() -> None:
    """vừa đúng trần thì không kèm ghi chú"""
    text = f"{'a' * 90}\n\n{'b' * 90}"
    parts = split_long_message(text, SplitOptions(max_chars=100, max_parts=2))
    assert len(parts) == 2
    assert OVERFLOW_NOTE not in parts[1]


# ------------------------------------------------------------------ additions of the port (UTF-16)

EMOJI = "\U0001f600"  # one code point, two UTF-16 units


def test_split_long_message_with_offsets_reports_utf16_offsets_into_the_input() -> None:
    """(port) bat_dau / phu_goc là đơn vị UTF-16 trên chuỗi đưa vào, kể cả sau emoji và khoảng trắng đầu"""
    doan_a = f"  {EMOJI}{EMOJI} " + "a" * 50
    doan_b = "B" * 59
    text = f"{doan_a}\n\n{doan_b}"
    doans = split_long_message_with_offsets(text, SplitOptions(max_chars=100, max_parts=5))
    assert len(doans) == 2
    assert doans[0].bat_dau == 2  # two leading spaces
    assert doans[0].text == f"{EMOJI}{EMOJI} " + "a" * 50
    assert doans[0].phu_goc == utf16_len(doans[0].text) == 55  # 2 emoji = 4 units, space, 50 letters
    # the second part starts after "\n\n": offsets are measured in UTF-16 units of the input
    assert utf16_slice(text, doans[1].bat_dau, doans[1].phu_goc) == doans[1].text == doan_b


def test_split_long_message_limit_counts_utf16_units_not_code_points() -> None:
    """(port) trần ký tự tính theo UTF-16: 60 emoji = 120 đơn vị > 100 nên phải cắt, dù chỉ có 60 code point"""
    text = (EMOJI + " ") * 40  # 40 * 3 units = 120 units, 80 code points
    parts = split_long_message(text, SplitOptions(max_chars=100, max_parts=5))
    assert len(parts) == 2
    for part in parts:
        assert utf16_len(part) <= 100


def test_split_long_message_hard_cut_never_splits_a_surrogate_pair() -> None:
    """(port) cắt cứng không bao giờ chẻ đôi một emoji (bản JS gốc có thể)"""
    text = EMOJI * 120  # no space anywhere: forces the hard cut; 240 units
    for max_chars in (99, 100, 101):  # odd and even limits: the cut lands inside a pair for one of them
        parts = split_long_message(text, SplitOptions(max_chars=max_chars, max_parts=10))
        assert "".join(parts) == text
        for part in parts:
            assert utf16_len(part) <= max_chars
            assert re.fullmatch(f"(?:{EMOJI})+", part), "mảnh vỡ của cặp thay thế"
            # a lone surrogate would not survive the round trip through UTF-8
            part.encode("utf-8")


def test_split_long_message_unit_string_of_the_parts_is_a_slice_of_the_input() -> None:
    """(port) mỗi đoạn (trước khi dán ghi chú) chính là lát cắt [bat_dau, bat_dau + phu_goc) của đầu vào"""
    text = "\n".join(f"Dòng {i} {EMOJI} có chữ" for i in range(30))
    units = to_units(text)
    for doan in split_long_message_with_offsets(text, SplitOptions(max_chars=100, max_parts=20)):
        assert utf16_slice(text, doan.bat_dau, doan.phu_goc) == doan.text
        assert units[doan.bat_dau : doan.bat_dau + doan.phu_goc] == to_units(doan.text)
