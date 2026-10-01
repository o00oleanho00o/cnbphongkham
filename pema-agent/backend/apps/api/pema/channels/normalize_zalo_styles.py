# ported from: src/zalo/normalize-zalo-styles.ts
"""Chuẩn hóa danh sách `TextStyle` trước khi giao cho kênh (normalise rich-text spans before sending).

VÌ SAO CÓ FILE NÀY - lỗi đã trả giá thật (2026-08-05, lượt 116): câu trả lời có dòng tiêu đề chứa in đậm,
ví dụ `## 1. Vé Tiền Giang - số **418512**`, sinh ra HAI span `b` chồng nhau: một từ luật tiêu đề (phủ cả
dòng) và một từ luật inline (phủ riêng dãy số). Zalo từ chối CẢ TIN với mã 112 ("tham số không hợp lệ").
Người dùng mất trọn câu trả lời sau 8 lượt tra web và 119k token, chỉ nhận lại câu "trục trặc kỹ thuật".

Đối chiếu 20 bước của 12 lượt gần đó: 9 tin gửi được đều có 0 span chồng trùng loại; lượt hỏng có 3. Bản
tham chiếu `zalo-personal` cũng phát Big+Bold cho tiêu đề nên `f_18` vô can - nó chỉ chưa gặp ca tiêu đề có
in đậm bên trong.

Pure module. Forced deviations (see PLAN-AI01 and the decisions of package C2):

* zca-js ``Style {start, len, st}`` becomes ``pema_contracts.channel.TextStyle(start, length, style)``.
  ``start`` / ``length`` are UTF-16 code units of the text the span belongs to.
* The zca-js ``TextStyle`` enum becomes ``ZaloTextStyle`` (a ``StrEnum``) with the SAME wire strings
  zca-js 2.1.2 sends (``b``, ``i``, ``u``, ``s``, ``c_db342e``, ``c_f27806``, ``c_f7b503``, ``c_15a85f``,
  ``f_13``, ``f_18``, ``lst_1``, ``lst_2``, ``ind_$``). The original tests only use the enum symbolically,
  so these strings come from the public zca-js source, not from a test.
* ``Style.indentSize`` (an extra key of the ``Indent`` style) cannot live in ``TextStyle`` (the contract
  forbids extra fields), so this module defines ``ZaloStyle(TextStyle)`` with an optional ``indent_size``.
  It is still a ``TextStyle`` for every consumer; ``style_to_wire`` emits it as ``indentSize``.
* ``style_to_wire`` is the one place that knows the wire shape ``{"start", "len", "st"[, "indentSize"]}``;
  byte budgets (``so_byte_tin``) are measured on it so they equal the original's ``JSON.stringify``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pema_contracts.channel import TextStyle


class ZaloTextStyle(StrEnum):
    """zca-js ``TextStyle`` members used by the pipeline, with their wire strings."""

    BOLD = "b"
    ITALIC = "i"
    UNDERLINE = "u"
    STRIKE_THROUGH = "s"
    RED = "c_db342e"
    ORANGE = "c_f27806"
    YELLOW = "c_f7b503"
    GREEN = "c_15a85f"
    SMALL = "f_13"
    BIG = "f_18"
    UNORDERED_LIST = "lst_1"
    ORDERED_LIST = "lst_2"
    INDENT = "ind_$"


class ZaloStyle(TextStyle):
    """``TextStyle`` plus the optional ``indentSize`` of the ``Indent`` style (see module docstring)."""

    indent_size: int | None = Field(default=None, ge=1)


def make_style(
    start: int, length: int, style: ZaloTextStyle | str, indent_size: int | None = None
) -> TextStyle:
    """Build a span. ``style`` is stored as a plain ``str`` (the wire code)."""
    code = style.value if isinstance(style, ZaloTextStyle) else style
    if indent_size is None:
        return TextStyle(start=start, length=length, style=code)
    return ZaloStyle(start=start, length=length, style=code, indent_size=indent_size)


def style_to_wire(style: TextStyle) -> dict[str, int | str]:
    """The zca-js ``Style`` object exactly as it is JSON-serialised: ``start``, ``len``, ``st`` in this
    order, then the extra keys of the original (``indentSize``) in their original position.
    """
    wire: dict[str, int | str] = {"start": style.start, "len": style.length, "st": style.style}
    if isinstance(style, ZaloStyle) and style.indent_size is not None:
        wire["indentSize"] = style.indent_size
    return wire


def khoa_gop(s: TextStyle) -> str:
    """Khóa gộp: hai span chỉ gộp được khi CÙNG kiểu tô.

    `Indent` phải tính cả `indentSize` - hai cấp thụt khác nhau là hai định dạng khác nhau, gộp lại là làm
    phẳng danh sách lồng.
    """
    if s.style == ZaloTextStyle.INDENT:
        size = s.indent_size if isinstance(s, ZaloStyle) and s.indent_size is not None else 1
        return f"{s.style}:{size}"
    return s.style


def chuan_hoa_styles(styles: list[TextStyle]) -> list[TextStyle]:
    """Gộp span trùng loại bị chồng (hoặc chạm nhau) và sắp lại theo vị trí.

    Gộp cả ca CHẠM NHAU (`b.start === a.start + a.len`) chứ không chỉ ca chồng: hai span liền kề cùng kiểu
    tô ra kết quả nhìn y hệt một span dài, nên gộp làm ít span hơn mà không đổi thứ người dùng thấy.

    Sắp xếp: theo `start` tăng dần, cùng `start` thì span DÀI đứng trước. Trước bản này span `Indent` bị
    phát SAU các span inline nên mảng không còn theo thứ tự vị trí (`0:lst_1 7:b 13:lst_1 25:b 13:ind_$`).
    Chưa đo được Zalo có bắt lỗi thứ tự hay không, nhưng gửi đi một mảng lộn xộn thì lúc có sự cố không ai
    loại trừ được nó.
    """
    if len(styles) <= 1:
        return styles

    theo_khoa: dict[str, list[TextStyle]] = {}
    for s in styles:
        theo_khoa.setdefault(khoa_gop(s), []).append(s)

    ra: list[TextStyle] = []
    for nhom in theo_khoa.values():
        nhom.sort(key=lambda s: s.start)
        dang_gom = nhom[0]
        for s in nhom[1:]:
            # CỐ Ý chỉ gộp span CHẠM hoặc CHỒNG nhau, không gộp qua ký tự xuống dòng. Đã thử gộp span danh
            # sách qua dòng để tiết kiệm byte: Zalo Web hiện đúng nhưng Zalo trên điện thoại chỉ vẽ MỘT dấu
            # đầu dòng cho cả span. Giờ danh sách đi bằng chữ "- " thường nên không còn span nào để gộp.
            if s.start <= dang_gom.start + dang_gom.length:
                # Chồng hoặc chạm: nới đuôi ra tới điểm xa nhất của hai span
                cuoi = max(dang_gom.start + dang_gom.length, s.start + s.length)
                dang_gom = dang_gom.model_copy(update={"length": cuoi - dang_gom.start})
            else:
                ra.append(dang_gom)
                dang_gom = s
        ra.append(dang_gom)

    ra.sort(key=lambda s: (s.start, -s.length))
    return ra
