# ported from: src/zalo/markdown-inline-styles.ts
"""Dịch các cặp dấu INLINE (`**đậm**`, `~~gạch~~`, `` `code` ``) của MỘT dòng.

Tách khỏi `markdown_to_zalo_styles.py` không phải để cho gọn: file kia lo việc theo DÒNG (tiền tố khối,
hàng rào code, cộng dồn con trỏ toàn cục), còn đây là một mối quan tâm khép kín - nhận một dòng, trả về
dòng đã bóc dấu kèm span tương đối. Ranh giới đó cũng là ranh giới của cái bẫy mô tả bên dưới.

Pure module. Forced deviations:

* The input line is a UTF-16 *unit string* (see ``utf16_text``): ``len(text)`` and every ``SpanInline``
  offset are UTF-16 units, exactly like the JS ``String.length`` of the original. The caller converts at the
  boundary.
* JS ``\\w`` is ASCII-only and the ``i`` flag of a non-unicode JS regex folds ASCII letters only, so the
  patterns use explicit ASCII classes / ``re.ASCII`` instead of the (wider) Python defaults.
* ``SpanInline`` is a plain dataclass (not ``TextStyle``): spans here are transient and the contract type
  validates ``length >= 1`` and ``start >= 0``; the caller converts at the boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize_zalo_styles import ZaloTextStyle

# Ký tự mốc để token hóa - xem `ap_dung_inline`
MOC = "\u0001"

_IGNORE_CASE = re.IGNORECASE | re.ASCII

# Các cặp dấu inline được dịch.
#
# CỐ Ý BỎ `__đậm__` và `_nghiêng_`: dấu gạch dưới sống đầy trong tên file và URL thật (`bao_gia_2026.pdf`),
# bắt chúng là đổi hỏng dữ liệu thật. Đây là quyết định đã có từ `sanitize_reply_text.py`, giữ nguyên.
#
# MỌI biểu thức ở đây phải TUYẾN TÍNH - bot đọc tin của người lạ, một tin soạn khéo khiến model nhại lại
# chuỗi độc là đủ để biểu thức bậc hai treo cả tiến trình. Lượng từ đều đi kèm lớp ký tự PHỦ ĐỊNH
# (`[^*\n]`) nên không backtrack chồng nhau được. Cùng luật với `sanitize_reply_text.py`.
#
# Thứ tự QUAN TRỌNG: dấu dài đứng trước dấu ngắn, không thì `**` bị `*` ăn mất.
CAP_DAU: list[tuple[re.Pattern[str], ZaloTextStyle]] = [
    (re.compile(r"\*\*\*([^*\n]+)\*\*\*"), ZaloTextStyle.BOLD),  # Zalo không chồng được đậm+nghiêng
    (re.compile(r"\*\*([^*\n]+)\*\*"), ZaloTextStyle.BOLD),
    (re.compile(r"~~([^~\n]+)~~"), ZaloTextStyle.STRIKE_THROUGH),
    (re.compile(r"`([^`\n]+)`"), ZaloTextStyle.BOLD),  # Zalo không có font mono
    (re.compile(r"(?<![*A-Za-z0-9_])\*(?!\*)([^*\n]+?)\*(?!\*)(?![A-Za-z0-9_])"), ZaloTextStyle.ITALIC),
    # Màu và gạch chân: markdown KHÔNG có cú pháp cho hai thứ này nên phải tự đặt quy ước. Dùng thẻ kiểu HTML
    # vì model quen viết, và vì lớp ký tự phủ định `[^<\n]` giữ biểu thức tuyến tính - không thẻ nào lồng
    # trong thẻ nào được, đó cũng chính là điều mình muốn (tô hai màu chồng nhau là vô nghĩa).
    #
    # Đây thuần là DỮ LIỆU, không phải code do model sinh ra, nên không mở thêm đường prompt injection -
    # cùng nguyên tắc với tool tạo file.
    #
    # Cả 4 màu + gạch chân đã ĐO THẬT trên cả Zalo Web lẫn điện thoại: hiện y hệt nhau, kể cả khi chồng với
    # đậm hoặc nghiêng.
    (re.compile(r"<do>([^<\n]+)</do>", _IGNORE_CASE), ZaloTextStyle.RED),
    (re.compile(r"<cam>([^<\n]+)</cam>", _IGNORE_CASE), ZaloTextStyle.ORANGE),
    (re.compile(r"<vang>([^<\n]+)</vang>", _IGNORE_CASE), ZaloTextStyle.YELLOW),
    (re.compile(r"<xanh>([^<\n]+)</xanh>", _IGNORE_CASE), ZaloTextStyle.GREEN),
    (re.compile(r"<gach>([^<\n]+)</gach>", _IGNORE_CASE), ZaloTextStyle.UNDERLINE),
]


@dataclass(frozen=True)
class SpanInline:
    """A span relative to the line (UTF-16 units). ``style`` is any style except ``Indent``."""

    start: int
    length: int
    style: ZaloTextStyle


@dataclass
class _MucDaCat:
    noi_dung: str
    style: ZaloTextStyle


def ap_dung_inline(dong: str) -> tuple[str, list[SpanInline]]:
    """Dịch phần inline của MỘT dòng (a unit string). Returns ``(text, spans)``.

    Cách ngây thơ - chạy từng regex rồi phát span theo độ dài kết quả - VỠ khi pass sau xóa ký tự nằm
    TRƯỚC span mà pass trước đã ghi: span cũ trôi đi mà không ai chỉnh lại. Bản tham chiếu đã dính thật, ca
    đo được là `__Chữ gạch chân__` hóa ra chỉ gạch chân `ữ gạch chân.`.

    Nên: mỗi pass thay đoạn khớp bằng token `MOC + số + MOC` và cất nội dung ra ngoài. Token có độ dài
    KHÔNG phụ thuộc số ký tự các pass khác xóa, và các regex sau không khớp vào token được. Xong hết mới đi
    một vòng cuối dựng lại chuỗi và phát span theo offset CUỐI CÙNG.
    """
    cat: list[_MucDaCat] = []
    tam = _token_hoa(dong, cat)

    # Nội dung cất ra ở pass TRƯỚC không được các pass SAU quét tới, nên phải token hóa lại chính nó. Ví dụ
    # `**<cam>X</cam>**`: pass đậm cất nguyên `<cam>X</cam>` vào kho rồi pass màu chỉ còn thấy token ở
    # ngoài, thẻ màu nằm trong kho thành chữ trần. Vòng này quét cả những mục MỚI sinh ra (`cat` dài thêm
    # trong lúc lặp) và dừng chắc chắn vì nội dung mỗi lần một ngắn đi.
    k = 0
    while k < len(cat):
        cat[k].noi_dung = _token_hoa(cat[k].noi_dung, cat)
        k += 1

    spans: list[SpanInline] = []
    text = _mo_rong(tam, cat, 0, spans)
    return text, spans


def _token_hoa(chuoi: str, cat: list[_MucDaCat]) -> str:
    """Thay mọi đoạn khớp bằng token, cất nội dung vào `cat`. Trả chuỗi đã token hóa."""
    tam = chuoi
    for regex, style in CAP_DAU:

        def thay(match: re.Match[str], style: ZaloTextStyle = style) -> str:
            n = len(cat)
            cat.append(_MucDaCat(noi_dung=match.group(1), style=style))
            return f"{MOC}{n}{MOC}"

        tam = regex.sub(thay, tam)
    return tam


def _mo_rong(chuoi: str, cat: list[_MucDaCat], goc: int, spans: list[SpanInline]) -> str:
    """Dựng lại chuỗi từ token và phát span theo offset CUỐI CÙNG.

    ĐỆ QUY vì thẻ lồng nhau là ca thường gặp nhất của màu: `<cam>**Thời gian:**</cam>` phải ra HAI span
    cùng phủ "Thời gian:" - một cam, một đậm. Bản một tầng chỉ phát được span ngoài, còn dấu `**` bên trong
    lọt ra thành chữ.
    """
    ra: list[str] = []
    do_dai = 0  # len("".join(ra)) kept incrementally
    i = 0
    while i < len(chuoi):
        if chuoi[i] != MOC:
            ra.append(chuoi[i])
            do_dai += 1
            i += 1
            continue
        het = chuoi.find(MOC, i + 1)
        muc = _tim_muc(cat, chuoi[i + 1 : het]) if het != -1 else None
        if muc is None:
            # Token hỏng (không nên xảy ra) - giữ nguyên ký tự, KHÔNG nuốt chữ
            ra.append(chuoi[i])
            do_dai += 1
            i += 1
            continue
        bat_dau = goc + do_dai
        trong = _mo_rong(muc.noi_dung, cat, bat_dau, spans)
        spans.append(SpanInline(start=bat_dau, length=len(trong), style=muc.style))
        ra.append(trong)
        do_dai += len(trong)
        i = het + 1
    return "".join(ra)


def _tim_muc(cat: list[_MucDaCat], so: str) -> _MucDaCat | None:
    """`cat[Number(so)]`: only the digits tokens we emit ourselves are accepted."""
    if not so.isascii() or not so.isdigit() or len(so) > 9:
        return None
    n = int(so)
    return cat[n] if n < len(cat) else None
