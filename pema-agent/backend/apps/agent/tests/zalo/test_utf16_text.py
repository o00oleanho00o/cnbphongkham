"""Tests of ``plugins.zalo.format.utf16_text`` (an addition of the port, no TS original)."""

from __future__ import annotations

import re

from plugins.zalo.format.utf16_text import (
    JS_NOT_S,
    JS_S,
    from_units,
    index_to_utf16,
    js_trim,
    js_trim_end,
    js_trim_start,
    khong_cat_giua_cap_thay_the,
    to_units,
    utf16_len,
    utf16_slice,
    utf16_to_index,
)

EMOJI = "\U0001f600"


def test_utf16_len_counts_astral_characters_as_two_units() -> None:
    """độ dài UTF-16: emoji ngoài BMP = 2 đơn vị, chữ có dấu = 1"""
    assert utf16_len("abc") == 3
    assert utf16_len("Đường") == 5
    assert utf16_len(f"a{EMOJI}b") == 4
    assert utf16_len("") == 0


def test_to_units_and_from_units_round_trip() -> None:
    """chuyển qua lại chuỗi đơn vị UTF-16 không mất gì"""
    for text in ["", "abc", "Đường Nguyễn", f"a{EMOJI}b{EMOJI}{EMOJI}", "\U0010ffff"]:
        units = to_units(text)
        assert len(units) == utf16_len(text)
        assert from_units(units) == text


def test_to_units_splits_a_pair_into_two_surrogate_units() -> None:
    """một emoji thành hai nửa surrogate"""
    units = to_units(EMOJI)
    assert [hex(ord(c)) for c in units] == ["0xd83d", "0xde00"]


def test_utf16_slice_and_offset_conversions_use_utf16_units() -> None:
    """lát cắt và đổi offset theo đơn vị UTF-16"""
    text = f"a{EMOJI}bc"
    assert utf16_slice(text, 1, 2) == EMOJI
    assert utf16_slice(text, 3, 2) == "bc"
    assert utf16_to_index(text, 3) == 2
    assert index_to_utf16(text, 2) == 3


def test_khong_cat_giua_cap_thay_the_moves_a_cut_off_the_middle_of_a_pair() -> None:
    """điểm cắt rơi giữa cặp thay thế thì lùi một đơn vị (hoặc tiến nếu đầu rỗng)"""
    units = to_units(f"ab{EMOJI}")
    assert khong_cat_giua_cap_thay_the(units, 3) == 2
    assert khong_cat_giua_cap_thay_the(units, 2) == 2
    assert khong_cat_giua_cap_thay_the(units, 4) == 4
    assert khong_cat_giua_cap_thay_the(to_units(EMOJI), 1) == 2


def test_js_whitespace_is_not_the_python_whitespace() -> None:
    """khoảng trắng JS: U+FEFF và U+00A0 có, U+0085 và U+001C không"""
    assert js_trim("﻿  x  　") == "x"
    assert js_trim("\u0085x\x1c") == "\u0085x\x1c"
    assert js_trim_start("\n\tx ") == "x "
    assert js_trim_end(" x\r\n﻿") == " x"
    assert re.fullmatch(f"{JS_S}+", "﻿  ") is not None
    assert re.fullmatch(f"{JS_S}+", "\u0085") is None
    assert re.fullmatch(JS_NOT_S, "\u0085") is not None
