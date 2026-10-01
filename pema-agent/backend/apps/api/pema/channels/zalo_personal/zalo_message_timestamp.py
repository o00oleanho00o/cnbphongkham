# ported from: src/zalo/zalo-message-timestamp.ts
"""Mốc giờ NGƯỜI TA GỬI một tin Zalo, đọc từ ``data.ts`` của zca-js.

Vì sao không dùng giờ ghi vào DB: giờ ghi là giờ tin TỚI LISTENER, không phải giờ người ta bấm gửi. Listener
nối lại sau khi mất mạng nhận một loạt tin cũ là hai mốc lệch nhau hàng giờ. Chính con số đó là thứ model
đọc để
hiểu "hôm nay", "vừa nãy", "sáng nay". Cả Hermes (``gateway/message_timestamps.py`` - lấy
``event.timestamp`` của
nền tảng) lẫn goclaw (``channels/telegram/handlers.go`` - ``time.Unix(message.Date)``) đều lấy giờ từ NỀN TẢNG
chứ không phải giờ xử lý.

Module THUẦN: không log, không đọc env, không chạm DB.

Forced deviation: the original returned an ISO UTC string; here the result is an aware UTC ``datetime`` (the
contract type ``InboundMessage.sent_at`` normalises it to +07:00 on the wire).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

# Đơn vị của `data.ts` KHÔNG được ghi ở đâu, và các repo tham khảo hiểu khác nhau:
# `zalo-personal/src/monitor.ts`
# coi là GIÂY, còn `zalo-agent-cli/src/commands/group.js` và `deplao-builder` coi là MILLI. Nên phân biệt
# bằng ĐỘ
# LỚN thay vì chọn một cách hiểu rồi cầu may:
#   - >= 1e11: chắc chắn milli (1e11 milli = 1973; 1e11 giây = năm 5138)
#   - >= 1e9:  giây (1e9 giây = 2001)
# Dưới 1e9 là rác - không có tin Zalo nào gửi trước năm 2001.
NGUONG_MILI = 1e11
NGUONG_GIAY = 1e9

# Khoảng chấp nhận quanh giờ nhận. Ngoài khoảng này thì bỏ `data.ts`, dùng giờ nhận.
#
# Rộng về phía QUÁ KHỨ có chủ đích: listener nối lại sau khi mất mạng sẽ nhận một loạt tin cũ, và giữ
# đúng giờ gửi
# thật của chúng chính là giá trị của cả module này - kẹp chặt sẽ dán nhãn "vừa gửi" lên tin của hai
# tiếng trước.
#
# Chặt về phía TƯƠNG LAI vì không tin nào gửi được từ tương lai; 5 phút chỉ để dung thứ lệch đồng hồ giữa
# máy chủ
# Zalo và máy chạy bot.
#
# Mục đích của cái kẹp này là chặn giá trị RÁC làm model tin sai ngày rồi đặt lịch sai, không phải chặn kẻ tấn
# công: `ts` do máy chủ Zalo sinh, người gửi không đặt được nó bằng nội dung tin.
TRE_TOI_DA_MS = 7 * 24 * 60 * 60 * 1000
SOM_TOI_DA_MS = 5 * 60 * 1000


def doi_sang_milli(raw: object) -> int | None:
    """Đổi ``data.ts`` thành milli epoch. ``None`` khi không đọc được."""
    so: float
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        so = float(raw)
    elif isinstance(raw, str):
        try:
            so = float(raw.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(so) or so <= 0:
        return None
    if so >= NGUONG_MILI:
        return math.floor(so)
    if so >= NGUONG_GIAY:
        return math.floor(so * 1000)
    return None


def moc_gui_cua_tin_zalo(raw: object, nhan_luc: datetime | None = None) -> datetime:
    """Mốc giờ gửi (aware UTC).

    ``raw`` là ``data.ts`` từ payload zca-js (chuỗi hoặc số). ``nhan_luc`` là giờ nhận tin - vừa là mốc
    để kẹp,
    vừa là giá trị thay thế khi ``raw`` hỏng. Truyền vào được để test không phụ thuộc đồng hồ thật.
    """
    nhan = (nhan_luc or datetime.now(UTC)).astimezone(UTC)
    milli = doi_sang_milli(raw)
    if milli is None:
        return nhan

    nhan_ms = nhan.timestamp() * 1000
    lech = milli - nhan_ms
    if lech > SOM_TOI_DA_MS or lech < -TRE_TOI_DA_MS:
        return nhan

    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=milli)
