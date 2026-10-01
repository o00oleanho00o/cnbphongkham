# ported from: src/zalo/sanitize-reply-text.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Module thuần - không cần setup môi trường.
"""

from __future__ import annotations

import re
import time

from pema.agent.prompt_leak_markers import DAU_HIEU_RO_PROMPT
from pema.channels.sanitize_reply_text import (
    co_dau_hieu_ro_prompt,
    lam_sach_giu_dinh_dang,
    lam_sach_tra_loi,
)
from pema.scheduler.silent_sentinel import la_dong_sentinel


def sach(t: str) -> str:
    return lam_sach_tra_loi(t).text


# ------------------------------------------------------------- bỏ markdown, GIỮ nội dung


def test_lam_sach_tra_loi_strip_markdown_bold() -> None:
    """in đậm"""
    assert sach("Giá vàng **tăng mạnh** hôm nay") == "Giá vàng tăng mạnh hôm nay"


def test_lam_sach_tra_loi_strip_markdown_italic() -> None:
    """in nghiêng"""
    assert sach("Đây là *ghi chú* nhỏ") == "Đây là ghi chú nhỏ"


def test_lam_sach_tra_loi_strip_markdown_bold_and_italic_together_bold_first_so_no_stray_star_remains() -> (
    None
):
    """đậm và nghiêng lồng nhau - đậm xử trước nên không còn dấu sao lẻ"""
    assert sach("**rất** *quan trọng*") == "rất quan trọng"
    assert "*" not in sach("**đậm** và *nghiêng*")


def test_lam_sach_tra_loi_strip_markdown_inline_code() -> None:
    """inline code"""
    assert sach("Chạy lệnh `pnpm dev` nhé") == "Chạy lệnh pnpm dev nhé"


def test_lam_sach_tra_loi_strip_markdown_code_block_keeps_content_drops_fence_and_language_label() -> None:
    """khối code - giữ nội dung, bỏ hàng rào và nhãn ngôn ngữ"""
    ra = sach("Đây là code:\n```js\nconst a = 1;\n```\nXong rồi")
    assert "```" not in ra, ra
    assert "js\n" not in ra, f"nhãn ngôn ngữ phải bị bỏ: {ra}"
    assert re.search(r"const a = 1;", ra)
    assert re.search(r"Xong rồi", ra)


def test_lam_sach_tra_loi_strip_markdown_code_block_written_on_one_line_keeps_its_content() -> None:
    """khối code viết trên MỘT dòng giữ nguyên nội dung"""
    # Vòng rà soát bắt được: bản đầu để `[^\n`]*\n?` ăn nhãn ngôn ngữ, nên với fence cùng dòng nó ăn luôn cả
    # thân và câu ra thành "Chạy  là xong"
    assert sach("Chạy ```pnpm dev``` là xong") == "Chạy pnpm dev là xong"
    assert sach("Dùng ```const a = 1``` nhé anh") == "Dùng const a = 1 nhé anh"


def test_lam_sach_tra_loi_strip_markdown_content_inside_a_code_block_is_not_eaten_by_the_markdown_steps() -> (
    None
):
    """nội dung TRONG khối code KHÔNG bị các bước markdown ăn tiếp"""
    # Bản đầu gỡ hàng rào NGAY nên `# Tính tổng` trong đoạn Python bị boTieuDe cắt mất dấu thăng - code trả về
    # sai cú pháp, người dùng copy về là lỗi
    ra = sach("```python\n# Tính tổng\ntong = 0\nx = a**2\n```")
    assert re.search(r"# Tính tổng", ra), f"dấu thăng của comment bị ăn: {ra}"
    assert re.search(r"a\*\*2", ra), f"luỹ thừa bị ăn: {ra}"
    assert "```" not in ra, ra


def test_lam_sach_tra_loi_strip_markdown_code_block_is_handled_before_inline_asserted_by_the_order_in_da_sua() -> (
    None
):
    """khối code xử TRƯỚC inline - khẳng định bằng THỨ TỰ trong daSua"""
    # Chỉ so nội dung ra là test ma: với đầu vào này hai thứ tự cho cùng kết quả nên đảo
    # `boKhoiCode`/`boInlineCode` mà test vẫn xanh. Đã đo thật. Thứ tự trong `da_sua` mới phân biệt được.
    kq = lam_sach_tra_loi("Xem `biến` rồi:\n```\nvar x = 1;\n```")
    assert kq.da_sua == ["khối code", "inline code"]
    assert re.search(r"var x = 1;", kq.text)
    assert re.search(r"Xem biến rồi:", kq.text)


def test_lam_sach_tra_loi_strip_markdown_backticks_inside_a_code_block_are_kept_not_eaten_by_the_inline_step() -> (
    None
):
    """dấu nháy đơn BÊN TRONG khối code được giữ, không bị bộ inline ăn"""
    kq = lam_sach_tra_loi("```\nvar x = `template`;\n```")
    assert kq.text == "var x = `template`;"
    assert kq.da_sua == ["khối code"], "không được có 'inline code' - nó nằm trong khối"


def test_lam_sach_tra_loi_strip_markdown_headings_of_every_level() -> None:
    """tiêu đề mọi cấp"""
    assert sach("# Tiêu đề\n## Mục nhỏ\n### Sâu hơn") == "Tiêu đề\nMục nhỏ\nSâu hơn"


def test_lam_sach_tra_loi_strip_markdown_link_keeps_both_text_and_url_the_url_is_real_information() -> None:
    """liên kết giữ CẢ chữ lẫn URL - URL là thông tin thật người dùng cần"""
    assert sach("Xem [báo cáo quý 3](https://vd.test/bc) nhé") == "Xem báo cáo quý 3 (https://vd.test/bc) nhé"


def test_lam_sach_tra_loi_strip_markdown_link_without_text_leaves_the_url() -> None:
    """liên kết không có chữ thì còn lại URL"""
    assert sach("[](https://vd.test/x)") == "https://vd.test/x"


def test_lam_sach_tra_loi_strip_markdown_url_with_params_and_trailing_space_does_not_lose_the_tail() -> None:
    """URL có tham số và khoảng trắng phía sau KHÔNG bị vứt phần đuôi"""
    # Bản đầu để `([^)\s]+)[^)]*` - phần sau khoảng trắng khớp nhưng không nằm trong nhóm nào nên bị vứt trắng
    assert (
        sach("Xem [tài liệu](https://vd.test/a?x=1 bản PDF) nhé")
        == "Xem tài liệu (https://vd.test/a?x=1 bản PDF) nhé"
    )


def test_lam_sach_tra_loi_strip_markdown_markdown_image_also_swallows_the_exclamation_mark() -> None:
    """ảnh markdown cũng bị nuốt dấu chấm than"""
    ra = sach("![biểu đồ](https://vd.test/a.png)")
    assert not ra.startswith("!"), ra
    assert re.search(r"vd\.test", ra)


# ------------------------------------------------------------- bảng markdown


def test_lam_sach_tra_loi_markdown_table_drops_the_separator_row_keeps_every_row_with_text() -> None:
    """bỏ dòng kẻ, GIỮ mọi dòng có chữ"""
    # Kịch bản nghiệm thu của phase: người dùng bảo "trình bày dạng bảng"
    ra = sach("| Sản phẩm | Giá |\n|---|---:|\n| Cà phê | 45.000 |\n| Trà | 30.000 |")
    assert "---" not in ra, f"còn dòng kẻ: {ra!r}"
    assert re.search(r"Sản phẩm", ra)
    assert re.search(r"Cà phê \| 45\.000", ra)
    assert re.search(r"Trà \| 30\.000", ra)


def test_lam_sach_tra_loi_markdown_table_plain_line_with_a_dash_is_not_mistaken_for_a_separator() -> None:
    """dòng chữ thường có gạch ngang KHÔNG bị nhận nhầm là dòng kẻ"""
    goc = "Giờ làm: 8h - 17h\n- Nghỉ trưa 12h - 13h"
    assert sach(goc) == goc


def test_lam_sach_tra_loi_markdown_table_line_of_only_dashes_without_a_pipe_is_kept() -> None:
    """dòng chỉ có gạch ngang nhưng KHÔNG có gạch đứng thì giữ nguyên"""
    assert sach("Phần một\n---\nPhần hai") == "Phần một\n---\nPhần hai"


def test_lam_sach_tra_loi_markdown_table_needs_at_least_two_adjacent_dashes_one_dash_is_data() -> None:
    """cần ÍT NHẤT hai gạch ngang liền nhau - một gạch là dữ liệu, không phải dòng kẻ"""
    # Docstring cam kết điều này; không có test thì nới thành một gạch vẫn xanh
    goc = "| 8h - 17h |\n| Ca 2 |"
    assert sach(goc) == goc
    assert sach("| A |\n| - |\n| 1 |") == "| A |\n| - |\n| 1 |"


# ------------------------------------------------------------- những thứ TUYỆT ĐỐI không được đụng


def test_lam_sach_tra_loi_never_touch_normal_vietnamese_reply_passes_through_unchanged_by_one_char() -> None:
    """câu trả lời tiếng Việt bình thường đi qua KHÔNG ĐỔI MỘT KÝ TỰ"""
    # Tiêu chí hoàn thành của phase - so sánh CHÍNH XÁC, không phải match
    goc = (
        "Chào anh Hải, em đã kiểm tra rồi ạ.\n"
        "- Đơn hàng số 1042: đã giao lúc 14h30 ngày 28/07\n"
        "- Đơn hàng số 1043: đang vận chuyển, dự kiến mai\n"
        "Anh cần em tra thêm gì nữa không ạ?"
    )
    kq = lam_sach_tra_loi(goc)
    assert kq.text == goc
    assert kq.da_sua == [], "không được báo là đã sửa gì"
    assert kq.chan is False


def test_lam_sach_tra_loi_never_touch_dash_bullets_stay_the_persona_teaches_the_bot_to_use_them() -> None:
    """gạch đầu dòng '-' giữ nguyên - persona đang DẠY bot dùng nó"""
    goc = "Có 3 việc:\n- Việc một\n- Việc hai\n- Việc ba"
    assert sach(goc) == goc


def test_lam_sach_tra_loi_never_touch_star_between_numbers_is_multiplication_not_italics() -> None:
    """dấu sao giữa số là phép nhân, không phải chữ nghiêng"""
    assert sach("Kết quả 2*3*4 = 24") == "Kết quả 2*3*4 = 24"
    assert sach("Diện tích = 5*4 mét") == "Diện tích = 5*4 mét"


def test_lam_sach_tra_loi_never_touch_star_with_spaces_on_both_sides_is_also_arithmetic() -> None:
    """dấu sao có khoảng trắng hai bên cũng là phép tính"""
    assert sach("Tính 12 * 5 * 2 giúp em") == "Tính 12 * 5 * 2 giúp em"


def test_lam_sach_tra_loi_never_touch_vietnamese_diacritics_survive_every_step_intact() -> None:
    """dấu tiếng Việt nguyên vẹn qua mọi bước xử lý"""
    kq = sach("**Đường Trần Hưng Đạo** có *quán phở* ngon lắm ạ")
    assert kq == "Đường Trần Hưng Đạo có quán phở ngon lắm ạ"
    # Đề phòng ai đó chữa regex bằng cách chuẩn hóa Unicode
    for ky_tu in ("ườ", "ạ", "ở"):
        assert ky_tu in kq


def test_lam_sach_tra_loi_never_touch_hash_mid_sentence_hashtag_is_not_a_heading() -> None:
    """dấu thăng giữa câu (hashtag) không bị coi là tiêu đề"""
    assert sach("Mã đơn #1042 nhé") == "Mã đơn #1042 nhé"


def test_lam_sach_tra_loi_never_touch_hash_glued_to_text_at_line_start_is_not_a_heading_a_space_is_required() -> (
    None
):
    """dấu thăng ĐẦU DÒNG dính liền chữ cũng không phải tiêu đề - cần khoảng trắng"""
    # Markdown đòi khoảng trắng sau dấu thăng. Bỏ đòi hỏi đó thì mã đơn đứng đầu dòng bị cắt mất dấu thăng
    assert sach("#1042 đã giao xong") == "#1042 đã giao xong"
    assert sach("Đơn:\n#1042 đã giao") == "Đơn:\n#1042 đã giao"


def test_lam_sach_tra_loi_never_touch_double_star_with_spaces_inside_is_arithmetic_not_bold() -> None:
    """cặp hai dấu sao có khoảng trắng bên trong là phép tính, không phải in đậm"""
    assert sach("Tính 12 ** 5 ** 2 giúp em") == "Tính 12 ** 5 ** 2 giúp em"


def test_lam_sach_tra_loi_never_touch_python_power_2_pow_3_pow_2_stays_left_flanking_like_the_single_star() -> (
    None
):
    """luỹ thừa Python 2**3**2 giữ nguyên - đúng luật left-flanking như dấu sao đơn"""
    assert sach("Trong Python 2**3**2 = 512 nhé") == "Trong Python 2**3**2 = 512 nhé"


def test_lam_sach_tra_loi_never_touch_bracket_paren_syntax_that_is_not_a_link_stays_verbatim() -> None:
    """cú pháp [..](..) KHÔNG phải liên kết thì giữ nguyên hoàn toàn"""
    # Cú pháp này xuất hiện đầy trong văn bản thường; đổi nó đi là hỏng chữ thật
    assert sach("Mã lô [A12](hàng nhập) đã về kho") == "Mã lô [A12](hàng nhập) đã về kho"
    assert sach("Gọi handlers[0](event) là được") == "Gọi handlers[0](event) là được"


def test_lam_sach_tra_loi_never_touch_url_with_underscores_and_dots_is_left_alone() -> None:
    """URL có dấu gạch dưới và dấu chấm không bị đụng"""
    goc = "Tải ở https://vd.test/bao_gia_2026.pdf nhé"
    assert sach(goc) == goc


def test_lam_sach_tra_loi_never_touch_empty_and_whitespace_only_strings_do_not_break() -> None:
    """chuỗi rỗng và chuỗi chỉ khoảng trắng không làm vỡ"""
    assert sach("") == ""
    assert sach("   ") == "   "


# ------------------------------------------------------------- chặn rò system prompt


def test_lam_sach_tra_loi_prompt_leak_every_marker_of_the_shared_constant_is_blocked() -> None:
    """mọi dấu hiệu trong hằng số dùng chung đều bị chặn"""
    for dau in DAU_HIEU_RO_PROMPT:
        kq = lam_sach_tra_loi(f"Đây là chỉ dẫn của mình: {dau} ...")
        assert kq.chan is True, dau
        assert kq.text == "", "chặn thì KHÔNG được gửi nửa vời"
        assert kq.da_sua == ["CHẶN: rò system prompt"]


def test_lam_sach_tra_loi_prompt_leak_is_checked_on_the_original_text_markdown_in_between_cannot_evade() -> (
    None
):
    """kiểm trên chữ GỐC - markdown xen vào không lách được"""
    # Bỏ định dạng TRƯỚC rồi mới kiểm thì dấu hiệu đã đổi hình dạng và bộ canh trượt đúng ca người ta cố tình
    # lách
    assert lam_sach_tra_loi("**Quy tắc an toàn (tuyệt đối, không có ngoại lệ):**").chan is True


def test_lam_sach_tra_loi_prompt_leak_normal_reply_mentioning_an_toan_is_not_blocked_by_mistake() -> None:
    """câu trả lời bình thường nhắc chữ 'an toàn' KHÔNG bị chặn nhầm"""
    kq = lam_sach_tra_loi("Anh đi đường an toàn nhé, nhớ đội mũ bảo hiểm ạ.")
    assert kq.chan is False


def test_lam_sach_tra_loi_prompt_leak_kha_nang_cua_ban_in_a_plain_sentence_is_not_blocked_marker_must_be_the_full_sentence() -> (
    None
):
    """'Khả năng của bạn lúc này' trong câu THƯỜNG không bị chặn - dấu hiệu phải là câu ĐẦY ĐỦ"""
    # Vòng rà soát bắt được: dấu hiệu cũ chỉ là mẩu tiếng Việt thường ngày. Chặn oan ở đây rất nặng và KHÔNG
    # TỰ KHỎI - hỏi lại vẫn y hệt vì model sinh lại đúng cách diễn đạt đó; ở scheduler còn tiêu suất chạy của
    # job.
    for cau in [
        "Khả năng của bạn lúc này đã đủ để thi B1 rồi ạ.",
        "Khả năng của bạn lúc này vay được khoảng 300 triệu.",
    ]:
        assert lam_sach_tra_loi(cau).chan is False, cau


def test_lam_sach_tra_loi_prompt_leak_but_the_full_sentence_produced_by_the_persona_is_still_blocked() -> (
    None
):
    """nhưng câu ĐẦY ĐỦ do persona sinh ra thì vẫn chặn"""
    assert lam_sach_tra_loi("Khả năng của bạn lúc này (đúng những công cụ đang bật, không hơn):").chan is True
    assert lam_sach_tra_loi("Khả năng của bạn lúc này: KHÔNG có công cụ nào được bật").chan is True


def test_lam_sach_tra_loi_prompt_leak_co_dau_hieu_ro_prompt_is_usable_on_its_own() -> None:
    """coDauHieuRoPrompt dùng được độc lập"""
    assert co_dau_hieu_ro_prompt("bình thường") is False
    assert co_dau_hieu_ro_prompt("<noi_dung_ngoai nguon=...") is True


def test_cac_chu_so_huu_khong_con_ban_sao_dau_hieu_va_sentinel_cung_mot_nguon() -> None:
    """(port) không còn bản sao: dấu hiệu rò prompt và dòng sentinel đến từ module chủ (D1, S)"""
    from pema.channels import sanitize_reply_text as module

    assert module.DAU_HIEU_RO_PROMPT is DAU_HIEU_RO_PROMPT
    assert module.la_dong_sentinel is la_dong_sentinel
    for line in ["[SILENT]", " [ silent ] ", "\ufeff[SILENT]", "[SILENT]\u00a0"]:
        assert la_dong_sentinel(line) is True, repr(line)
    for line in ["", "x [SILENT]", "[SILENT] là nhãn"]:
        assert la_dong_sentinel(line) is False, repr(line)


# ------------------------------------------------------------- nhãn [SILENT] lọt vào lượt chat thường


def test_lam_sach_tra_loi_silent_label_own_line_is_dropped_the_rest_is_kept() -> None:
    """dòng [SILENT] riêng bị bỏ, phần còn lại giữ nguyên"""
    kq = lam_sach_tra_loi("Hôm nay có 2 tin mới ạ.\n\n[SILENT]")
    assert kq.text == "Hôm nay có 2 tin mới ạ."
    assert "nhãn [SILENT]" in kq.da_sua


def test_lam_sach_tra_loi_silent_label_at_the_start_is_dropped_too() -> None:
    """[SILENT] đứng đầu cũng bị bỏ"""
    assert lam_sach_tra_loi("[SILENT]\nKhông có gì mới.").text == "Không có gì mới."


def test_lam_sach_tra_loi_silent_label_in_the_middle_of_a_sentence_is_kept_it_is_real_text() -> None:
    """[SILENT] nằm GIỮA câu giữ nguyên - đó là chữ thật, không phải nhãn"""
    goc = "Mình định [SILENT] nhưng đây là tóm tắt hôm nay: có 3 tin."
    assert lam_sach_tra_loi(goc).text == goc


def test_lam_sach_tra_loi_silent_label_line_starting_with_silent_but_with_real_content_is_kept_whole() -> (
    None
):
    """dòng MỞ ĐẦU bằng [SILENT] nhưng có nội dung thật thì GIỮ NGUYÊN CẢ DÒNG"""
    # Vòng rà soát bắt được: bản đầu đem `isSilentResponse` (hàm phán xét CẢ câu trả lời, có luật "mở đầu bằng
    # [SILENT] thì nuốt cả câu") đi lọc TỪNG DÒNG. Kết quả: câu trả lời hợp lệ khi người dùng hỏi về chính cái
    # nhãn bị vứt sạch, người nhắn ngồi im không nhận gì.
    goc = "[SILENT] là nhãn nội bộ, dùng để bot im lặng khi không có tin mới ạ."
    assert lam_sach_tra_loi(goc).text == goc
    assert lam_sach_tra_loi(goc).da_sua == [], "không được đụng gì"

    hai = "[SILENT] không có gì mới\nCảm ơn anh đã hỏi ạ"
    assert lam_sach_tra_loi(hai).text == hai


# ------------------------------------------------------------- không ăn tham trên câu dài


def test_lam_sach_tra_loi_greedy_2000_char_reply_full_of_special_characters_still_keeps_the_right_text() -> (
    None
):
    """câu 2000 ký tự nhiều ký tự đặc biệt vẫn giữ đúng phần chữ"""
    khoi = "Mục **quan trọng** với `mã lệnh` và [liên kết](https://vd.test/a) - dòng thường 2*3.\n"
    goc = khoi * 30
    assert len(goc) > 2000, f"mới {len(goc)} ký tự"
    ra = sach(goc)

    assert "**" not in ra, "còn sót dấu sao đôi"
    assert "`" not in ra, "còn sót dấu nháy"
    assert "](" not in ra, "còn sót cú pháp liên kết"
    # Đếm để chắc regex không nuốt mất cả đoạn ở giữa
    assert ra.count("quan trọng") == 30
    assert ra.count("2*3") == 30, "phép nhân phải còn đủ 30 chỗ"
    assert ra.count("- dòng thường") == 30, "gạch đầu dòng phải còn đủ"


def test_lam_sach_tra_loi_greedy_unpaired_stars_neither_hang_nor_swallow_text() -> None:
    """dấu sao lẻ không cặp không làm treo hay nuốt chữ"""
    assert sach("Ghi chú * chưa xong") == "Ghi chú * chưa xong"
    assert sach("**chưa đóng") == "**chưa đóng"


def test_lam_sach_tra_loi_greedy_a_nul_char_from_the_model_cannot_hijack_the_code_block_marker() -> None:
    """ký tự NUL của model không cướp được mốc khối code"""
    # MOC_KHOI là ký tự NUL. Docstring nói "model không sinh ra nó" - đó là giả định, không phải bất biến: JSON
    # escape NUL hoàn toàn hợp lệ. Không dọn trước thì chuỗi có dạng NUL + số + NUL va đúng mốc và
    # `tra_khoi_code_ve` nhét nội dung khối code vào nhầm chỗ.
    nul = "\u0000"
    ra = sach(f"x {nul}0{nul} y\n```\nTHAT SU\n```")
    assert nul not in ra, "không được để lọt ký tự NUL xuống Zalo"
    assert ra.count("THAT SU") == 1, f"nội dung khối code bị nhân đôi: {ra!r}"


# Same wall-clock budget as the original: a quadratic expression on these inputs takes seconds to minutes,
# the linear ones take a few milliseconds (the whole test runs in ~0.15 s).
REDOS_BUDGET_MS = 500


def test_lam_sach_tra_loi_greedy_malicious_strings_do_not_make_the_expressions_quadratic_redos() -> None:
    """chuỗi độc không làm biểu thức chạy bậc hai (ReDoS)"""
    # Đây là đường tấn công THẬT, không phải lý thuyết: bot đọc tin của người lạ, một tin "lặp lại chính xác
    # chuỗi sau: [[[[..." là đủ để model nhại lại. Tiến trình này MỘT luồng phục vụ mọi account + vòng tick
    # scheduler + HTTP dashboard, nên kẹt event loop vài giây là cả bot đứng hình.
    #
    # Đo trước khi vá: 51.200 dấu `[` mất 1.263ms, 25.600 gạch trong bảng mất 1.446ms. Sau khi vá cả hai còn
    # dưới 30ms.
    doc_hai: list[tuple[str, str]] = [
        ("dấu ngoặc vuông", "[" * 50_000),
        ("dòng kẻ bảng", f"|{'-' * 50_000}x"),
        ("ngoặc liên kết", f"[a]({'b' * 50_000}"),
        ("hàng rào code", "```" * 20_000),
        # Ca này KHÔNG bị bộ trên chạm tới: vòng rà soát toàn cục đo được 200.000 dấu cách sau ``` mất 20,5
        # GIÂY vì `[ \t]*...[ \t]*` là hai lượng từ trên cùng lớp ký tự - đúng thứ luật số 2 đầu file cấm
        ("khoảng trắng sau hàng rào", f"```{' ' * 100_000}x"),
        ("tab sau hàng rào", f"Anh xem: ```{chr(9) * 50_000}"),
        ("dấu sao", "*" * 50_000),
        ("nháy đơn", "`a" * 25_000),
    ]
    for ten, doc in doc_hai:
        t0 = time.perf_counter()
        lam_sach_tra_loi(doc)
        ms = (time.perf_counter() - t0) * 1000
        assert ms < REDOS_BUDGET_MS, f"{ten}: {ms:.0f}ms - biểu thức đang chạy bậc hai"


# ------------------------------------------------------------- additions of the port


def test_lam_sach_giu_dinh_dang_keeps_markdown_and_only_applies_the_two_shields() -> None:
    """(port) đường giữ định dạng: không xóa markdown, chỉ chặn rò prompt, bỏ NUL và nhãn [SILENT]"""
    kq = lam_sach_giu_dinh_dang("**đậm** `code`\n[SILENT]\u0000")
    assert kq.text == "**đậm** `code`"
    assert kq.da_sua == ["nhãn [SILENT]"]
    assert lam_sach_giu_dinh_dang("<noi_dung_ngoai x").chan is True


def test_la_dong_sentinel_uses_the_js_whitespace_set() -> None:
    """(port) trim / \\s của JS: U+FEFF và U+00A0 là khoảng trắng, U+0085 thì không"""
    assert la_dong_sentinel("\ufeff[SILENT]\u00a0") is True
    assert la_dong_sentinel("[ \u00a0s i l e n t ]") is True
    assert la_dong_sentinel("[SILENT]\u0085") is False
    assert la_dong_sentinel("[SILENT] x") is False


def test_lam_sach_tra_loi_heading_and_table_rules_follow_js_multiline_line_breaks() -> None:
    """(port) ^ và $ chế độ nhiều dòng của JS cũng ngắt ở CR, U+2028, U+2029"""
    assert sach("Mở\r## Tiêu đề") == "Mở\rTiêu đề"
    assert sach("Mở\u2028# Tiêu đề") == "Mở\u2028Tiêu đề"
    assert sach("a\r\n|---|\r\nb") == "a\r\nb"
    assert sach("a\n|---|\u2028b") == "a\n\u2028b"
