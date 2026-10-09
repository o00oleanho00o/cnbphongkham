# ported from: src/zalo/markdown-to-zalo-styles.ts
"""Dịch markdown của model thành TEXT TRẦN + danh sách `TextStyle` của Zalo.

Vì sao đổi từ XÓA sang DỊCH: docstring cũ của `sanitize_reply_text.py` nêu lý do xóa markdown là "Zalo
không render markdown". Điều đó đúng với KÝ TỰ markdown nhưng SAI với định dạng - `sendMessage` của zca-js
nhận `styles: Style[]` và Zalo render đậm/cỡ chữ/danh sách bình thường (`zca-js/src/apis/sendMessage.ts`,
enum `TextStyle`). Người dùng chỉ ra rằng tin Zalo thật có in đậm và tiêu đề, còn bot thì trả lời một khối
chữ phẳng.

MỨC ĐỘ: cố ý CHỈ dùng nhóm không màu - đậm, nghiêng, gạch ngang, tiêu đề to-đậm. Zalo có sẵn 4 màu nhưng
bot trả lời hội thoại mà tô màu thì đọc như tin quảng cáo; màu để dành cho ca thông báo, quyết định sau.
Danh sách CỐ Ý không dùng style của Zalo - xem docstring `la_dong_khoi`.

OFFSET ĐẾM THEO ĐƠN VỊ UTF-16 (`String.length` của JS), KHÔNG phải code point. zca-js gói thẳng
`start`/`len` vào `textProperties` JSON, không đổi gì, nên phải khớp cách Zalo Web đếm. Emoji là cặp
surrogate = 2 đơn vị: "sửa cho đúng" thành đếm ký tự thật sẽ lệch toàn bộ phần sau emoji đầu tiên, mà tin
nhắn thật đầy emoji.

Phỏng theo `zalo-personal/src/send.ts` (MIT) - bản đó đã chạy thật và trả giá cho đúng cái bẫy mô tả ở
`ap_dung_inline` bên dưới.

Pure module (no env, no logger, no DB). Forced deviations:

* The text runs as a UTF-16 *unit string* (see ``utf16_text``): ``to_units`` on entry, ``from_units`` on
  exit, so every ``TextStyle.start`` / ``length`` is a UTF-16 offset into the RETURNED text, as in JS.
* ``\\s``, ``\\S``, ``trim`` use the JS whitespace set; ``\\d`` is ``[0-9]``; JS ``.`` (no ``s`` flag) does
  not match CR, LS, PS, so the heading pattern excludes them explicitly.
* The table-separator pattern ``^\\s*\\|?[-:|\\s]*--[-:|\\s]*\\|?\\s*$`` has two overlapping quantifiers
  (quadratic on a long dash line). It accepts exactly "every char in ``[-:|\\s]`` and contains ``--``", so
  the port tests that directly (same language, linear). ``test_dong_ke_bang_tuong_duong_bieu_thuc_goc`` pins
  the equivalence against the literal regex.
* ``[ \\t]+$`` (strip trailing blanks) is ``rstrip(" \\t")`` for the same reason.
* Spans with ``length < 1`` are dropped at the boundary (``TextStyle`` validates ``length >= 1``); the
  original never emits one on purpose (``len(daInline) > 0`` guard).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .markdown_inline_styles import MOC, ap_dung_inline
from .multiline_markup_per_line import rai_dinh_dang_nhieu_dong
from .normalize_zalo_styles import ZaloTextStyle, chuan_hoa_styles, make_style
from .text_style import TextStyle
from .utf16_text import JS_NOT_S, JS_S, JS_WS_CHARS, from_units, js_trim, js_trim_end, to_units

# JS `.` without the `s` flag: anything but \n \r U+2028 U+2029 (a line never holds \n).
TIEU_DE_RE = re.compile(r"(#{1,6})[ \t]+([^\n\r  ]+)\Z")

DANH_SACH_RE = re.compile(f"{JS_S}*(?:[-*+]|[0-9]+\\.)[ \\t]+{JS_NOT_S}")

_RAO_CODE_RE = re.compile(f"{JS_S}*```")
_BANG_KE_CHARS = re.compile(f"[-:|{JS_WS_CHARS}]*\\Z")
_RAO_CUNG_DONG_RE = re.compile(r"```([^\n`]*)```")
_LINK_RE = re.compile(
    rf"\[([^\]\n]+)\]\((https?://[^{JS_WS_CHARS})]+|mailto:[^{JS_WS_CHARS})]+|tel:[^{JS_WS_CHARS})]+)\)"
)


def la_dong_danh_sach(dong: str | None) -> bool:
    """Dòng này là một mục danh sách (gạch đầu dòng hoặc đánh số)."""
    return dong is not None and DANH_SACH_RE.match(dong) is not None


def la_cau_dan(dong: str | None) -> bool:
    """Dòng này có DẪN VÀO danh sách ngay dưới không - dấu hiệu là kết thúc bằng dấu hai chấm ("Đối chiếu
    vé 645300:", "Kết quả Tiền Giang:").

    Cần phân biệt vì bản đầu bỏ dòng trống trước MỌI danh sách, kể cả khi đoạn trên chẳng liên quan. Đo trên
    tin thật: bản tin công nghệ có "Nguồn: CNBC" rồi URL, rồi mục "2. Nvidia thúc đẩy..." - dòng trống giữa
    URL và mục 2 bị xóa nên mục mới dính luôn vào cuối tin trước, trong khi các mục khác vẫn có khoảng cách.
    Nhìn ra là cách dòng lộn xộn.
    """
    if dong is None:
        return False
    s = js_trim_end(dong)
    return len(s) > 0 and s.endswith(":")


def la_dong_khoi(dong: str | None) -> bool:
    """VÌ SAO KHÔNG DÙNG `lst_1`/`lst_2` CỦA ZALO - đo trên máy thật 2026-08-05: hai client render KHÁC
    NHAU. Zalo Web vẽ một dấu đầu dòng cho mỗi dòng nằm trong span; Zalo trên điện thoại chỉ vẽ MỘT dấu cho
    cả span rồi thụt các dòng sau vào như xuống dòng mềm. Danh sách 9 mục hiện thành 1 mục trên điện thoại.

    Đã thử hướng "mỗi dòng một span" - đúng trên cả hai client, nhưng một danh sách 40 dòng là 40 span, mà
    JSON định dạng vốn đã ngốn gấp đôi chữ và Zalo chặn theo TỔNG byte. Trả giá bằng thêm tin cho người dùng
    phải đọc.

    Nên: GIỮ NGUYÊN ký tự "- " và "1. " làm chữ thường. Chữ thường hiện y hệt nhau ở mọi client, tốn 0 span,
    và người dùng thấy dễ đọc hơn dấu chấm tròn. Đây là lựa chọn của người dùng sau khi nhìn cả hai bản.
    """
    if dong is None:
        return False
    return TIEU_DE_RE.match(dong) is not None


@dataclass(frozen=True)
class KetQuaDinhDang:
    """Result of the conversion: plain text and its spans (UTF-16 offsets into ``text``)."""

    text: str
    styles: list[TextStyle]


def _la_dong_ke_bang(dong: str) -> bool:
    """`/^\\s*\\|?[-:|\\s]*--[-:|\\s]*\\|?\\s*$/.test(dong) && dong.includes("-")` (see module docstring)."""
    return _BANG_KE_CHARS.match(dong) is not None and "--" in dong


def _thay_link(match: re.Match[str]) -> str:
    chu, url = match.group(1), match.group(2)
    return url if js_trim(chu) == js_trim(url) else f"{chu} ({url})"


def markdown_sang_style_zalo(input_text: str) -> KetQuaDinhDang:
    """Dịch cả đoạn: xử lý TỪNG DÒNG, bóc dấu khối (tiêu đề / gạch đầu dòng / đánh số) rồi chạy inline trên
    phần nội dung còn lại, cộng dồn con trỏ toàn cục để mọi span nằm ở offset của CHUỖI CUỐI.
    """
    # Model có thể sinh ra chính ký tự mốc (JSON escape được \u0001). Dọn trước khi dùng nó làm mốc, không
    # thì chuỗi dạng MOC+số+MOC va đúng token và `ap_dung_inline` nhét nhầm nội dung. Cùng lá chắn với
    # `MOC_KHOI` ở `sanitize_reply_text.py`.
    src = to_units(input_text)
    if MOC in src:
        src = src.replace(MOC, "")

    # Rào code CÙNG DÒNG: chỉ gỡ rào, giữ nguyên nội dung
    src = _RAO_CUNG_DONG_RE.sub(lambda m: m.group(1), src)

    # Rải dấu VẮT NHIỀU DÒNG thành dấu từng dòng, TRƯỚC khi cắt dòng. Model bọc cả khối nhiều dòng trong một
    # cặp dấu (`<xanh>` quanh cả bài thơ) là chuyện thường, mà vòng lặp dưới đây xử theo dòng nên cặp đó
    # không bao giờ khớp - người dùng nhận nguyên chuỗi `<xanh>` giữa bài.
    src = rai_dinh_dang_nhieu_dong(src)

    dongs = src.split("\n")
    phan: list[str] = []
    styles: list[TextStyle] = []
    con_tro = 0
    trong_khoi_code = False

    for i, dong in enumerate(dongs):
        # Dòng rào ``` chỉ bật/tắt trạng thái rồi biến mất khỏi tin
        if _RAO_CODE_RE.match(dong):
            trong_khoi_code = not trong_khoi_code
            continue

        # Nội dung trong khối code đi thẳng, KHÔNG qua bước khối hay inline. Bỏ bước này thì `# Tính tổng`
        # trong đoạn Python bị hiểu là tiêu đề và mất dấu thăng - đúng lỗi mà `sanitize_code_block.py` đã
        # được viết ra để chữa.
        if trong_khoi_code:
            phan.append(dong)
            con_tro += len(dong)
            if i < len(dongs) - 1:
                phan.append("\n")
                con_tro += 1
            continue

        # Dòng kẻ ngăn của bảng markdown (|---|:---:|) chỉ là rác trên Zalo - bỏ hẳn dòng, giữ nguyên các
        # dòng dữ liệu. Giữ lại hành vi của lớp làm sạch cũ.
        if _la_dong_ke_bang(dong):
            continue

        # Dòng TRỐNG: giữ hay bỏ tùy hai bên nó là gì. Luật này dựng theo đúng chỗ người dùng chỉ trên ảnh
        # chụp màn hình thật, không phải suy đoán.
        #
        #   BỎ - ngay SAU dòng tiêu đề: tiêu đề và câu dẫn của nó thuộc về nhau.
        #   BỎ - giữa CÂU DẪN và danh sách ngay dưới nó: danh sách là phần khai triển của chính câu đó
        #        ("Đối chiếu vé 645300:" rồi tới các mục), tách ra là làm rời hai thứ đi liền nhau.
        #   GIỮ - ngay TRƯỚC dòng tiêu đề: đó là ranh giới giữa hai mục, thiếu nó thì "Kết luận: Không
        #        trúng." dính luôn vào tiêu đề mục sau.
        #   GIỮ - mọi chỗ còn lại (giữa hai đoạn văn, sau một khối danh sách).
        if js_trim(dong) == "":
            truoc = dongs[i - 1] if i > 0 else None
            sau = dongs[i + 1] if i + 1 < len(dongs) else None
            if la_dong_khoi(truoc):
                continue
            if la_cau_dan(truoc) and la_dong_danh_sach(sau) and not la_dong_danh_sach(truoc):
                continue

        # [chữ](url) -> "chữ (url)" để URL vẫn bấm được; trùng nhau thì chỉ giữ url. Làm TỪNG DÒNG chứ không
        # trên cả đoạn, để dòng trong khối code không bị đụng. Bỏ khoảng trắng CUỐI dòng: trong markdown hai
        # dấu cách cuối dòng nghĩa là "ngắt dòng", nhưng ở đây ký tự xuống dòng đã làm việc đó rồi - giữ lại
        # chỉ tổ cho span ôm thêm mấy ô trắng vô nghĩa. Dòng trong khối code đã đi đường riêng ở trên nên
        # không bị đụng.
        dong_link = _LINK_RE.sub(_thay_link, dong.rstrip(" \t"))

        # CÙNG biểu thức mà `la_dong_khoi` dùng - hai nơi lệch nhau thì việc bỏ dòng trống sẽ nhắm sai dòng,
        # mà lỗi đó không lộ ra ở đâu ngoài mắt người đọc.
        #
        # Chỉ còn TIÊU ĐỀ là khối: gạch đầu dòng và đánh số cố ý đi qua đây như chữ thường, giữ nguyên ký tự
        # "- " / "1. " - lý do ở docstring `la_dong_khoi`.
        m_tieu_de = TIEU_DE_RE.match(dong_link)
        noi_dung = js_trim_end(m_tieu_de.group(2)) if m_tieu_de else dong_link

        da_inline, spans = ap_dung_inline(noi_dung)
        phan.append(da_inline)

        if len(da_inline) > 0:
            # Big cho to hơn thấy rõ, Bold thêm độ đậm cho client cũ
            if m_tieu_de:
                styles.append(make_style(con_tro, len(da_inline), ZaloTextStyle.BIG))
                styles.append(make_style(con_tro, len(da_inline), ZaloTextStyle.BOLD))
            styles.extend(make_style(con_tro + s.start, s.length, s.style) for s in spans if s.length > 0)

        con_tro += len(da_inline)
        if i < len(dongs) - 1:
            phan.append("\n")
            con_tro += 1

    # Chuẩn hóa ở ĐÂY chứ không ở nơi gửi: mọi span đều sinh ra từ hàm này, nên đây là chỗ duy nhất bảo đảm
    # được bất biến "không span nào chồng span cùng kiểu". Bộ cắt tin bên `split_styled_message.py` chỉ CẮT
    # span có sẵn nên không thể tạo ra chồng lấn mới.
    return KetQuaDinhDang(text=from_units("".join(phan)), styles=chuan_hoa_styles(styles))
