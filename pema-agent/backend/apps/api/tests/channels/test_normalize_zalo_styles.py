# ported from: src/zalo/normalize-zalo-styles.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Module thuần. Bất biến gốc: KHÔNG span nào chồng span CÙNG KIỂU. Zalo trả mã 112 và bỏ cả tin khi gặp - đã
mất một câu trả lời thật vì chuyện này.
"""

from __future__ import annotations

import json

from pema.channels.markdown_to_zalo_styles import markdown_sang_style_zalo
from pema.channels.normalize_zalo_styles import (
    ZaloStyle,
    ZaloTextStyle,
    chuan_hoa_styles,
    make_style,
    style_to_wire,
)
from pema_contracts.channel import TextStyle


def dem_cap_chong(styles: list[TextStyle]) -> int:
    """Đếm số cặp span cùng kiểu mà giao nhau - phải luôn bằng 0 sau chuẩn hóa."""
    n = 0
    for i, a in enumerate(styles):
        for b in styles[i + 1 :]:
            if a.style != b.style:
                continue
            if min(a.start + a.length, b.start + b.length) > max(a.start, b.start):
                n += 1
    return n


def dam(start: int, length: int) -> TextStyle:
    return make_style(start, length, ZaloTextStyle.BOLD)


def test_chuan_hoa_styles_bold_child_inside_bold_parent_is_merged_into_one() -> None:
    """span đậm con NẰM TRONG span đậm cha bị gộp làm một"""
    # Đúng hình dạng đã làm hỏng lượt 116: tiêu đề đậm cả dòng, bên trong còn một đoạn **đậm** nữa.
    ra = chuan_hoa_styles([dam(72, 28), dam(94, 6)])
    assert ra == [dam(72, 28)], "span con thừa, phải biến mất"


def test_chuan_hoa_styles_two_partially_overlapping_bold_spans_merge_into_one_covering_both() -> None:
    """hai span đậm chồng MỘT PHẦN gộp thành span phủ cả hai"""
    assert chuan_hoa_styles([dam(0, 10), dam(5, 10)]) == [dam(0, 15)]


def test_chuan_hoa_styles_two_touching_bold_spans_also_merge() -> None:
    """hai span đậm CHẠM NHAU cũng gộp - nhìn ra kết quả y hệt"""
    assert chuan_hoa_styles([dam(0, 5), dam(5, 5)]) == [dam(0, 10)]


def test_chuan_hoa_styles_two_disjoint_bold_spans_are_kept() -> None:
    """hai span đậm RỜI NHAU giữ nguyên - không được nối bừa qua chữ ở giữa"""
    ra = chuan_hoa_styles([dam(0, 5), dam(8, 5)])
    assert len(ra) == 2, "nối lại là tô đậm luôn chữ không được đánh dấu"


def test_chuan_hoa_styles_different_styles_are_not_merged_even_when_identical_in_position() -> None:
    """KHÁC kiểu tô thì KHÔNG gộp, dù trùng khít vị trí"""
    # Tiêu đề = Big + Bold cùng phạm vi. Đây là cặp bản tham chiếu dùng thật, gộp nhầm là mất một trong hai.
    ra = chuan_hoa_styles(
        [
            make_style(0, 10, ZaloTextStyle.BIG),
            make_style(0, 10, ZaloTextStyle.BOLD),
        ]
    )
    assert len(ra) == 2
    assert {s.style for s in ra} == {ZaloTextStyle.BIG, ZaloTextStyle.BOLD}


def test_chuan_hoa_styles_indent_of_different_levels_is_not_merged() -> None:
    """Indent KHÁC CẤP thì không gộp - gộp là làm phẳng danh sách lồng"""
    ra = chuan_hoa_styles(
        [
            make_style(0, 10, ZaloTextStyle.INDENT, indent_size=1),
            make_style(0, 10, ZaloTextStyle.INDENT, indent_size=2),
        ]
    )
    assert len(ra) == 2, "cấp 1 và cấp 2 là hai định dạng khác nhau"


def test_chuan_hoa_styles_result_is_sorted_by_start_longer_span_first_on_equal_start() -> None:
    """kết quả LUÔN sắp theo start, span dài đứng trước khi cùng start"""
    ra = chuan_hoa_styles(
        [
            dam(25, 3),
            make_style(13, 10, ZaloTextStyle.INDENT, indent_size=1),
            make_style(13, 20, ZaloTextStyle.UNORDERED_LIST),
            dam(0, 2),
        ]
    )
    assert [s.start for s in ra] == [0, 13, 13, 25]
    assert ra[1].length == 20, "cùng start thì span dài đứng trước"


def test_chuan_hoa_styles_empty_and_single_element_pass_through_unchanged() -> None:
    """mảng rỗng và một phần tử đi qua không đổi"""
    assert chuan_hoa_styles([]) == []
    assert chuan_hoa_styles([dam(3, 4)]) == [dam(3, 4)]


def test_markdown_sang_style_zalo_heading_with_bold_inside_the_case_that_made_zalo_return_112() -> None:
    """TIÊU ĐỀ CÓ IN ĐẬM BÊN TRONG - đúng ca đã làm Zalo trả mã 112"""
    ket = markdown_sang_style_zalo("## 1. Vé Tiền Giang - số **418512**")
    assert dem_cap_chong(ket.styles) == 0, "còn span chồng là Zalo còn bỏ cả tin"

    # Vẫn phải CÒN định dạng, không phải chữa bằng cách vứt hết đi
    kieu = {s.style for s in ket.styles}
    assert ZaloTextStyle.BIG in kieu, "tiêu đề phải còn to"
    assert ZaloTextStyle.BOLD in kieu, "tiêu đề phải còn đậm"


def test_markdown_sang_style_zalo_mixed_text_zero_overlapping_pairs_and_spans_sorted_by_position() -> None:
    """văn bản trộn đủ thứ: 0 cặp chồng, và span sắp theo vị trí"""
    doc = "\n".join(
        [
            "## Kết quả **hôm nay**",
            "- mục **một** và *nghiêng*",
            "  - lồng **hai** với `code`",
            "### Chốt lại: **xong**",
        ]
    )
    ket = markdown_sang_style_zalo(doc)

    assert dem_cap_chong(ket.styles) == 0
    sap_xep = all(i == 0 or ket.styles[i - 1].start <= s.start for i, s in enumerate(ket.styles))
    assert sap_xep, f"span không theo thứ tự: {[s.start for s in ket.styles]}"


# ------------------------------------------------------------------ additions of the port


def test_zalo_text_style_codes_are_the_zca_js_wire_strings() -> None:
    """(port) mã style khớp chuỗi zca-js 2.1.2 gửi lên đường dây"""
    assert {m.name: m.value for m in ZaloTextStyle} == {
        "BOLD": "b",
        "ITALIC": "i",
        "UNDERLINE": "u",
        "STRIKE_THROUGH": "s",
        "RED": "c_db342e",
        "ORANGE": "c_f27806",
        "YELLOW": "c_f7b503",
        "GREEN": "c_15a85f",
        "SMALL": "f_13",
        "BIG": "f_18",
        "UNORDERED_LIST": "lst_1",
        "ORDERED_LIST": "lst_2",
        "INDENT": "ind_$",
    }


def test_style_to_wire_is_the_zca_js_shape_with_keys_in_order() -> None:
    """(port) dạng dây: start, len, st (rồi indentSize) đúng thứ tự khóa, JSON gọn khớp JSON.stringify"""
    assert list(style_to_wire(dam(3, 4))) == ["start", "len", "st"]
    wire = style_to_wire(make_style(0, 9, ZaloTextStyle.INDENT, indent_size=2))
    assert list(wire) == ["start", "len", "st", "indentSize"]
    assert json.dumps({"styles": [wire]}, separators=(",", ":"), ensure_ascii=False) == (
        '{"styles":[{"start":0,"len":9,"st":"ind_$","indentSize":2}]}'
    )


def test_chuan_hoa_styles_keeps_the_indent_size_of_the_surviving_span() -> None:
    """(port) gộp hai span Indent cùng cấp vẫn giữ indent_size"""
    ra = chuan_hoa_styles(
        [
            make_style(0, 5, ZaloTextStyle.INDENT, indent_size=2),
            make_style(3, 5, ZaloTextStyle.INDENT, indent_size=2),
        ]
    )
    assert len(ra) == 1
    assert isinstance(ra[0], ZaloStyle)
    assert (ra[0].start, ra[0].length, ra[0].indent_size) == (0, 8, 2)
