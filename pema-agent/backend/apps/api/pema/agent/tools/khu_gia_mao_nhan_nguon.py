# ported from: src/agent/tools/khu-gia-mao-nhan-nguon.ts
"""Chống giả mạo nhãn nguồn (I13) cho ``kb_search_tool``: một tài liệu (hoặc chính TÊN NGUỒN/TIÊU ĐỀ của
nó) có thể tự viết đúng định dạng ``[Nguồn: ...]`` cùng dải phân cách ``\\n\\n---\\n\\n`` (khử ở
``khu_dai_phan_cach_gia``) để tự gán nội dung độc hại cho một nguồn khác.

ĐÃ QUA BA VÒNG RÀ SOÁT. Vòng 2: ``tieu_de`` không qua khử + regex hẹp (ZWSP, fullwidth). Vòng 3: regex vòng
2 tự HẸP HƠN bản gốc (thiếu đệm ``\\s`` ngay sau ngoặc mở), ``tieu_de``/``ten_nguon`` không qua
``loc_ky_tu_an``, ba dạng ngoặc CJK/toán mới, NFC chống dạng NFD. Vòng 4 tìm tiếp:

* ``${DEM_GIUA}[\\s\\p{Cf}]*:`` (vòng 3) là HAI lượng từ KỀ NHAU trên hai lớp GIAO NHAU ở ``\\p{Cf}`` (ZWSP
  vừa khớp được ``DEM_GIUA`` vừa khớp được lớp sau) - đúng thứ ``sanitize-reply-text.ts:24-33`` cấm. Đo được:
  payload ``"[Nguồn" + ZWSP.repeat(16000) + "x"`` mất 2.479ms (nặng gấp 5,6 lần chính cái vòng 3 vừa vá).
  Sửa: gộp thành MỘT lượng từ ``[\\s\\p{Cf}\\p{Mn}]*`` ngay sau chữ cái cuối "Nguồn" - không còn hai lớp kề
  nhau nữa.
* Chuỗi tấn công THẬT sống sót qua cả hai lớp khử (không cần ký tự vô hình): ``\\v``/``\\f`` (điều khiển
  ASCII, đã sửa - xem ``khu_dai_phan_cach_gia``), dấu hai chấm FULLWIDTH ``：`` thay ``:``, và 10 dạng ngoặc
  mở CJK/toán khác ngoài 3 dạng vòng 3 đã vá. Sửa bằng MỞ RỘNG lớp ký tự (không NFKC hoá cả chuỗi - đã đo
  NFKC phá ``½ ﬁ m²``, và ánh xạ vị trí giữa bản NFKC/bản gốc phức tạp vì NFKC đổi độ dài chuỗi cho nhiều ký
  tự, vd ``½`` -> ``1⁄2``): thêm 10 cặp ngoặc, một lớp dấu hai chấm chịu biến thể, và một lớp chữ cái chịu
  dạng FULLWIDTH cho phần ASCII của "Nguồn" (qua công thức chính thức +0xFEE0 của khối Fullwidth Forms,
  không liệt kê tay).

PHẠM VI CỐ Ý, KHÔNG MỞ RỘNG THÊM: không vét cạn MỌI ký tự "trông giống" trong Unicode (danh sách
ngoặc/dấu hai chấm dưới đây là tập ĐÃ ĐO, không phải tập ĐẦY ĐỦ - còn có thể có biến thể khác chưa ai tìm
ra). Homoglyph (Cyrillic ``о`` thay ``o``...) và việc bỏ dấu tiếng Việt nằm NGOÀI phạm vi có chủ đích: hàng
rào THẬT chống injection là NONCE ở ``wrap_untrusted_content`` (chặn được toàn bộ payload
vô hình/fullwidth/homoglyph cho RANH GIỚI tin cậy, vì attacker không đoán được nonce dù viết đúng chữ gì).
Bộ khử nhãn ở đây chỉ chống một mối đe doạ HẸP HƠN: DẪN SAI NGUỒN (I13) - vét cạn thêm ký tự chỉ thu hẹp
một khe nhỏ của một mối đe doạ đã có lớp phòng chính.

Forced deviation: ``\\p{Cf}``/``\\p{Mn}`` and JavaScript's ``\\s`` are spelled out as bracket classes
(``unicode_char_classes``); the ``giu`` flags become ``re.IGNORECASE`` (``u`` is the default of a ``str``
pattern).

Module THUẦN: không env, không DB.
"""

from __future__ import annotations

import re
import unicodedata

from pema.agent.tools.khu_dai_phan_cach_gia import khu_dai_phan_cach_gia
from pema.agent.tools.unicode_char_classes import CF, JS_WHITESPACE, MN


def bien_the_fullwidth(ch: str) -> str:
    """Trả về CHUỖI ký tự thay thế được cho ``ch`` - CHÍNH NÓ, cộng dạng FULLWIDTH nếu có (fullwidth ASCII
    U+FF01-FF5E = ASCII in được U+0021-007E + 0xFEE0 - công thức CHÍNH THỨC của khối Fullwidth Forms, không
    phải liệt kê tay). KHÔNG bọc ngoặc vuông, để ghép tự do vào một lớp ký tự lớn hơn."""
    cp = ord(ch[0])
    if cp < 0x21 or cp > 0x7E:
        return ch  # ngoài ASCII in được - không có dạng fullwidth
    return f"{ch}{chr(cp + 0xFEE0)}"


def chu_va_fullwidth(ch: str) -> str:
    """Bọc kết quả ``bien_the_fullwidth`` thành một LỚP KÝ TỰ regex - dùng cho chữ cái ASCII của "Nguồn" ("ồ"
    không phải ASCII nên không có dạng fullwidth, ``bien_the_fullwidth`` trả nguyên nó, hàm này vẫn bọc
    ``[...]`` bình thường)."""
    return f"[{re.escape(bien_the_fullwidth(ch))}]"


DEM_GIUA = f"[{CF}{MN}]*"
"""Đệm GIỮA từng chữ cái "Nguồn" - ký tự định dạng vô hình + dấu phụ, KHÔNG gồm ``\\s``: chữ cái không tự
nhiên cách nhau bằng dấu cách hợp lệ."""

DEM_DAU = f"[{JS_WHITESPACE}{CF}{MN}]*"
"""Đệm NGAY SAU ngoặc mở - PHẢI gồm ``\\s``: chỗ vòng rà soát lần 3 bắt được quên (bản trước chỉ đệm
``\\p{Cf}``/``\\p{Mn}`` ở đây, một dấu cách ASCII thường không thuộc hai lớp đó nên lọt nguyên văn)."""

DAU_HAI_CHAM_RE_CLASS = f"[{re.escape(bien_the_fullwidth(':'))}{re.escape('∶꞉︓﹕')}]"
"""Dấu hai chấm ASCII + 5 biến thể "trông giống" đo được/đã biết - fullwidth (qua công thức
``chu_va_fullwidth``) cộng bốn ký tự Unicode khác thường dùng để né bộ lọc ASCII thuần (ratio, modifier
letter, hai dạng trình bày dọc/nhỏ CJK). KHÔNG vét cạn - xem "PHẠM VI CỐ Ý" ở docstring đầu file."""

CAP_NGOAC: tuple[tuple[str, str], ...] = (
    ("[", "]"),
    ("［", "］"),  # U+FF3B/FF3D fullwidth
    ("【", "】"),  # U+3010/3011 CJK black lenticular bracket
    ("⁅", "⁆"),  # U+2045/2046 square bracket with quill
    ("﹇", "﹈"),  # U+FE47/FE48 presentation form for vertical left/right square bracket
    ("〔", "〕"),  # U+3014/3015 CJK tortoise shell bracket
    ("〖", "〗"),  # U+3016/3017 CJK white lenticular bracket
    ("⟦", "⟧"),  # U+27E6/27E7 mathematical white square bracket
    ("｢", "｣"),  # U+FF62/FF63 halfwidth corner bracket
    ("❲", "❳"),  # U+2772/2773 light tortoise shell bracket ornament
    ("⦋", "⦌"),  # U+298B/298C left/right square bracket with underbar
    ("⦇", "⦈"),  # U+2987/2988 Z notation image bracket
    ("〚", "〛"),  # U+301A/301B left/right white square bracket
    ("⸨", "⸩"),  # U+2E28/2E29 left/right double parenthesis
    ("﹝", "﹞"),  # U+FE5D/FE5E small tortoise shell bracket
)
"""Cặp ngoặc mở/đóng có thể giả làm hoặc tự đóng sớm nhãn ``[Nguồn: ...]`` - ASCII, fullwidth, và 13 biến thể
CJK/toán đo được qua 2 vòng rà soát. Thêm dạng ngoặc mới thì chỉ sửa MẢNG này - cả regex nhãn lẫn bộ khử
ngoặc dùng chung, không lặp danh sách ở hai nơi rồi trôi khỏi nhau."""

NGOAC_MO_SET = frozenset(mo for mo, _ in CAP_NGOAC)


def lop_ky_tu(chars: list[str]) -> str:
    """Dựng lớp ký tự regex an toàn từ danh sách. (The original escaped only ASCII ``]``; ``re.escape`` also
    covers ``[``, ``\\``, ``^`` and ``-``, which Python would otherwise treat as syntax or warn about.)"""
    return f"[{''.join(re.escape(c) for c in chars)}]"


# MỘT lượng từ duy nhất ``[\s\p{Cf}\p{Mn}]*`` ngay sau chữ cái cuối "Nguồn", rồi TRỰC TIẾP tới lớp dấu hai
# chấm (không phải lượng từ) - KHÔNG còn nối thêm ``${DEM_GIUA}`` (một lượng từ khác) trước lớp đó như bản
# vòng 3, vì hai lượng từ liên tiếp trên hai lớp giao nhau (``\p{Cf}`` có ở cả hai) là đúng dạng bậc hai đã
# đo được (2.479ms ở n=16.000).
NHAN_NGUON_GIA_RE = re.compile(
    lop_ky_tu([mo for mo, _ in CAP_NGOAC])
    + DEM_DAU
    + DEM_GIUA.join(chu_va_fullwidth(c) for c in "Nguồn")
    + f"[{JS_WHITESPACE}{CF}{MN}]*"
    + DAU_HAI_CHAM_RE_CLASS,
    re.IGNORECASE,
)

NGOAC_CA_HAI_RE = re.compile(lop_ky_tu([c for cap in CAP_NGOAC for c in cap]))


def khu_ngoac_vuong_trong_nhan(s: str) -> str:
    """Mọi dạng ngoặc vuông trong TÊN NGUỒN/TIÊU ĐỀ (kể cả không kèm chữ "Nguồn") tự đóng/mở được nhãn
    ``[Nguồn: ...]`` bao ngoài - đổi sang ngoặc tròn để giữ chữ mà không giữ cấu trúc. Gọi SAU
    ``khu_gia_mao_trong_doan``: đó lo đúng mẫu "[Nguồn:", đây lo MỌI ngoặc còn sót có thể đóng sớm khối bao
    ngoài dù không mang chữ "Nguồn" (vd tiêu đề "Sản phẩm] Giảm giá" không có "Nguồn" nhưng dấu ``]`` vẫn
    đóng sớm được ``[Nguồn: ...]`` thật)."""
    return NGOAC_CA_HAI_RE.sub(lambda m: "(" if m.group(0) in NGOAC_MO_SET else ")", s)


def khu_gia_mao_trong_doan(s: str) -> str:
    """Khử giả mạo trong MỘT chuỗi - dùng cho cả ``noi_dung`` LẪN ``ten_nguon``/``tieu_de`` (cùng một
    pipeline, xem docstring đầu file).

    Export để test đo trực tiếp: (a) test siêu tập so quy tắc mới với quy tắc cũ trên cùng một tập payload,
    (b) test hiệu năng tuyến tính - cả hai cần gọi thẳng hàm này, đi qua nguyên cả tool sẽ làm nhiễu số đo.

    ``normalize("NFC")`` trước khi khử: ``[Nguồn:`` viết dạng NFD (chữ "ồ" tách thành "o" + hai dấu tổ hợp)
    lọt vì regex so khớp CHUỖI CODEPOINT. NFC an toàn hơn NFKC nhiều: chỉ GHÉP LẠI tổ hợp CHUẨN TẮC, không
    đổi nghĩa hay hình dạng hiển thị (khác NFKC đã bị loại ở nghiên cứu Câu hỏi 1 vì đổi ``½``->``1⁄2``,
    ``ﬁ``->``fi``...)."""
    return khu_dai_phan_cach_gia(NHAN_NGUON_GIA_RE.sub("(Nguồn:", unicodedata.normalize("NFC", s)))
