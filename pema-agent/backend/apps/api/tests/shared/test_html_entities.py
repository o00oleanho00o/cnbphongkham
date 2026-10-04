# ported from: src/shared/html-entities.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.shared.html_entities import decode_html_entities


def test_decode_html_entities_lowercase_named_entities_minhngoc_style() -> None:
    """entity tên chữ thường - kiểu minhngoc.net.vn hay dùng"""
    assert decode_html_entities("Ng&agrave;y quay: th&aacute;ng 7") == "Ngày quay: tháng 7"


def test_decode_html_entities_uppercase_named_derived_from_lowercase_table() -> None:
    """entity tên viết hoa suy ra từ bảng chữ thường (CHUY&Ecirc;N -> CHUYÊN)"""
    assert decode_html_entities("CHUY&Ecirc;N TRANG") == "CHUYÊN TRANG"
    assert decode_html_entities("&Ocirc;ng &Agrave;") == "Ông À"


def test_decode_html_entities_decimal_and_hex_numeric_entities() -> None:
    """entity số thập phân và hex"""
    assert decode_html_entities("Gi&#225; v&#224;ng") == "Giá vàng"
    assert decode_html_entities("&#x1EA1;") == "ạ"


def test_decode_html_entities_symbols_nbsp_amp_trade_hellip() -> None:
    """ký hiệu: nbsp, amp, trade, hellip"""
    assert decode_html_entities("A&nbsp;&amp;&nbsp;B&hellip;") == "A & B..."
    assert decode_html_entities("Minh Ngọc&trade;") == "Minh Ngọc(TM)"


def test_decode_html_entities_unknown_entity_kept_as_is_without_throwing() -> None:
    """entity không biết giữ nguyên, không throw"""
    assert decode_html_entities("&khongbiet; &x;") == "&khongbiet; &x;"


# ---- added: guards that Python needs and JS did not (see the module docstring) ----


def test_decode_html_entities_out_of_range_code_point_is_kept_as_text() -> None:
    """code point ngoài khoảng hợp lệ (hoặc surrogate lẻ) giữ nguyên, không throw"""
    assert decode_html_entities("&#99999999999;") == "&#99999999999;"
    assert decode_html_entities("&#xD800;") == "&#xD800;"
