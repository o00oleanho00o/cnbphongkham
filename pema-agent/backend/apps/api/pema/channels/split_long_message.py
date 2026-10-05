# ported from: src/zalo/split-long-message.ts
"""Cắt câu trả lời dài thành nhiều tin nhắn Zalo (split a long reply into several Zalo messages).

Vì sao cần: Zalo chặn tin quá dài ở PHÍA SERVER (error_code 118 "Nội dung quá dài") - zca-js không kiểm
gì, chỉ ném lỗi lên. Trước khi có module này, một câu trả lời dài là mất trắng: tin không gửi được,
không vào history, người nhắn không nhận được gì sau khi bot đã đốt cả trăm nghìn token.

Nguyên tắc cắt: KHÔNG BAO GIỜ cắt giữa từ, ưu tiên ranh giới tự nhiên từ to xuống nhỏ (đoạn văn -> dòng ->
câu -> khoảng trắng). Cắt cứng chỉ dùng khi một "từ" đơn dài hơn cả cửa sổ (URL khổng lồ) - lúc đó không
còn lựa chọn.

Pure module (no env, no logger). Forced deviations:

* Lengths and offsets are UTF-16 code units like the JS original (``max_chars`` is a JS ``String.length``
  budget, ``DoanDaCat.bat_dau`` / ``phu_goc`` are UTF-16 offsets into the INPUT text). The algorithm runs on a
  unit string (see ``utf16_text``), so it is the original line for line.
* The only behaviour change: the hard cut (case 5) never splits a surrogate pair (an emoji); the JS original
  could cut it in half and send a lone surrogate.
* ``trim`` / ``trimEnd`` / ``trimStart`` and ``\\s`` use the exact JS whitespace set (``utf16_text``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from pema.channels.utf16_text import (
    JS_S,
    from_units,
    js_trim,
    js_trim_end,
    js_trim_start,
    khong_cat_giua_cap_thay_the,
    to_units,
)


@dataclass(frozen=True)
class SplitOptions:
    # Số ký tự tối đa mỗi tin (UTF-16 units, như `String.length` của JS)
    max_chars: int
    # Số tin tối đa cho 1 lượt trả lời - bắn quá nhiều tin liên tiếp dễ bị Zalo coi là spam
    max_parts: int


# Ghi chú gắn vào đoạn cuối khi câu trả lời vượt trần số đoạn. Nói thật là còn nữa thay vì cắt ngang im
# lặng để người đọc biết mà hỏi tiếp.
OVERFLOW_NOTE = "\n\n(Phần sau còn dài, bạn hỏi tiếp phần cần rõ nhé.)"

# Chỉ nhận điểm cắt nằm sau ngưỡng này của cửa sổ. Không có ràng buộc đó, một dòng trống ở ký tự thứ 30 sẽ
# sinh ra đoạn 30 ký tự rồi đoạn 2000 ký tự - cũng là một kiểu cắt vô duyên.
MIN_FILL_RATIO = 0.5

# Kết thúc câu: cắt NGAY SAU dấu để câu không bị mất dấu chấm
SENTENCE_END = re.compile(f"[.!?…](?={JS_S})")


def _find_cut_index(text: str, limit: int) -> int:
    """Vị trí cắt tốt nhất trong `limit` ký tự đầu của text (a unit string).

    Trả về index để `text[:index]` là đoạn giữ lại.
    """
    window = text[:limit]
    min_index = math.floor(limit * MIN_FILL_RATIO)

    # 1. Dòng trống - ranh giới đoạn văn, giữ nguyên khối ý
    paragraph = window.rfind("\n\n")
    if paragraph >= min_index:
        return paragraph

    # 2. Xuống dòng đơn - giữ nguyên từng gạch đầu dòng của danh sách
    line = window.rfind("\n")
    if line >= min_index:
        return line

    # 3. Hết câu (cắt sau dấu chấm/hỏi/than)
    sentence = -1
    for match in SENTENCE_END.finditer(window):
        if match.start() >= min_index:
            sentence = match.start() + 1
    if sentence > 0:
        return sentence

    # 4. Khoảng trắng - tệ nhất cũng không cắt giữa từ
    space = window.rfind(" ")
    if space > 0:
        return space

    # 5. Không có chỗ nào cắt được (1 "từ" dài hơn cả cửa sổ, vd URL) - cắt cứng. Không bao giờ cắt đôi
    #    một cặp thay thế (emoji).
    return khong_cat_giua_cap_thay_the(text, limit)


@dataclass(frozen=True)
class DoanDaCat:
    """Một đoạn đã cắt, kèm vị trí của nó trong chuỗi GỐC.

    `bat_dau` tính trên chuỗi ĐƯA VÀO (trước `.trim()` của hàm này), để caller dời được các span định dạng
    sang offset của từng đoạn. Không có nó thì không cách nào suy ngược: `trimEnd`/`trimStart` XÓA ký tự ở
    ranh giới, nên đếm lại từ ngoài chắc chắn lệch.

    `phu_goc`: số ký tự của chuỗi GỐC mà đoạn này phủ, tính từ `bat_dau`. Thường bằng độ dài `text`, TRỪ
    đoạn cuối bị dán thêm ghi chú "còn nữa": ghi chú là chữ thêm vào, không có trong chuỗi gốc. Lấy độ
    dài `text` làm phạm vi ở đoạn đó thì span nằm trong phần BỊ CẮT BỎ sẽ rơi trúng ghi chú.

    Both numbers are UTF-16 units.
    """

    text: str
    bat_dau: int
    phu_goc: int


def split_long_message_with_offsets(text: str, options: SplitOptions) -> list[DoanDaCat]:
    """Bản trả về KÈM MỐC - dùng khi tin có định dạng (`TextStyle[]`) cần dời theo.

    `split_long_message` bên dưới chỉ là lớp mỏng bọc hàm này. MỘT thuật toán cắt duy nhất: nhân bản ra hai
    bản sẽ trôi khỏi nhau, và bản ít được để mắt hơn sẽ là bản sai.
    """
    max_chars = options.max_chars
    max_parts = options.max_parts
    units = to_units(text)
    trimmed = js_trim(units)
    if not trimmed:
        return []
    # `.trim()` cắt đầu chuỗi nên mọi mốc phải cộng lại phần đã mất
    lech = units.find(trimmed)
    if len(trimmed) <= max_chars:
        return [DoanDaCat(text=from_units(trimmed), bat_dau=lech, phu_goc=len(trimmed))]

    parts: list[DoanDaCat] = []
    rest = trimmed
    vi_tri = lech

    while len(rest) > max_chars:
        # Đã tới đoạn cuối được phép mà vẫn còn dài: cắt kèm ghi chú "còn nữa"
        if len(parts) + 1 >= max_parts:
            room = max(1, max_chars - len(OVERFLOW_NOTE))
            cut = _find_cut_index(rest, room)
            than = js_trim_end(rest[:cut])
            # Ghi chú "còn nữa" là chữ THÊM VÀO, không có trong chuỗi gốc - `phu_goc` chỉ tính phần thân, và
            # nó nằm ở CUỐI nên không đẩy lệch span nào phía trước.
            parts.append(DoanDaCat(text=from_units(than) + OVERFLOW_NOTE, bat_dau=vi_tri, phu_goc=len(than)))
            return parts

        cut = _find_cut_index(rest, max_chars)
        chunk = js_trim_end(rest[:cut])
        if chunk:
            parts.append(DoanDaCat(text=from_units(chunk), bat_dau=vi_tri, phu_goc=len(chunk)))

        con_lai = rest[cut:]
        da_cat_dau = len(con_lai) - len(js_trim_start(con_lai))
        vi_tri += cut + da_cat_dau
        rest = js_trim_start(con_lai)

    if rest:
        parts.append(DoanDaCat(text=from_units(rest), bat_dau=vi_tri, phu_goc=len(rest)))
    return parts


def split_long_message(text: str, options: SplitOptions) -> list[str]:
    """Chia text thành các tin nhắn gửi tuần tự. Text ngắn trả về đúng 1 phần tử, text rỗng trả về danh
    sách rỗng (caller khỏi phải tự kiểm).
    """
    return [p.text for p in split_long_message_with_offsets(text, options)]
