# ported from: src/shared/html-to-text.ts
"""Rút text đọc được từ HTML cho tool web_fetch - không thêm dependency (readability/cheerio) vì nhu cầu chỉ
là "agent đọc lướt nội dung trang".

Bài học từ vụ dò vé số: trang tin Việt Nam (minhngoc, xoso...) mở đầu bằng cả nghìn ký tự menu, đẩy
nội dung thật ra sau cap của tool -> model chỉ thấy menu và tưởng trang không có dữ liệu. GoClaw giải bằng
Defuddle (bóc nội dung chính kiểu Readability); mình dùng phiên bản tối giản của đúng tín hiệu đó: list nào
text nằm gần hết trong <a> là menu điều hướng, vứt.

Trang render bằng JS sẽ ra ít text - chấp nhận, đó là giới hạn đã biết.

Forced deviations from the TypeScript original (behaviour unchanged):

* JS ``\\s`` is spelled out as ``_WS`` (the ECMAScript whitespace set) instead of Python's ``\\s``, so the two
  engines agree on what "whitespace" is, and ``trim`` is ``_js_trim``.
* ``toLowerCase`` -> ``_ascii_lower``. Lowering the whole page with the Unicode rules can CHANGE ITS LENGTH
  ("İ" becomes two characters), after which every index found in the lowered copy would point to the wrong
  place in the original. Tag names are ASCII, so lowering only A-Z is equivalent for matching and keeps the
  two strings index-aligned.
* ``boTheKhongNoiDung`` appends to a list instead of ``+=`` on a string (same linear scan).
"""

from __future__ import annotations

import re

from pema.shared.html_entities import decode_html_entities

THE_KHONG_NOI_DUNG = [
    "script",
    "style",
    "noscript",
    "svg",
    "header",
    "head",
    "nav",
    "footer",
    "aside",
    "form",
    "select",
    "iframe",
    "template",
]
"""Block không bao giờ là nội dung."""

_WS = r"[\t\n\v\f\r    -     　﻿]"
_WS_CHARS = "\t\n\v\f\r                  　﻿"

_WS_RUN = re.compile(f"{_WS}+")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _js_trim(text: str) -> str:
    return text.strip(_WS_CHARS)


def _ascii_lower(text: str) -> str:
    return text.translate(_ASCII_LOWER)


def _ket_thuc_ten_the(html: str, sau: int) -> bool:
    """Ký tự ngay sau tên thẻ phải KHÔNG phải chữ/số - thay cho ``\\b`` của regex."""
    if sau >= len(html):
        return True
    c = html[sau]
    return not (("A" <= c <= "Z") or ("a" <= c <= "z") or ("0" <= c <= "9"))


def _bo_the_khong_noi_dung(html: str, ten: str) -> str:
    """Bỏ một loại thẻ và toàn bộ nội dung bên trong, QUÉT TUYẾN TÍNH.

    Bản trước dùng regex ``<(script|style|...)\\b[\\s\\S]*?<\\/\\1\\s*>``. Mỗi thẻ mở KHÔNG đóng khiến
    ``[\\s\\S]*?`` quét tới hết tài liệu rồi thất bại - O(K x n) với K là số thẻ mở. ``web-fetch-tool.ts`` cho
    phép trang 3 MB, và người lạ chỉ cần gửi một link trỏ về server của họ để model gọi ``web_fetch``.

    Đo thật trên trang toàn ``<script>`` không đóng (bản TS):

        256 KB     474 ms
        1 MB     7.107 ms
        3 MB    63.310 ms   (đúng trần MAX_HTML_BYTES)

    Tiến trình này MỘT luồng phục vụ mọi account, vòng tick scheduler và cả HTTP dashboard - hơn một phút đứng
    hình là cả bot chết.

    Kẹp trần lượng từ (cách vá quen thuộc) KHÔNG đủ ở đây: vẫn còn O(K x trần), mà K với trang 3 MB lên tới
    hàng chục nghìn. Nên đổi hẳn thuật toán.

    Mấu chốt để TUYẾN TÍNH: con trỏ chỉ tiến, và khi không tìm thấy thẻ đóng thì DỪNG HẲN loại thẻ đó -
    ``find`` vừa quét tới cuối chuỗi rồi, nên chắc chắn phía sau cũng không còn thẻ đóng nào. Tổng công: mỗi
    loại thẻ một lượt quét.

    Thẻ mở không có thẻ đóng thì GIỮ NGUYÊN, ``strip_html_tags`` dọn sau - thiên về giữ nhầm hơn xóa nhầm,
    cùng hướng an toàn với ``_remove_link_dense_lists``.
    """
    thap = _ascii_lower(html)
    mo = f"<{ten}"
    dong = f"</{ten}"

    ra: list[str] = []
    cat = 0  # đã ghi ra tới đâu
    tim = 0  # tìm thẻ mở từ đâu

    while True:
        i_mo = thap.find(mo, tim)
        if i_mo == -1:
            break
        if not _ket_thuc_ten_the(thap, i_mo + len(mo)):
            # "<header>" khi đang tìm "<head" - bỏ qua, tìm tiếp từ ngay sau
            tim = i_mo + len(mo)
            continue

        i_dong = thap.find(dong, i_mo + len(mo))
        # Không còn thẻ đóng nào phía sau -> dừng hẳn loại thẻ này. ĐÂY là chỗ
        # biến thuật toán từ bậc hai thành tuyến tính.
        if i_dong == -1:
            break

        i_het = thap.find(">", i_dong)
        if i_het == -1:
            break

        ra.append(html[cat:i_mo])
        cat = i_het + 1
        tim = cat

    if cat == 0:
        return html
    ra.append(html[cat:])
    return "".join(ra)


def _bo_moi_the_khong_noi_dung(html: str) -> str:
    ra = html
    for ten in THE_KHONG_NOI_DUNG:
        ra = _bo_the_khong_noi_dung(ra, ten)
    return ra


_TAG = re.compile(r"<[^>]+>")


def strip_html_tags(html: str) -> str:
    """Bóc thẻ HTML + giải mã entity (số lẫn tên - xem html_entities.py).

    Ở đây chứ không ở ``web_search_providers.py`` như trước: đây là module "HTML -> chữ", còn bên kia là
    module gọi mạng và có logger. Nhập ngược chiều khiến ``html_to_text`` (vốn thuần) kéo theo cả logger.
    """
    return _js_trim(_WS_RUN.sub(" ", decode_html_entities(_TAG.sub("", html))))


MENU_LINK_DENSITY = 0.7
"""Tỉ lệ text-trong-link tối thiểu để coi 1 list là menu điều hướng."""
MENU_MIN_LINKS = 3

_LIST_BLOCK = re.compile(
    rf"<(ul|ol|menu)\b[^>]*>(?:(?!<(?:ul|ol|menu)\b)[\s\S])*?</\1{_WS}*>",
    re.IGNORECASE,
)
_ANCHOR = re.compile(r"<a\b[^>]*>([\s\S]*?)</a>", re.IGNORECASE)


def _remove_link_dense_lists(html: str) -> str:
    """Xóa <ul>/<ol> là menu: >= 3 link và >= 70% chữ nằm trong <a> (list nội dung thật thì chữ chủ yếu nằm
    ngoài link).

    Regex chỉ match list TRONG CÙNG (content không chứa thẻ mở list khác) rồi chạy lặp: gỡ menu con xong thì
    menu cha thành trong cùng và được xét ở lượt sau. Match lazy thường sẽ ăn từ thẻ mở ngoài tới thẻ đóng
    trong - nuốt mất opener của cha, phần còn lại không bao giờ được xét (bug đã dính khi viết). List con được
    GIỮ (nội dung thật) thì cha không bao giờ thành trong cùng - thiên về giữ nhầm hơn xóa nhầm, đúng hướng an
    toàn.
    """
    current = html
    for _pass in range(5):
        removed_any = False

        def replace(match: re.Match[str]) -> str:
            nonlocal removed_any
            block = match.group(0)
            total_text = strip_html_tags(block)
            if not total_text:
                removed_any = True
                return " "
            anchors = list(_ANCHOR.finditer(block))
            anchor_text = " ".join(strip_html_tags(m.group(1)) for m in anchors)
            is_menu = (
                len(anchors) >= MENU_MIN_LINKS and len(anchor_text) / len(total_text) >= MENU_LINK_DENSITY
            )
            if is_menu:
                removed_any = True
            return " " if is_menu else block

        current = _LIST_BLOCK.sub(replace, current)
        if not removed_any:
            break
    return current


_MULTILINE_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")


def _collapse_multiline_tags(html: str) -> str:
    """Gộp thẻ viết tràn nhiều dòng về 1 dòng.

    Bước cuối của hàm dưới tách dòng TRƯỚC rồi mới bóc thẻ từng dòng, nên thẻ bị xuống dòng giữa chừng không
    còn khớp ``<...>`` trên dòng nào cả và lọt nguyên vào text gửi model. Lỗi thật ở tuoitre.vn:

        <input onfocus="this.removeAttribute('readonly');" class="input-search"
        placeholder="Nhập nội dung cần tìm" />

    Chỉ đụng phần bên trong ``<...>``, nội dung văn bản giữ nguyên. Ràng buộc ký tự đầu là chữ / ``/`` / ``!``
    để dấu nhỏ hơn trong văn xuôi ("a < b") không bị nhận nhầm là thẻ mở.
    """
    return _MULTILINE_TAG.sub(lambda m: _WS_RUN.sub(" ", m.group(0)), html)


_SPAN_GAP = re.compile(rf"</span>{_WS}*<span", re.IGNORECASE)
_BLOCK_BREAK = re.compile(
    r"<(br|/p|/div|/h[1-6]|/li|/tr|tr\b|/section|/article)[^>]*>",
    re.IGNORECASE,
)
_LI_OPEN = re.compile(r"<li[^>]*>", re.IGNORECASE)
_CELL_OPEN = re.compile(r"<t[dh]\b[^>]*>", re.IGNORECASE)


def html_to_readable_text(html: str) -> str:
    without_blocks = _remove_link_dense_lists(_bo_moi_the_khong_noi_dung(_collapse_multiline_tags(html)))

    # Giữ cấu trúc đoạn: thẻ block phổ biến thành xuống dòng trước khi bóc thẻ
    # Span liền kề phải có khoảng trắng ở ranh giới: xoso.com.vn bọc MỖI CON SỐ
    # kết quả trong 1 span, bóc thẻ trần sẽ ra "836791064644..." dính chùm -
    # model không cách nào tách lại được. Chỉ xử ranh giới </span><span> nên
    # span đơn lẻ giữa từ (kiểu tô màu 1 chữ) không bị chẻ đôi.
    with_breaks = _SPAN_GAP.sub("</span> <span", without_blocks)
    # Hàng/ô bảng bám theo thẻ MỞ chứ không phải thẻ đóng: HTML5 cho phép bỏ
    # </td></tr> và xoso.com.vn viết đúng kiểu đó - bám thẻ đóng là cả bảng
    # kết quả dính thành 1 dòng "836791064644...". Thẻ đóng </tr> vẫn giữ cho
    # site viết đủ; dòng rỗng sinh thêm bị filter(Boolean) nuốt.
    with_breaks = _BLOCK_BREAK.sub("\n", with_breaks)
    with_breaks = _LI_OPEN.sub("\n- ", with_breaks)
    # Ranh giới ô trong bảng: bảng kết quả (xổ số, giá) mà dính chữ liền nhau
    # là model đọc sai cột
    with_breaks = _CELL_OPEN.sub(" | ", with_breaks)

    # strip_html_tags nuốt cả \n (collapse \s+) nên tách dòng trước, bóc thẻ từng dòng
    lines = (strip_html_tags(line) for line in with_breaks.split("\n"))
    return "\n".join(line for line in lines if line)


_TITLE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)


def extract_html_title(html: str) -> str:
    """Tiêu đề trang từ thẻ <title> - rỗng nếu không có."""
    match = _TITLE.search(html)
    return strip_html_tags(match.group(1)) if match else ""
