# ported from: src/zalo/markdown-to-zalo-styles.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Module thuần, không chạm DB.

CÁCH KHẲNG ĐỊNH: hầu hết ca đều kiểm ``text[start : start + len]`` (UTF-16) ra ĐÚNG đoạn chữ mong muốn, thay
vì so ``start``/``length`` với số tự tính tay. Số tự tính tay thì lỗi số học của người viết test và lỗi của
code triệt tiêu nhau, còn lát cắt thì chứng minh thẳng "Zalo sẽ tô đúng chỗ này".
"""

from __future__ import annotations

import itertools
import re

from plugins.zalo.format.markdown_to_zalo_styles import KetQuaDinhDang, markdown_sang_style_zalo
from plugins.zalo.format.normalize_zalo_styles import ZaloTextStyle
from plugins.zalo.format.text_style import TextStyle
from plugins.zalo.format.utf16_text import JS_S, JS_WS_CHARS, utf16_len, utf16_slice

Z = ZaloTextStyle


def doan_cua(ket: KetQuaDinhDang, i: int) -> str:
    """Đoạn chữ mà một span trỏ tới - dùng để khẳng định căn lề (offsets are UTF-16 units)."""
    s = ket.styles[i]
    return utf16_slice(ket.text, s.start, s.length)


def doan_cua_style(ket: KetQuaDinhDang, s: TextStyle) -> str:
    return utf16_slice(ket.text, s.start, s.length)


# ----------------------------------------------------------------------------- inline


def test_markdown_sang_style_zalo_inline_plain_text_produces_no_style() -> None:
    """chữ thường không sinh style nào"""
    ket = markdown_sang_style_zalo("Chào anh Hải, hôm nay trời đẹp.")
    assert ket.text == "Chào anh Hải, hôm nay trời đẹp."
    assert ket.styles == []


def test_markdown_sang_style_zalo_inline_bold_strips_the_markers_and_styles_the_exact_text() -> None:
    """**đậm** bóc dấu và tô ĐÚNG đoạn chữ"""
    ket = markdown_sang_style_zalo("Giá là **45.000 đồng** nhé")
    assert ket.text == "Giá là 45.000 đồng nhé", "dấu ** phải biến mất khỏi chữ"
    assert len(ket.styles) == 1
    assert ket.styles[0].style == Z.BOLD
    assert doan_cua(ket, 0) == "45.000 đồng"


def test_markdown_sang_style_zalo_inline_vietnamese_diacritics_do_not_shift_offsets() -> None:
    """dấu tiếng Việt KHÔNG làm lệch offset"""
    # Mọi ký tự có dấu ở đây đều là một đơn vị UTF-16, nhưng ca này là lưới đỡ cho lần ai đó đổi cách đếm.
    ket = markdown_sang_style_zalo("Đường Nguyễn Huệ có **quán cà phê Đợi** rất đông")
    assert doan_cua(ket, 0) == "quán cà phê Đợi"


def test_markdown_sang_style_zalo_inline_emoji_before_bold_text_still_aligns_offsets_are_utf16_units() -> (
    None
):
    """EMOJI trước đoạn đậm vẫn căn đúng - offset là đơn vị UTF-16"""
    # Emoji là cặp surrogate = 2 đơn vị UTF-16. Đếm theo code point sẽ lệch toàn bộ phần sau emoji đầu tiên,
    # mà tin nhắn thật đầy emoji.
    ket = markdown_sang_style_zalo("🔥🎉 Khuyến mãi **giảm 50%** hôm nay")
    assert doan_cua(ket, 0) == "giảm 50%", "lệch ở đây nghĩa là Zalo tô đậm nhầm chỗ ngay khi tin có emoji"
    # the proof that the offset is in UTF-16 units: two emoji are 4 units, the text before the span is
    # "🔥🎉 Khuyến mãi " = 4 + 1 + 6 + 1 + 3 + 1 = 16 units but only 14 code points
    assert ket.styles[0].start == 16
    assert ket.text.index("giảm") == 14


def test_markdown_sang_style_zalo_inline_several_different_markers_on_one_line_later_spans_do_not_drift() -> (
    None
):
    """nhiều cặp dấu KHÁC NHAU trên cùng một dòng - span sau không bị trôi"""
    # Đây là cái bẫy bản tham chiếu đã dính thật: pass sau xóa ký tự nằm TRƯỚC span pass trước đã ghi, span cũ
    # trôi mà không ai chỉnh lại.
    ket = markdown_sang_style_zalo("**Đậm** rồi ~~gạch~~ rồi *nghiêng*")
    assert ket.text == "Đậm rồi gạch rồi nghiêng"
    theo_chu = {doan_cua(ket, i): s.style for i, s in enumerate(ket.styles)}
    assert theo_chu == {
        "Đậm": Z.BOLD,
        "gạch": Z.STRIKE_THROUGH,
        "nghiêng": Z.ITALIC,
    }


def test_markdown_sang_style_zalo_inline_underscores_are_left_alone_real_file_names_are_full_of_them() -> (
    None
):
    """gạch dưới KHÔNG bị đụng tới - tên file thật đầy dấu đó"""
    # Quyết định đã có từ `sanitize_reply_text`: bắt `__x__`/`_x_` là đổi hỏng dữ liệu thật như
    # `bao_gia_2026.pdf`.
    ket = markdown_sang_style_zalo("File bao_gia_2026.pdf và __ghi chú__ giữ nguyên")
    assert ket.text == "File bao_gia_2026.pdf và __ghi chú__ giữ nguyên"
    assert ket.styles == []


def test_markdown_sang_style_zalo_inline_code_becomes_bold_because_zalo_has_no_mono_font() -> None:
    """`code` thành đậm vì Zalo không có font mono"""
    ket = markdown_sang_style_zalo("Chạy lệnh `pnpm dev` nhé")
    assert ket.text == "Chạy lệnh pnpm dev nhé"
    assert ket.styles[0].style == Z.BOLD
    assert doan_cua(ket, 0) == "pnpm dev"


# ----------------------------------------------------------------------------- block


def test_markdown_sang_style_zalo_block_heading_becomes_big_plus_bold_and_the_hashes_disappear() -> None:
    """tiêu đề thành to + đậm, dấu # biến mất"""
    ket = markdown_sang_style_zalo("## Bảng giá hôm nay")
    assert ket.text == "Bảng giá hôm nay"
    assert sorted(s.style for s in ket.styles) == sorted([Z.BIG, Z.BOLD])
    assert doan_cua(ket, 0) == "Bảng giá hôm nay"


def test_markdown_sang_style_zalo_block_dash_bullets_keep_the_dash_char_and_emit_no_list_style() -> None:
    """gạch đầu dòng GIỮ NGUYÊN ký tự "- ", KHÔNG sinh style danh sách"""
    # Đã đo trên máy thật 2026-08-05: `lst_1` render KHÁC NHAU giữa hai client. Zalo Web vẽ một dấu cho mỗi
    # dòng, Zalo trên điện thoại chỉ vẽ MỘT dấu cho cả span rồi thụt các dòng sau vào - danh sách 9 mục thành
    # 1 mục. Chữ "- " thường thì hiện y hệt nhau ở mọi client và tốn 0 span.
    ket = markdown_sang_style_zalo("- cà phê đen\n- cà phê sữa")
    assert ket.text == "- cà phê đen\n- cà phê sữa", "ký tự gạch đầu dòng phải còn nguyên"
    assert ket.styles == [], "không được phát style danh sách nào"


def test_markdown_sang_style_zalo_block_numbered_list_also_keeps_the_1_dot_chars() -> None:
    """đánh số cũng giữ nguyên ký tự "1. " """
    ket = markdown_sang_style_zalo("1. một\n2. hai")
    assert ket.text == "1. một\n2. hai"
    assert ket.styles == []


def test_markdown_sang_style_zalo_block_nested_list_keeps_the_leading_indent_spaces() -> None:
    """danh sách lồng giữ khoảng trắng thụt đầu dòng"""
    # Không còn span `Indent` nào - cấp lồng nằm ở chính khoảng trắng của chữ.
    ket = markdown_sang_style_zalo("- cha\n  - con")
    assert ket.text == "- cha\n  - con"
    assert ket.styles == []


def test_markdown_sang_style_zalo_block_bold_inside_a_list_line_is_still_styled_in_the_right_place() -> None:
    """in đậm TRONG dòng danh sách vẫn tô đúng chỗ"""
    # Bỏ style danh sách không được kéo theo mất định dạng bên trong dòng.
    ket = markdown_sang_style_zalo("- Giải 8: **87**\n- Giải 7: **110**")
    assert ket.text == "- Giải 8: 87\n- Giải 7: 110"
    assert [doan_cua_style(ket, s) for s in ket.styles] == ["87", "110"]


def test_markdown_sang_style_zalo_block_mixed_block_and_inline_lines_every_span_points_at_the_right_place() -> (
    None
):
    """nhiều dòng trộn khối và inline - mọi span vẫn trỏ đúng chỗ"""
    ket = markdown_sang_style_zalo("# Tiêu đề\nMở đầu **quan trọng** ở đây\n- mục **một**")
    for i in range(len(ket.styles)):
        doan = doan_cua(ket, i)
        assert len(doan) > 0, f"span {i} trỏ vào chuỗi rỗng - dấu hiệu lệch offset"
        assert "*" not in doan, f"span {i} còn dính dấu markdown: {doan}"
        assert "#" not in doan, f"span {i} còn dính dấu markdown: {doan}"
    assert "quan trọng" in ket.text
    assert "**" not in ket.text, "không còn dấu ** trong chữ cuối"


def test_markdown_sang_style_zalo_block_keeps_the_blank_line_before_a_heading_drops_the_one_after_it() -> (
    None
):
    """GIỮ dòng trống TRƯỚC tiêu đề, BỎ dòng trống ngay sau nó"""
    # Trước tiêu đề là ranh giới hai mục - thiếu nó thì câu kết của mục trên dính luôn vào tiêu đề mục dưới.
    # Sau tiêu đề thì câu dẫn thuộc về nó.
    ket = markdown_sang_style_zalo("Kết luận: xong.\n\n## Mục sau\n\nCâu dẫn.")
    assert ket.text == "Kết luận: xong.\n\nMục sau\nCâu dẫn."


def test_markdown_sang_style_zalo_block_drops_the_blank_line_between_a_lead_in_sentence_and_its_list() -> (
    None
):
    """BỎ dòng trống giữa CÂU DẪN và danh sách ngay dưới nó"""
    # Danh sách là phần khai triển của chính câu đó ("Đối chiếu vé 645300:" rồi tới các mục) - tách ra là làm
    # rời hai thứ vốn đi liền nhau.
    ket = markdown_sang_style_zalo("Đối chiếu vé 645300:\n\n- Hai số cuối 00\n- Ba số cuối 300")
    assert ket.text == "Đối chiếu vé 645300:\n- Hai số cuối 00\n- Ba số cuối 300"


def test_markdown_sang_style_zalo_block_keeps_the_blank_line_before_a_list_item_when_the_text_above_does_not_lead_into_it() -> (
    None
):
    """GIỮ dòng trống trước mục danh sách khi đoạn trên KHÔNG dẫn vào nó"""
    # Đo trên bản tin công nghệ thật: mỗi tin là một mục đánh số, kết bằng dòng nguồn và URL. Bản đầu bỏ dòng
    # trống trước MỌI danh sách nên mục sau dính luôn vào URL của tin trước, trong khi các mục khác vẫn có
    # khoảng cách - nhìn ra là cách dòng lộn xộn.
    ket = markdown_sang_style_zalo(
        "1. **Tin một**\n\nNội dung.\n\nNguồn: CNBC\nhttps://a.test/x.html\n\n2. **Tin hai**\n\nNội dung hai."
    )
    assert "https://a.test/x.html\n\n2. Tin hai" in ket.text, f"mục 2 dính vào URL của tin trước:\n{ket.text}"


def test_markdown_sang_style_zalo_block_keeps_the_blank_line_after_a_list_block() -> None:
    """GIỮ dòng trống SAU khối danh sách - đó là ranh giới sang ý khác"""
    ket = markdown_sang_style_zalo("- một\n- hai\n\nKết luận: xong.")
    assert ket.text == "- một\n- hai\n\nKết luận: xong."


def test_markdown_sang_style_zalo_block_blank_line_between_two_plain_paragraphs_is_kept() -> None:
    """dòng trống giữa hai ĐOẠN VĂN thường vẫn giữ - Zalo không tự thêm gì ở đó"""
    # Chỗ này mà cũng bỏ thì hai đoạn dính liền, đọc còn tệ hơn khe hở đôi.
    ket = markdown_sang_style_zalo("Đoạn một.\n\nĐoạn hai.")
    assert ket.text == "Đoạn một.\n\nĐoạn hai."


def test_markdown_sang_style_zalo_block_dropping_blank_lines_does_not_shift_spans_of_later_lines() -> None:
    """bỏ dòng trống KHÔNG làm lệch span của những dòng phía sau"""
    # Bỏ dòng là dời mọi thứ phía sau sang trái. Quên trừ con trỏ thì toàn bộ span sau chỗ bỏ trôi đi - mà
    # đây là ca thường gặp nhất trong tin thật.
    ket = markdown_sang_style_zalo("Mở đầu:\n\n- mục **một**\n\n## Tiêu đề **đậm**\n\n- mục **hai**")
    for s in ket.styles:
        doan = doan_cua_style(ket, s)
        assert len(doan) > 0, "span trỏ vào chuỗi rỗng - lệch offset"
        assert "\n" not in doan, f"span trùm qua ký tự xuống dòng: {doan!r}"
    dam = [s for s in ket.styles if s.style == Z.BOLD]
    doan_dam = [doan_cua_style(ket, s) for s in dam]
    assert "một" in doan_dam, f'mất hoặc lệch "một": {doan_dam!r}'
    assert "hai" in doan_dam, f'mất hoặc lệch "hai": {doan_dam!r}'


def test_markdown_sang_style_zalo_block_table_separator_row_is_dropped_data_rows_are_kept() -> None:
    """dòng kẻ ngăn của bảng bị bỏ, dòng dữ liệu giữ nguyên"""
    ket = markdown_sang_style_zalo("| Loại | Giá |\n|---|---|\n| Đen | 20k |")
    assert "---" not in ket.text, "dòng kẻ ngăn phải biến mất"
    assert "| Đen | 20k |" in ket.text, "dòng dữ liệu phải còn nguyên"


def test_markdown_sang_style_zalo_block_code_block_content_is_kept_verbatim_never_read_as_markdown() -> None:
    """NỘI DUNG TRONG KHỐI CODE giữ nguyên xi, không bị hiểu là markdown"""
    # Đây đúng là lỗi mà `sanitize_code_block` được viết ra để chữa: gỡ rào sớm thì `# Tính tổng` bị coi là
    # tiêu đề và code trả về sai cú pháp.
    ket = markdown_sang_style_zalo("Đoạn Python:\n```python\n# Tính tổng\n- a = 1\n*x = 2\n```\nxong")
    assert "# Tính tổng" in ket.text, "dấu thăng của comment Python phải còn"
    assert "- a = 1" in ket.text, "dấu gạch trong code phải còn"
    assert "*x = 2" in ket.text, "dấu sao trong code phải còn"
    assert "```" not in ket.text, "hàng rào thì bỏ"
    assert ket.styles == [], "không span nào phát ra từ code"


def test_markdown_sang_style_zalo_block_same_line_code_fence_is_only_unfenced_no_text_swallowed() -> None:
    """rào code CÙNG DÒNG chỉ bị gỡ rào, không nuốt chữ"""
    ket = markdown_sang_style_zalo("Chạy ```pnpm dev``` là xong")
    assert ket.text == "Chạy pnpm dev là xong"


def test_markdown_sang_style_zalo_block_markdown_link_becomes_text_followed_by_url_so_the_link_stays_clickable() -> (
    None
):
    """[chữ](url) thành 'chữ (url)' để link vẫn bấm được"""
    ket = markdown_sang_style_zalo("Xem [bảng giá](https://vd.test/gia) nhé")
    assert ket.text == "Xem bảng giá (https://vd.test/gia) nhé"


# ----------------------------------------------------------------------------- safety


def test_markdown_sang_style_zalo_safety_no_text_is_swallowed_every_non_markup_char_remains() -> None:
    """KHÔNG NUỐT CHỮ: mọi ký tự không phải dấu markdown đều còn lại"""
    # Luật số 1 của lớp làm sạch: hàm này chạm MỌI câu trả lời, nuốt chữ còn tệ hơn nhiều so với để lọt vài
    # ký tự định dạng.
    goc = "Anh Hải ơi, giá **45.000đ** cho *2 ly* - gồm cà phê & sữa (100% arabica)!"
    ket = markdown_sang_style_zalo(goc)
    for chu in ["Anh Hải ơi", "45.000đ", "2 ly", "cà phê & sữa", "100% arabica"]:
        assert chu in ket.text, f'mất đoạn "{chu}"'


def test_markdown_sang_style_zalo_safety_a_marker_char_produced_by_the_model_cannot_break_tokenising() -> (
    None
):
    """ký tự mốc do model sinh ra không phá được việc token hóa"""
    # MOC là U+0001. Model JSON escape ra nó được, và chuỗi dạng MOC+số+MOC va đúng token thì `ap_dung_inline`
    # sẽ nhét nhầm nội dung.
    doc = f"{chr(1)}0{chr(1)} và **đậm thật**"
    ket = markdown_sang_style_zalo(doc)
    assert chr(1) not in ket.text, "ký tự mốc phải bị dọn khỏi chữ"
    assert doan_cua(ket, 0) == "đậm thật", "đoạn đậm THẬT vẫn phải đúng chỗ"


def test_markdown_sang_style_zalo_safety_every_span_is_within_the_bounds_of_the_string() -> None:
    """mọi span đều nằm trong biên của chuỗi"""
    ket = markdown_sang_style_zalo("# Tiêu đề **đậm**\n- mục *nghiêng*\n  - lồng `code`")
    for s in ket.styles:
        assert s.start >= 0, f"start âm: {s.start}"
        assert s.start + s.length <= utf16_len(ket.text), (
            f"span vượt biên: {s.start}+{s.length} > {utf16_len(ket.text)}"
        )
        assert s.length > 0, "span rỗng không có nghĩa gì"


# ----------------------------------------------------------------------------- colours and underline

TEN = {
    Z.RED: "đỏ",
    Z.ORANGE: "cam",
    Z.YELLOW: "vàng",
    Z.GREEN: "xanh",
    Z.UNDERLINE: "gạch",
}
"""Bảng tra ngược: mã style của Zalo -> tên đọc được."""


def test_markdown_sang_style_zalo_colours_four_colours_and_underline_strip_the_tags_and_style_the_exact_text() -> (
    None
):
    """bốn màu và gạch chân bóc thẻ, tô đúng đoạn chữ"""
    # Cả 5 kiểu đã đo thật trên CẢ Zalo Web LẪN điện thoại - hiện y hệt nhau.
    ket = markdown_sang_style_zalo(
        "<do>đỏ</do> <cam>cam</cam> <vang>vàng</vang> <xanh>lá</xanh> <gach>gạch</gach>"
    )
    assert ket.text == "đỏ cam vàng lá gạch", "thẻ phải biến mất khỏi chữ"
    assert [(TEN[ZaloTextStyle(s.style)], doan_cua_style(ket, s)) for s in ket.styles] == [
        ("đỏ", "đỏ"),
        ("cam", "cam"),
        ("vàng", "vàng"),
        ("xanh", "lá"),
        ("gạch", "gạch"),
    ]


def test_markdown_sang_style_zalo_colours_tag_nested_with_bold_the_shape_of_an_invitation_label() -> None:
    """THẺ LỒNG với in đậm - đúng hình dạng nhãn của thư mời"""
    # Ca thường gặp nhất của màu. Bộ token hóa một tầng chỉ phát được span ngoài, còn dấu ** bên trong lọt ra
    # thành chữ.
    ket = markdown_sang_style_zalo("<cam>**Thời gian:**</cam> 7h00 thứ 7")
    assert ket.text == "Thời gian: 7h00 thứ 7", "dấu ** bên trong thẻ phải bị bóc"
    assert {s.style for s in ket.styles} == {Z.ORANGE, Z.BOLD}
    for s in ket.styles:
        assert doan_cua_style(ket, s) == "Thời gian:"


def test_markdown_sang_style_zalo_colours_nesting_the_other_way_round_also_yields_two_spans() -> None:
    """LỒNG NGƯỢC LẠI cũng phải ra đúng hai span"""
    # `**<cam>X</cam>**`: pass đậm cất nguyên thẻ màu vào kho rồi pass màu chỉ còn thấy token ở ngoài - thẻ
    # nằm trong kho sẽ thành chữ trần nếu không token hóa lại chính nội dung đã cất.
    ket = markdown_sang_style_zalo("**<cam>Đặc biệt</cam>**")
    assert ket.text == "Đặc biệt"
    assert {s.style for s in ket.styles} == {Z.ORANGE, Z.BOLD}


def test_markdown_sang_style_zalo_colours_colour_nested_with_italic_the_shape_of_a_verse() -> None:
    """màu lồng với NGHIÊNG - đúng hình dạng câu thơ"""
    ket = markdown_sang_style_zalo("<xanh>*Tháng Tám chớm thu*</xanh>")
    assert ket.text == "Tháng Tám chớm thu"
    assert {s.style for s in ket.styles} == {Z.GREEN, Z.ITALIC}


def test_markdown_sang_style_zalo_colours_uppercase_tags_are_accepted_the_model_is_inconsistent_about_case() -> (
    None
):
    """thẻ viết HOA vẫn nhận - model không nhất quán chuyện hoa thường"""
    ket = markdown_sang_style_zalo("<CAM>nhãn</CAM>")
    assert ket.text == "nhãn"
    assert ket.styles[0].style == Z.ORANGE


def test_markdown_sang_style_zalo_colours_unclosed_tag_keeps_the_text_never_swallows_it() -> None:
    """thẻ KHÔNG ĐÓNG thì giữ nguyên chữ, tuyệt đối không nuốt"""
    # Luật số 1 của lớp này: nuốt chữ tệ hơn nhiều so với để lọt vài ký tự thẻ.
    ket = markdown_sang_style_zalo("<cam>quên đóng thẻ")
    assert ket.text == "<cam>quên đóng thẻ"
    assert ket.styles == []


def test_markdown_sang_style_zalo_colours_tags_inside_a_code_block_stay_verbatim_not_colours() -> None:
    """thẻ nằm TRONG KHỐI CODE giữ nguyên xi, không thành màu"""
    ket = markdown_sang_style_zalo("Ví dụ:\n```html\n<do>chữ đỏ</do>\n```")
    assert "<do>chữ đỏ</do>" in ket.text, "code phải giữ nguyên thẻ"
    assert ket.styles == []


def test_markdown_sang_style_zalo_colours_every_span_of_a_multi_colour_message_is_in_bounds_and_points_at_the_right_text() -> (
    None
):
    """mọi span của tin nhiều màu đều nằm trong biên và trỏ đúng chữ"""
    thu_moi = "\n".join(
        [
            "## 🌟 <cam>**THƯ MỜI KHÓA THIỀN**</cam> 🌟",
            "",
            "- 🌿 <cam>**Thời gian:**</cam> <do>**7h00 thứ 7 ngày 08/08**</do>",
            "- 📮 <cam>**Địa chỉ:**</cam> Chùa Từ Tân, Bảy Hiền",
            "",
            "<xanh>*Tháng Tám chớm thu gió dịu hiền,*</xanh>",
            "<xanh>*Lời hẹn khóa thiền giữ vẹn nguyên*</xanh>",
        ]
    )
    ket = markdown_sang_style_zalo(thu_moi)

    assert "<" not in ket.text, f"còn sót thẻ trong chữ: {ket.text}"
    assert "**" not in ket.text, "còn sót dấu đậm"
    for s in ket.styles:
        assert s.start >= 0, "span âm"
        assert s.length > 0, "span rỗng"
        assert s.start + s.length <= utf16_len(ket.text), "span vượt biên"
        doan = doan_cua_style(ket, s)
        assert "<" not in doan, f"span dính ký tự thẻ: {doan}"
        assert "*" not in doan, f"span dính ký tự đậm: {doan}"


# ----------------------------------------------------------------------------- multi-line markers


def test_markdown_sang_style_zalo_multiline_colour_tag_around_a_multi_line_block_one_span_per_line_no_tag_leaks() -> (
    None
):
    """thẻ màu bọc cả khối nhiều dòng: mỗi dòng một span, không lọt thẻ"""
    # Đo trên tin thật: model bọc CẢ BÀI THƠ trong một cặp <xanh>. Vòng lặp xử theo dòng nên cặp đó không bao
    # giờ khớp, người dùng nhận nguyên chuỗi "<xanh>" giữa bài.
    ket = markdown_sang_style_zalo("<xanh>Câu một,\nCâu hai,\nCâu ba.</xanh>")
    assert ket.text == "Câu một,\nCâu hai,\nCâu ba.", "không được sót ký tự thẻ"
    assert [(s.style, doan_cua_style(ket, s)) for s in ket.styles] == [
        (Z.GREEN, "Câu một,"),
        (Z.GREEN, "Câu hai,"),
        (Z.GREEN, "Câu ba."),
    ]


def test_markdown_sang_style_zalo_multiline_bold_spanning_two_lines_is_also_spread_per_line() -> None:
    """in đậm vắt hai dòng cũng rải theo dòng"""
    # Model viết tiêu đề hai dòng: `**THƯ MỜI THAM GIA\nKHÓA THIỀN...**`
    ket = markdown_sang_style_zalo("**THƯ MỜI THAM GIA\nKHÓA THIỀN THÁNG 8**")
    assert ket.text == "THƯ MỜI THAM GIA\nKHÓA THIỀN THÁNG 8"
    assert [doan_cua_style(ket, s) for s in ket.styles] == ["THƯ MỜI THAM GIA", "KHÓA THIỀN THÁNG 8"]


def test_markdown_sang_style_zalo_multiline_tag_wrapping_bold_both_spanning_lines_the_invitation_title_shape() -> (
    None
):
    """THẺ BỌC ĐẬM cùng vắt dòng - đúng hình dạng tiêu đề thư mời"""
    # Ca khó nhất: rải thẻ trước thì ra `<cam>**A</cam>` - dấu sao mất vế đóng trên dòng đó rồi lọt ra thành
    # chữ. Phải rải `**` trước.
    ket = markdown_sang_style_zalo("<cam>**THƯ MỜI\nTHÁNG 8**</cam>")
    assert ket.text == "THƯ MỜI\nTHÁNG 8", "không được sót dấu sao hay thẻ"
    theo_doan: dict[str, set[str]] = {}
    for s in ket.styles:
        theo_doan.setdefault(doan_cua_style(ket, s), set()).add(s.style)
    assert [(d, sorted(k)) for d, k in theo_doan.items()] == [
        ("THƯ MỜI", sorted([Z.BOLD, Z.ORANGE])),
        ("THÁNG 8", sorted([Z.BOLD, Z.ORANGE])),
    ]


def test_markdown_sang_style_zalo_multiline_blank_line_inside_a_block_is_not_wrapped_an_empty_span_is_corrupt_data() -> (
    None
):
    """DÒNG TRỐNG bên trong khối không bị bọc - span rỗng là dữ liệu hỏng"""
    ket = markdown_sang_style_zalo("<xanh>Câu một,\n\nCâu hai.</xanh>")
    for s in ket.styles:
        assert s.length > 0, "span rỗng"
    assert [doan_cua_style(ket, s) for s in ket.styles] == ["Câu một,", "Câu hai."]


def test_markdown_sang_style_zalo_multiline_unclosed_multi_line_tag_keeps_the_text() -> None:
    """thẻ vắt dòng mà KHÔNG ĐÓNG thì giữ nguyên chữ"""
    ket = markdown_sang_style_zalo("<xanh>Câu một,\nCâu hai.")
    assert ket.text == "<xanh>Câu một,\nCâu hai."
    assert ket.styles == []


def test_markdown_sang_style_zalo_multiline_a_pair_inside_one_line_is_left_alone() -> None:
    """cặp dấu trong MỘT dòng không bị đụng tới"""
    ket = markdown_sang_style_zalo("Giá **45.000đ** và <cam>khuyến mãi</cam>")
    assert ket.text == "Giá 45.000đ và khuyến mãi"
    assert len(ket.styles) == 2


# ----------------------------------------------------------------------------- additions of the port (UTF-16)

EMOJI = "\U0001f600"


def test_markdown_sang_style_zalo_utf16_astral_characters_before_and_inside_spans_keep_spans_exact() -> None:
    """(port) emoji ngoài BMP trước và TRONG span: start/length là đơn vị UTF-16 trên chữ trả về"""
    ket = markdown_sang_style_zalo(f"{EMOJI} đầu **a{EMOJI}b** giữa *c* cuối {EMOJI} **d**")
    assert ket.text == f"{EMOJI} đầu a{EMOJI}b giữa c cuối {EMOJI} d"
    spans = {doan_cua_style(ket, s): s for s in ket.styles}
    assert set(spans) == {f"a{EMOJI}b", "c", "d"}
    assert spans[f"a{EMOJI}b"].length == 4  # a + pair + b
    assert spans[f"a{EMOJI}b"].start == 2 + 1 + 3 + 1  # pair, space, "đầu", space
    # each slice is whole characters: no lone surrogate on either side
    for s in ket.styles:
        doan_cua_style(ket, s).encode("utf-8")


def test_markdown_sang_style_zalo_utf16_heading_with_emoji_covers_the_whole_line_in_units() -> None:
    """(port) tiêu đề có emoji: Big + Bold phủ đúng số đơn vị UTF-16 của dòng"""
    ket = markdown_sang_style_zalo(f"## {EMOJI}{EMOJI} Tin\nvăn xuôi")
    assert ket.text == f"{EMOJI}{EMOJI} Tin\nvăn xuôi"
    assert sorted((s.start, s.length, s.style) for s in ket.styles) == sorted(
        [(0, 8, Z.BIG.value), (0, 8, Z.BOLD.value)]
    )


def test_markdown_sang_style_zalo_utf16_spans_after_a_blank_line_drop_and_emoji_stay_aligned() -> None:
    """(port) bỏ dòng trống + emoji ở dòng trên: span dòng sau vẫn trỏ đúng"""
    ket = markdown_sang_style_zalo(f"Mở đầu {EMOJI}:\n\n- mục **một** {EMOJI}\n- mục **hai**")
    assert ket.text == f"Mở đầu {EMOJI}:\n- mục một {EMOJI}\n- mục hai"
    assert [doan_cua_style(ket, s) for s in ket.styles] == ["một", "hai"]


def test_dong_ke_bang_tuong_duong_bieu_thuc_goc() -> None:
    """(port) kiểm tra dòng kẻ bảng viết tuyến tính khớp biểu thức gốc `^\\s*\\|?[-:|\\s]*--[-:|\\s]*\\|?\\s*$`"""
    goc = re.compile(f"{JS_S}*\\|?[-:|{JS_WS_CHARS}]*--[-:|{JS_WS_CHARS}]*\\|?{JS_S}*\\Z")
    for n in range(0, 7):
        for chars in itertools.product("-:| x\t", repeat=n):
            dong = "".join(chars)
            literal = goc.match(dong) is not None and "-" in dong
            # a table-separator line is dropped from the output; a data line is kept
            ket = markdown_sang_style_zalo(f"a\n{dong}\nb")
            dropped = ket.text == "a\nb"
            if dong.strip() == "":
                continue  # blank lines follow the blank-line rules, not the table rule
            if "x" in dong:
                assert not literal
                continue
            assert dropped == literal, repr(dong)
