# ported from: src/zalo/multiline-markup-per-line.ts
"""Rải dấu định dạng VẮT NHIỀU DÒNG thành dấu của từng dòng.

VÌ SAO CÓ FILE NÀY - đo trên tin thật ngày 2026-08-05. Model viết thư mời như người ta viết thật, tức là
bọc cả khối nhiều dòng trong MỘT cặp dấu:

    <cam>**THƯ MỜI THAM GIA
    KHÓA THIỀN TỪ TÂN THÁNG 8**</cam>

    <xanh>*Tháng Tám chớm thu gió dịu hiền,*
    *Lời hẹn khóa thiền giữ vẹn nguyên.*</xanh>

`markdown_to_zalo_styles.py` xử lý TỪNG DÒNG và mọi biểu thức inline đều kẹp bằng lớp phủ định có `\\n`, nên
cặp dấu vắt dòng KHÔNG BAO GIỜ khớp - người dùng nhận nguyên chuỗi `<xanh>` và `</xanh>` giữa bài.

Cách chữa: rải lại thành mỗi dòng một cặp dấu, TRƯỚC khi cắt dòng. Rải chứ không phải cho biểu thức vượt
dòng, vì span phủ qua ký tự xuống dòng là thứ đã trả giá ở `lst_1` (Zalo Web và điện thoại render khác
nhau). Mỗi dòng một span thì hai client chắc chắn giống nhau.

QUÉT BẰNG `find`, KHÔNG dùng biểu thức lười vượt dòng: `([\\s\\S]*?)` với nhiều thẻ mở mà thiếu thẻ đóng cho
ra bậc hai, mà bot đọc tin của người lạ.

Pure module: no imports beyond the JS-whitespace helpers. Forced deviations: ``trim`` / ``trimEnd`` use the
JS whitespace set; ``toLowerCase()`` of the remaining text (which in JS can change the length of a few
non-ASCII characters and so misalign the closing-tag index) is replaced by an ASCII case-insensitive search
of the closing tag, identical for every input where the original is correct.
"""

from __future__ import annotations

import re

from pema.channels.utf16_text import js_trim, js_trim_end

# Tên thẻ màu/gạch chân - PHẢI khớp danh sách ở `markdown_inline_styles.py`
TEN_THE = ("do", "cam", "vang", "xanh", "gach")
THE_MO_RE = re.compile(f"<({'|'.join(TEN_THE)})>", re.IGNORECASE | re.ASCII)
_THE_DONG_RE = {ten: re.compile(f"</{ten}>", re.IGNORECASE | re.ASCII) for ten in TEN_THE}


def _rai_tung_dong(noi_dung: str, mo: str, dong: str) -> str:
    """Bọc lại từng dòng, bỏ qua dòng trống (bọc dòng trống là đẻ ra span rỗng)."""
    return "\n".join(d if js_trim(d) == "" else f"{mo}{js_trim_end(d)}{dong}" for d in noi_dung.split("\n"))


def _rai_dam_nhieu_dong(src: str) -> str:
    """`**đậm vắt\\nhai dòng**` -> `**đậm vắt**\\n**hai dòng**`.

    Chỉ đụng cặp có ký tự xuống dòng ở giữa; cặp trong một dòng để nguyên cho `ap_dung_inline` lo. Bỏ qua
    khi nội dung dính thêm dấu sao ở hai đầu (`***`) - đó là ca hiếm mà rải sai thì hỏng chữ.
    """
    if "**" not in src:
        return src
    ra: list[str] = []
    i = 0
    while True:
        mo = src.find("**", i)
        if mo < 0:
            ra.append(src[i:])
            return "".join(ra)
        dong = src.find("**", mo + 2)
        if dong < 0:
            ra.append(src[i:])
            return "".join(ra)
        noi_dung = src[mo + 2 : dong]
        ra.append(src[i:mo])
        rai_duoc = "\n" in noi_dung and not noi_dung.startswith("*") and not noi_dung.endswith("*")
        ra.append(_rai_tung_dong(noi_dung, "**", "**") if rai_duoc else f"**{noi_dung}**")
        i = dong + 2


def _rai_the_nhieu_dong(src: str) -> str:
    """`<xanh>dòng một\\ndòng hai</xanh>` -> `<xanh>dòng một</xanh>\\n<xanh>dòng hai</xanh>`.

    Thẻ không có thẻ đóng thì GIỮ NGUYÊN chữ - cùng luật với cả lớp định dạng: để lọt vài ký tự thẻ còn
    hơn nuốt chữ của người ta.
    """
    if "<" not in src:
        return src
    ra: list[str] = []
    i = 0
    while True:
        khop = THE_MO_RE.search(src, i)
        if khop is None:
            ra.append(src[i:])
            return "".join(ra)
        ten = khop.group(1).lower()
        dau_nd = khop.end()
        # Tìm thẻ đóng KHÔNG phân biệt hoa thường để bắt được `</CAM>` viết hoa
        dong = _THE_DONG_RE[ten].search(src, dau_nd)
        if dong is None:
            # Thẻ mở không có thẻ đóng - giữ nguyên rồi đi tiếp từ SAU nó
            ra.append(src[i:dau_nd])
            i = dau_nd
            continue
        ket_thuc = dong.start()
        noi_dung = src[dau_nd:ket_thuc]
        ra.append(src[i : khop.start()])
        ra.append(
            _rai_tung_dong(noi_dung, f"<{ten}>", f"</{ten}>")
            if "\n" in noi_dung
            else f"<{ten}>{noi_dung}</{ten}>"
        )
        i = dong.end()


def rai_dinh_dang_nhieu_dong(src: str) -> str:
    """Rải mọi dấu vắt dòng. Thứ tự QUAN TRỌNG: `**` trước thẻ.

    Với `<cam>**A\\nB**</cam>` mà rải thẻ trước thì ra `<cam>**A</cam>` - dấu sao mất vế đóng trên dòng đó
    và lọt ra thành chữ. Rải `**` trước thì thành `<cam>**A**\\n**B**</cam>`, rồi rải thẻ mới ra hai dòng
    cân đối.
    """
    return _rai_the_nhieu_dong(_rai_dam_nhieu_dong(src))
