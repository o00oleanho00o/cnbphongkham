# ported from: src/agent/tools/khu-dai-phan-cach-gia.ts
"""Gộp dải phân cách GIẢ (I13, một nửa) - nhiều dòng trống bao quanh một dòng gạch ngang - về KHÔNG CÒN dòng
trống nào, phá cấu trúc "2 dòng trống bao quanh" mà ``kb_search_tool`` dùng (``"\\n\\n---\\n\\n".join``) để
nối các đoạn thật. Tách riêng khỏi ``khu_gia_mao_nhan_nguon`` (khử NHÃN) - đây là mối lo KHÁC: dải phân cách
giả không cần đi kèm nhãn giả để nguy hiểm.

Viết bằng CODE (quét từng dòng, con trỏ chỉ tiến) thay vì nhồi vào MỘT regex - bản vòng 2 dùng
``(?:\\n[ \\t\\p{Cf}]*){2,}(-{3,})(?:\\n[ \\t\\p{Cf}]*){2,}``, HAI lượng từ LỒNG NHAU (lượng từ trong
``[...]*``, lượng từ ngoài ``{2,}`` quanh cả nhóm chứa nó) - vòng rà soát đo được O(n^2) THẬT trên payload
``("\\n ")*n``: 441ms cho 24.008 ký tự (gấp đôi độ dài -> gấp bốn thời gian), so với 0,01-0,04ms của regex
cũ tới tận 48.000 ký tự. Đúng lớp lỗi mà ``sanitize-reply-text.ts:24-33`` đã ghi thành luật sống còn sau một
lần trả giá thật ("MỖI biểu thức chỉ có MỘT lượng từ mở trên cùng một lớp ký tự; phần kiểm thêm làm bằng
code, không bằng backtrack"). Bản này quét MỖI DÒNG đúng một lần (hai con trỏ chỉ tiến, không lùi) nên tuyến
tính theo số dòng - xem test đo thời gian.

Forced deviation: ``\\p{Cf}`` and JavaScript's ``\\s`` are spelled out as bracket classes
(``unicode_char_classes``). A line is matched with ``fullmatch`` instead of ``^...$`` because Python's ``$``
also matches before a trailing newline.

Module THUẦN: không env, không DB.
"""

from __future__ import annotations

import re

from pema.agent.tools.unicode_char_classes import BRAILLE_BLANK, CF, JS_WHITESPACE

_KHOANG_TRANG = f"[{JS_WHITESPACE}{CF}{BRAILLE_BLANK}]"

# Một DÒNG (không xuống dòng, đã tách bằng ``.split("\n")``) toàn khoảng trắng/ký tự định dạng - ``\s`` của JS
# đã gồm tab/space/CR/LF/VT/FF (vertical tab, form feed - hai ký tự điều khiển ASCII vòng rà soát lần 4 đo
# được lọt khi lớp cũ chỉ liệt kê tay `` \t``) VÀ toàn bộ ``\p{Zs}`` (NBSP, em space, ideographic space...);
# cộng thêm ``\p{Cf}`` (ZWSP, ZWNJ... không nằm trong ``\s``) và dấu cách Braille U+2800 (không nằm trong
# ``\s`` lẫn ``\p{Zs}``, là ký hiệu, không phải khoảng trắng). ĐÚNG MỘT lượng từ trên MỘT lớp ký tự.
DONG_TRONG_RE = re.compile(f"{_KHOANG_TRANG}*")

# Một DÒNG chỉ có gạch ngang (>=3), cho phép khoảng trắng/ký tự định dạng hai đầu - HAI lượng từ TÁCH BIỆT
# trên các lớp ký tự RỜI NHAU (gạch ngang không nằm trong lớp khoảng trắng), không lồng nhau nên không mơ hồ.
DONG_GACH_RE = re.compile(f"{_KHOANG_TRANG}*-{{3,}}{_KHOANG_TRANG}*")


def khu_dai_phan_cach_gia(s: str) -> str:
    if "-" not in s:
        return s  # lối tắt rẻ - đa số nội dung không có gạch ngang chuỗi 3+
    dong = s.split("\n")
    ra: list[str] = []
    i = 0
    doi_chut = False
    while i < len(dong):
        j = i
        while j < len(dong) and DONG_TRONG_RE.fullmatch(dong[j]):
            j += 1
        co_trong_truoc = j > i

        if co_trong_truoc and j < len(dong) and DONG_GACH_RE.fullmatch(dong[j]):
            k = j + 1
            while k < len(dong) and DONG_TRONG_RE.fullmatch(dong[k]):
                k += 1
            if k > j + 1:
                # Đúng mẫu: >=1 dòng trống - dòng gạch ngang - >=1 dòng trống. GỘP VỀ KHÔNG DÒNG TRỐNG NÀO
                # CẢ (dòng gạch ngang dính liền chữ hai bên) - không phải "còn lại đúng 1 dòng trống". Bug
                # thật đã xảy ra ở đây: bản đầu push "", dong[j], "" (giữ lại 1 dòng trống mỗi bên) - với
                # payload CHỈ CÓ ĐÚNG 1 dòng trống mỗi bên (chính là hình dạng "\n\n---\n\n" mà ``.join()``
                # dùng), "gộp về 1" là PHÉP ĐỒNG NHẤT, không đổi gì - dải phân cách giả sống sót y nguyên.
                # Đúng ngữ nghĩa của regex CŨ (``\n{2,}(-{3,})\n{2,}`` thay bằng ``\n${dashes}\n``): khớp
                # tối thiểu 2 dấu xuống dòng mỗi bên (>=1 dòng trống) rồi thay bằng ĐÚNG 1 dấu xuống dòng
                # (0 dòng trống) - luôn CẮT MỘT NẤC, không giữ nguyên nấc.
                ra.append(dong[j])
                i = k
                doi_chut = True
                continue
        # Không khớp mẫu phân cách giả - giữ nguyên nhóm dòng trống (nếu có) rồi dòng hiện tại, không đụng gì.
        ra.extend(dong[i:j])
        if j < len(dong):
            ra.append(dong[j])
            i = j + 1
        else:
            i = j
    return "\n".join(ra) if doi_chut else s
