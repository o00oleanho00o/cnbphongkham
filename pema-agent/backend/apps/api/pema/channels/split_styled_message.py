# ported from: src/zalo/split-styled-message.ts
"""Cắt tin dài KÈM định dạng.

Vì sao phải có module riêng: `TextStyle.start`/`length` tính trên TOÀN VĂN, nên khi một câu trả lời bị chẻ
thành nhiều tin Zalo, mọi span từ đoạn 2 trở đi lệch đúng bằng độ dài các đoạn trước - Zalo sẽ tô đậm nhầm
chỗ, hoặc bỏ qua span vượt biên. Bản tham chiếu (`zalo-personal`) KHÔNG gặp bài này vì nó cắt cụt ở 4000
ký tự thay vì chẻ nhiều tin.

Hai việc phải làm, và việc thứ hai dễ quên: (1) dời mốc về đầu mỗi đoạn, (2) CHẺ ĐÔI span nằm vắt qua chỗ
cắt. Bỏ luôn span vắt qua thì mất định dạng; giữ nguyên len thì tràn sang chữ không thuộc về nó.

Module THUẦN: không env, không logger, không DB. Forced deviations:

* zca-js ``Style`` is ``pema_contracts.channel.TextStyle`` (``len`` -> ``length``, ``st`` -> ``style``);
  every offset is a UTF-16 unit (see ``utf16_text``), like the JS original.
* ``so_byte_tin`` measures the wire shape of the spans (``normalize_zalo_styles.style_to_wire``) as compact
  JSON, which is what ``JSON.stringify({ styles })`` gives for the original.
* ``chia_theo_ngan_sach_byte`` takes ``NganSachByteOptions`` (a ``SplitOptions`` with ``max_payload_bytes``)
  instead of the TS intersection type ``SplitOptions & { maxPayloadBytes }``.
* ``TinCoDinhDang.bo_dinh_dang`` is a ``bool`` (``False`` where TS has ``undefined``).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from pema.channels.normalize_zalo_styles import style_to_wire
from pema.channels.split_long_message import (
    OVERFLOW_NOTE,
    SplitOptions,
    split_long_message_with_offsets,
)
from pema.channels.utf16_text import utf16_len
from pema_contracts.channel import TextStyle


@dataclass(frozen=True)
class TinCoDinhDang:
    text: str
    styles: list[TextStyle] = field(default_factory=list[TextStyle])
    # Đoạn này bị BỎ định dạng vì quá nặng so với trần byte.
    #
    # Phải có cờ riêng, KHÔNG suy ra từ `len(styles) == 0`: một đoạn vốn không có chữ nào cần tô thì cũng
    # rỗng, mà đó là chuyện bình thường. Bản đầu suy ra từ độ dài và đã báo động giả ngay lượt chạy thật đầu
    # tiên - đoạn cuối của câu trả lời chỉ là văn xuôi nên không có span nào.
    bo_dinh_dang: bool = False


@dataclass(frozen=True)
class NganSachByteOptions(SplitOptions):
    max_payload_bytes: int


def _utf8_bytes(text: str) -> int:
    # JS `Buffer.byteLength` counts a lone surrogate as 3 bytes (U+FFFD); `surrogatepass` does the same.
    return len(text.encode("utf-8", "surrogatepass"))


def so_byte_tin(tin: TinCoDinhDang) -> int:
    """Số byte một tin sẽ chiếm trên đường dây: chữ (UTF-8) cộng JSON định dạng.

    Đây là con số Zalo thật sự đo, không phải số ký tự - đã đo được bằng cách gửi thật (xem
    `chia_theo_ngan_sach_byte`). Dựng đúng hình dạng zca-js gửi đi: `textProperties: JSON.stringify({
    styles })`.
    """
    chu = _utf8_bytes(tin.text)
    if len(tin.styles) == 0:
        return chu
    payload = json.dumps(
        {"styles": [style_to_wire(s) for s in tin.styles]}, separators=(",", ":"), ensure_ascii=False
    )
    return chu + _utf8_bytes(payload)


def dem_doan_bo_dinh_dang(phan: list[TinCoDinhDang]) -> int:
    """Số đoạn THẬT SỰ bị bỏ định dạng - để nơi gửi kêu lên.

    Là hàm riêng chứ không phải một dòng `filter` ở nơi gửi, vì đây đúng là chỗ đã báo động giả: bản đầu
    đếm `styles.length === 0` và kêu ngay lượt chạy thật đầu tiên, trong khi đoạn cuối chỉ là văn xuôi nên
    vốn không có span nào. Tách ra thì phép phá code chạm được vào nó.
    """
    return sum(1 for p in phan if p.bo_dinh_dang)


# Cắt nhỏ tối đa - dưới mức này thì tin vụn tới mức khó đọc, thà bỏ định dạng
KY_TU_TOI_THIEU = 400


def _bi_vut_bot_chu(phan: list[TinCoDinhDang]) -> bool:
    """Bộ tin này có bị VỨT BỚT chữ không?

    Dấu hiệu duy nhất đáng tin là ghi chú "còn nữa" - `split_long_message` chỉ dán nó khi phải bỏ chữ vì
    hết chỗ. KHÔNG đo bằng cách so tổng số ký tự giữa hai lần cắt: cắt mịn hơn thì `trimEnd` ở mỗi ranh
    giới ăn thêm vài ký tự trắng (đo thật: 2167 -> 2165 -> 2163 -> 2159), nên phép so đó luôn báo "mất chữ"
    và vòng co thoát ngay từ bước đầu.
    """
    return bool(phan) and phan[-1].text.endswith(OVERFLOW_NOTE)


def split_styled_message(tin: TinCoDinhDang, options: SplitOptions) -> list[TinCoDinhDang]:
    """Chia `{text, styles}` thành nhiều tin, mỗi tin có mốc định dạng của RIÊNG nó.

    Không style thì đi thẳng đường cũ, khỏi tính giao nhau vô ích.
    """
    doans = split_long_message_with_offsets(tin.text, options)
    if len(tin.styles) == 0:
        return [TinCoDinhDang(text=d.text, styles=[]) for d in doans]

    ket_qua: list[TinCoDinhDang] = []
    for doan in doans:
        het = doan.bat_dau + doan.phu_goc
        do_dai_doan = utf16_len(doan.text)
        styles: list[TextStyle] = []

        for s in tin.styles:
            # Giao của [s.start, s.start+s.length) với [bat_dau, het)
            dau = max(s.start, doan.bat_dau)
            cuoi = min(s.start + s.length, het)
            if cuoi <= dau:
                continue  # không dính đoạn này

            # `trimEnd`/`trimStart` ở chỗ cắt XÓA ký tự, nên `phu_goc` có thể ngắn hơn khoảng đã tiêu. Kẹp
            # lần nữa vào độ dài chữ thật để không bao giờ phát ra span vượt biên - zca-js gói thẳng số này
            # vào JSON, không ai kiểm hộ.
            start = dau - doan.bat_dau
            length = min(cuoi - dau, do_dai_doan - start)
            if length <= 0:
                continue

            # `{...s, start, len}`: keeps every other field (e.g. the indent size of an Indent span)
            styles.append(s.model_copy(update={"start": start, "length": length}))

        ket_qua.append(TinCoDinhDang(text=doan.text, styles=styles))
    return ket_qua


def chia_theo_ngan_sach_byte(tin: TinCoDinhDang, options: NganSachByteOptions) -> list[TinCoDinhDang]:
    """Chia sao cho MỖI TIN nằm dưới ngân sách byte của Zalo.

    VÌ SAO CÓ HÀM NÀY - đo thật ngày 2026-08-05 bằng cách gửi vào Zalo:

    | byte chữ + byte style | kết quả |
    |---|---|
    | 1642 + 572 = 2214 | được |
    | 2321 + 0 = 2321 | được |
    | 320 + 2412 = 2732 | được |
    | 2321 + 546 = 2867 | được |
    | 2321 + 1391 = 3712 | HỎNG (mã 112) |
    | 2321 + 1580 = 3901 | HỎNG (mã 112) |

    Hai dòng cuối dùng ĐÚNG đoạn chữ của dòng 2321+0 - khác mỗi chỗ có style. Nên trần không nằm ở độ dài
    chữ (1600 ký tự kèm style vẫn gửi được), không nằm ở số span (80 span vẫn gửi được), không nằm ở số
    dòng (1/30/60 dòng đều được), mà ở TỔNG hai thứ cộng lại. Đã dò nhầm hướng ba vòng trước khi thấy.

    Cách chữa là cắt NHỎ HƠN chứ không phải bỏ định dạng: người dùng nhận thêm một tin thì vẫn đọc được,
    còn mất định dạng thì mất đúng thứ vừa làm ra. Chỉ khi co hết cỡ mà vẫn vượt (tin dày đặc span bất
    thường) mới bỏ định dạng của riêng đoạn đó - vẫn còn `sendOneCoDuongLui` đỡ phía sau.
    """
    max_payload_bytes = options.max_payload_bytes
    cat = SplitOptions(max_chars=options.max_chars, max_parts=options.max_parts)
    phan = split_styled_message(tin, cat)
    if len(tin.styles) == 0:
        return phan

    # Co dần trần ký tự cho tới khi mọi tin lọt ngân sách.
    #
    # Bước co 10% chứ không phải 30%: mỗi lần co quá tay là THÊM một tin người dùng phải đọc. Đo trên tin
    # thật - ở mức 980 ký tự tin chỉ vượt trần đúng 50 byte, mà bước 30% nhảy thẳng xuống 686 và đẻ ra tin
    # thứ ba không cần thiết. Vòng lặp chỉ là phép cắt chuỗi trên vài nghìn ký tự nên chạy thêm chục vòng
    # không đáng kể so với một lượt gọi API.
    ky_tu = cat.max_chars
    while any(so_byte_tin(p) > max_payload_bytes for p in phan) and ky_tu > KY_TU_TOI_THIEU:
        ky_tu = max(KY_TU_TOI_THIEU, math.floor(ky_tu * 0.9))
        thu = split_styled_message(tin, SplitOptions(max_chars=ky_tu, max_parts=cat.max_parts))

        # DỪNG khi co tiếp làm MẤT CHỮ - đo thẳng số chữ giao được, không đo số tin. Bản đầu chặn bằng
        # `thu.length >= maxParts` và đó là đo sai đại lượng: chạm đúng trần số tin KHÔNG phải mất chữ
        # (`split_long_message` chỉ cắt bớt khi cần NHIỀU HƠN max_parts). Hậu quả đo được trên tin thật: ở
        # bước co 685 ký tự bộ cắt cho ra 5 tin, mọi tin đều dưới trần và không hụt chữ - vậy mà chốt chặn
        # nổ, vứt kết quả tốt, giữ bản 3 tin có một tin 3754 byte rồi bỏ định dạng của tin đó. Người dùng
        # nhận tin đầu phẳng lì.
        if _bi_vut_bot_chu(thu):
            break
        phan = thu

    # Đoạn nào vẫn quá khổ thì bỏ định dạng của riêng nó, giữ nguyên chữ. Đánh dấu `bo_dinh_dang` để nơi gửi
    # phân biệt được với đoạn vốn không có gì để tô.
    return [
        TinCoDinhDang(text=p.text, styles=[], bo_dinh_dang=True) if so_byte_tin(p) > max_payload_bytes else p
        for p in phan
    ]
