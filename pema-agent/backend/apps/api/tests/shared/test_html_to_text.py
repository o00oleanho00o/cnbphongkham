# ported from: src/shared/html-to-text.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Module thuần (chỉ kéo theo html_entities) nên import tĩnh được. Giữ được điều đó là lý do ``strip_html_tags``
nằm ở đây chứ không ở ``web_search_providers.py``.
"""

from __future__ import annotations

import re
import time

from pema.shared.html_to_text import extract_html_title, html_to_readable_text, strip_html_tags

# ------------------------------------------------------------------ stripHtmlTags


def test_strip_html_tags_removes_tags_decodes_numeric_entities_collapses_whitespace() -> None:
    """bỏ thẻ, giải entity số (giữ dấu tiếng Việt), gộp khoảng trắng"""
    # &#225; = á, &#224; = à - entity số hay gặp trong kết quả DDG tiếng Việt
    assert strip_html_tags("<b>Gi&#225;\n  v&#224;ng</b> h&#244;m nay &amp; mai") == "Giá vàng hôm nay & mai"
    assert strip_html_tags("&quot;t&#7889;t&quot; &#39;ok&#39;") == "\"tốt\" 'ok'"


# ------------------------------------------------------------------ htmlToReadableText


def test_html_to_readable_text_drops_script_style_nav_keeps_main_content_by_line() -> None:
    """bỏ script/style/nav, giữ nội dung chính theo dòng"""
    html = """<html><head><title>Trang</title><style>.a{color:red}</style></head>
      <body>
        <nav><a href="/">Menu rác</a></nav>
        <script>alert("xss")</script>
        <h1>Tiêu đề bài</h1>
        <p>Đoạn một có <b>chữ đậm</b>.</p>
        <p>Đoạn hai.</p>
        <footer>Bản quyền</footer>
      </body></html>"""
    text = html_to_readable_text(html)

    assert "alert" not in text, "script phải bị bỏ"
    assert "color:red" not in text, "style phải bị bỏ"
    assert "Menu rác" not in text, "nav phải bị bỏ"
    assert "Bản quyền" not in text, "footer phải bị bỏ"
    assert text.split("\n") == ["Tiêu đề bài", "Đoạn một có chữ đậm.", "Đoạn hai."]


def test_html_to_readable_text_li_becomes_bullet() -> None:
    """thẻ li thành gạch đầu dòng"""
    text = html_to_readable_text("<ul><li>Một</li><li>Hai</li></ul>")
    assert text.split("\n") == ["- Một", "- Hai"]


def test_html_to_readable_text_empty_or_all_junk_html_returns_empty_string() -> None:
    """HTML rỗng/toàn rác trả chuỗi rỗng, không throw"""
    assert html_to_readable_text("<script>x</script>") == ""
    assert html_to_readable_text("") == ""


def test_html_to_readable_text_menu_list_dropped_real_content_list_kept() -> None:
    """list menu (chữ nằm hết trong link) bị vứt, list nội dung thật được giữ"""
    html = """
      <ul>
        <li><a href="/">Home</a></li>
        <li><a href="/mien-nam">Miền Nam</a></li>
        <li><a href="/mien-bac">Miền Bắc</a></li>
        <li><a href="/truc-tiep">Trực Tiếp Xổ Số</a></li>
      </ul>
      <p>Kết quả kỳ quay 19/07.</p>
      <ul>
        <li>Giải đặc biệt quay lúc 16h15 mỗi ngày</li>
        <li>Đối chiếu tại <a href="/so-ket-qua">sổ kết quả</a> trong 30 ngày</li>
      </ul>"""
    text = html_to_readable_text(html)

    assert "Home" not in text, "menu điều hướng phải bị vứt"
    assert "Miền Nam" not in text
    assert "Kết quả kỳ quay 19/07." in text
    assert "- Giải đặc biệt quay lúc 16h15 mỗi ngày" in text, "list nội dung phải còn"
    assert "sổ kết quả" in text, "link nằm trong câu văn không bị tính là menu"


def test_html_to_readable_text_nested_menu_removed_over_several_passes() -> None:
    """menu lồng menu con vẫn bị gỡ sạch qua nhiều lượt"""
    html = """
      <ul><li><a href="/">Trang chủ</a>
        <ul><li><a href="/a">Mục A</a></li><li><a href="/b">Mục B</a></li><li><a href="/c">Mục C</a></li></ul>
      </li><li><a href="/x">Mục X</a></li><li><a href="/y">Mục Y</a></li></ul>
      <p>Nội dung thật.</p>"""
    text = html_to_readable_text(html)
    assert "Mục A" not in text
    assert "Mục X" not in text, "menu lồng phải bị gỡ hết"
    assert text == "Nội dung thật."


def test_html_to_readable_text_form_select_header_dropped_lottery_lookup_block() -> None:
    """form/select/header bị bỏ (khối 'Ngày: Tỉnh: Vé Số:' kiểu trang dò vé)"""
    html = """
      <header><h1>Logo to đùng</h1></header>
      <form>Ngày: <select><option>19/07</option><option>18/07</option></select> Tỉnh: Đà Lạt</form>
      <p>Bảng kết quả ở đây.</p>"""
    text = html_to_readable_text(html)
    assert "Logo" not in text, "header phải bị bỏ nhưng head vẫn xử lý riêng"
    assert "Ngày:" not in text, "form phải bị bỏ"
    assert "19/07</option>" not in text
    assert "18/07" not in text, "option phải bị bỏ"
    assert text == "Bảng kết quả ở đây."


def test_html_to_readable_text_table_cells_in_a_row_separated_by_pipe() -> None:
    """bảng: ô cùng hàng ngăn bằng ' | ' để số không dính liền nhau"""
    html = """<table>
      <tr><td>Giải đặc biệt</td><td>123456</td></tr>
      <tr><td>Giải nhất</td><td>65432</td></tr>
    </table>"""
    text = html_to_readable_text(html)
    assert "Giải đặc biệt | 123456" in text, f"thiếu ngăn cách cột: {text}"
    assert "Giải nhất | 65432" in text


def test_html_to_readable_text_named_entity_in_content_is_decoded() -> None:
    """entity tên trong nội dung được giải mã (CHUY&Ecirc;N -> CHUYÊN)"""
    assert html_to_readable_text("<p>CHUY&Ecirc;N TRANG KẾT QUẢ</p>") == "CHUYÊN TRANG KẾT QUẢ"


def test_html_to_readable_text_numbers_in_adjacent_spans_do_not_clump() -> None:
    """số trong các span liền kề không dính chùm (markup kiểu xoso.com.vn)"""
    # Site bọc mỗi con số kết quả trong 1 span - bóc thẻ trần ra "36910..." vô dụng
    html = "<div><span>36</span><span>910</span><span>4644</span> <span>6422</span></div>"
    assert html_to_readable_text(html) == "36 910 4644 6422"


def test_html_to_readable_text_html5_table_without_closing_td_tr_still_splits_rows_and_columns() -> None:
    """bảng HTML5 bỏ thẻ đóng </td></tr> vẫn tách được hàng và cột"""
    # Đúng markup thật của xoso.com.vn: <tr><td>8<td><span>36</span><tr>...
    html = (
        "<table><tr><td class=name-prize>8<td><span data-loto=36>36</span>"
        "<tr><td class=name-prize>7<td><span data-loto=910>910</span>"
        "<tr><td class=name-prize>ĐB<td><span data-loto=087842>087842</span></table>"
    )
    text = html_to_readable_text(html)
    assert "836" not in text, f'hàng phải tách, không dính "8"+"36": {text}'
    assert re.search(r"8\s*\|\s*36", text), f"thiếu ranh giới cột hàng G8: {text}"
    assert re.search(r"ĐB\s*\|\s*087842", text), f"thiếu ranh giới cột hàng ĐB: {text}"


def test_html_to_readable_text_single_span_inside_word_not_split() -> None:
    """span đơn giữa từ không bị chẻ đôi"""
    assert html_to_readable_text("<p>Gi<span>á</span> vàng</p>") == "Giá vàng"


def test_html_to_readable_text_multiline_tag_is_still_stripped_tuoitre_markup() -> None:
    """thẻ viết tràn nhiều dòng vẫn bị bóc (markup thật của tuoitre.vn)"""
    # Bóc thẻ chạy trên TỪNG DÒNG nên thẻ xuống dòng giữa chừng từng lọt nguyên
    # markup vào text gửi cho model
    html = """<div><input onfocus="this.removeAttribute('readonly');" class="input-search"
placeholder="Nhập nội dung cần tìm" />
<p>Giá vàng hôm nay tăng</p></div>"""
    text = html_to_readable_text(html)
    assert "<input" not in text, f"còn markup trong text: {text}"
    assert "placeholder" not in text, f"còn thuộc tính trong text: {text}"
    assert "Giá vàng hôm nay tăng" in text


def test_html_to_readable_text_block_tag_broken_across_lines_still_splits_paragraphs() -> None:
    """thẻ block xuống dòng giữa chừng vẫn tách được đoạn"""
    html = '<p\nclass="intro">Đoạn một</p>\n<p>Đoạn hai</p>'
    assert html_to_readable_text(html) == "Đoạn một\nĐoạn hai"


def test_html_to_readable_text_less_than_sign_in_prose_not_mistaken_for_tag() -> None:
    """dấu nhỏ hơn trong văn xuôi không bị nhận nhầm là thẻ"""
    assert (
        html_to_readable_text("<p>Giá vàng < 100 triệu là mua được</p>") == "Giá vàng < 100 triệu là mua được"
    )


# ------------------------------------------------------------------ extractHtmlTitle


def test_extract_html_title_takes_title_and_strips_nested_tags() -> None:
    """lấy title, bóc thẻ lồng trong title"""
    assert extract_html_title("<title>Tin <b>nóng</b> hôm nay</title>") == "Tin nóng hôm nay"
    assert extract_html_title("<p>không có title</p>") == ""


# ------------------------------------------------------------------ boMoiTheKhongNoiDung - tuyến tính, không ReDoS


def test_bo_moi_the_khong_noi_dung_3mb_page_of_unclosed_open_tags_finishes_under_one_second() -> None:
    """trang 3 MB toàn thẻ mở KHÔNG đóng phải xong dưới 1 giây"""
    # Đây là đường tấn công THẬT: người lạ gửi link trỏ về server của họ, model
    # gọi web_fetch, `MAX_HTML_BYTES` cho tới 3 MB. Tiến trình một luồng phục vụ
    # mọi account + tick scheduler + HTTP dashboard.
    #
    # Bản regex `<(script|...)\b[\s\S]*?<\/\1\s*>` đo được: 256 KB = 474 ms,
    # 1 MB = 7,1 giây, 3 MB = 63,3 GIÂY. Sau khi đổi sang quét tuyến tính: 73 ms.
    don = "<script>" + "a" * 50
    html = don * ((3 * 1024 * 1024) // len(don))

    t0 = time.perf_counter()
    html_to_readable_text(html)
    ms = (time.perf_counter() - t0) * 1000
    assert ms < 1000, f"{ms:.0f}ms - thuật toán đang chạy bậc hai"


def test_bo_moi_the_khong_noi_dung_linear_doubling_input_does_not_quadruple_time() -> None:
    """tuyến tính: gấp đôi đầu vào thì KHÔNG gấp bốn thời gian"""
    don = "<style>" + "b" * 40

    def do1(n: int) -> float:
        html = don * (n // len(don))
        t0 = time.perf_counter()
        html_to_readable_text(html)
        return (time.perf_counter() - t0) * 1000

    # Lấy MIN của nhiều vòng chứ không đo một phát: nhiễu (GC, scheduler) chỉ
    # cộng thêm thời gian chứ không bao giờ trừ đi, nên min là số đo sạch nhất.
    def min_cua(n: int) -> float:
        return min(do1(n) for _ in range(5))

    do1(200_000)  # làm nóng, bỏ số đo đầu
    nho = min_cua(400_000)
    to = min_cua(800_000)
    # Tuyến tính ~2x, bậc hai ~4x, bản regex cũ đo được ~15x.
    assert to / nho < 3, f"gấp đôi đầu vào -> gấp {to / nho:.1f} lần thời gian"


# ------------------------------------------------------------------ boMoiTheKhongNoiDung - hành vi giữ nguyên như bản regex


def test_bo_moi_the_khong_noi_dung_removes_tag_and_all_inner_content() -> None:
    """bỏ thẻ và toàn bộ nội dung bên trong"""
    ra = html_to_readable_text("<p>Giữ lại</p><script>var x = 1;</script><p>Cũng giữ</p>")
    assert "Giữ lại" in ra
    assert "Cũng giữ" in ra
    assert "var x" not in ra, ra


def test_bo_moi_the_khong_noi_dung_header_not_mistaken_for_head() -> None:
    """<header> KHÔNG bị nhận nhầm thành <head> - đúng bẫy mà thứ tự trong regex cũ né"""
    # Regex cũ dựa vào thứ tự alternation "header|head"; bản mới kiểm ký tự
    # ngay sau tên thẻ. Cả hai phải cho cùng kết quả.
    ra = html_to_readable_text("<header>Menu trên</header><p>Nội dung thật</p>")
    assert "Nội dung thật" in ra
    assert "Menu trên" not in ra, ra


def test_bo_moi_the_khong_noi_dung_open_tag_without_close_keeps_text_not_whole_page() -> None:
    """thẻ mở KHÔNG có thẻ đóng thì giữ phần chữ, không nuốt cả trang"""
    # Thiên về giữ nhầm hơn xóa nhầm - cùng hướng an toàn với removeLinkDenseLists
    ra = html_to_readable_text("<p>Trước</p><script>chưa đóng<p>Sau vẫn phải còn</p>")
    assert "Trước" in ra
    assert "Sau vẫn phải còn" in ra


def test_bo_moi_the_khong_noi_dung_many_tags_of_same_kind_all_closed() -> None:
    """nhiều thẻ cùng loại, có thẻ đóng đầy đủ"""
    ra = html_to_readable_text("<p>A</p><nav>menu1</nav><p>B</p><nav>menu2</nav><p>C</p>")
    assert "A" in ra
    assert "B" in ra
    assert "C" in ra
    assert "menu1" not in ra
    assert "menu2" not in ra, ra


def test_bo_moi_the_khong_noi_dung_closing_tag_uppercase_and_with_space() -> None:
    """thẻ đóng viết hoa và có khoảng trắng"""
    ra = html_to_readable_text("<p>Giữ</p><SCRIPT>bỏ đi</SCRIPT >")
    assert "Giữ" in ra
    assert "bỏ đi" not in ra, ra


# ---- added: the index-alignment guard of the Python port ----


def test_bo_moi_the_khong_noi_dung_unicode_lowercase_length_change_does_not_shift_indexes() -> None:
    """chữ hoa có dấu chấm (İ) làm toLowerCase đổi độ dài không được làm lệch vị trí cắt thẻ"""
    ra = html_to_readable_text("<p>İİİ giữ lại</p><script>bỏ đi</script><p>Cuối</p>")
    assert "giữ lại" in ra
    assert "Cuối" in ra
    assert "bỏ đi" not in ra, ra
