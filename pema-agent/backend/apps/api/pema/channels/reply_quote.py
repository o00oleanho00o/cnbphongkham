# ported from: src/zalo/reply-quote.ts
"""Trích dẫn tin người dùng khi bot trả lời trong NHÓM.

Vì sao cần: bot trả lời một lượt gộp, mà trong nhóm nhiều người cùng nhắn thì không ai biết câu trả lời đang
nhắm vào tin nào. Zalo có sẵn khối trích dẫn - dùng nó là cách rẻ nhất để nói "câu này trả lời cho tin kia".

goclaw làm đúng vậy và chỉ làm trong nhóm (`cmd/gateway_consumer_normal.go`: `if isGroup {
outMeta["reply_to_message_id"] = ... }`), kèm chú thích nói rõ mục đích: "render a clear 'this reply is for
X' signal". Chat riêng chỉ có hai người nên trích dẫn là nhiễu - đó cũng là lựa chọn ở đây.

Module THUẦN: không log, không đọc env, không chạm DB, không gọi mạng.

Forced deviations:

* The TS takes a ``ParsedMessage`` (``isGroup``, ``rawData``) and returns zca-js ``SendMessageQuote``. Here
  the input is ``pema_contracts.channel.InboundMessage`` (``is_group``, ``raw`` = the zca-js ``data`` object)
  and the result is ``QuoteRef``: ``msg_id`` / ``cli_msg_id`` / ``sender_id`` come from ``msgId`` /
  ``cliMsgId`` / ``uidFrom`` and ``QuoteRef.raw`` holds the FULL ``SendMessageQuote`` dict ``{content,
  msgType, propertyExt, uidFrom, msgId, cliMsgId, ts, ttl}`` (key order kept; ``content`` / ``propertyExt``
  are left out when the payload has none, like ``JSON.stringify`` drops ``undefined``). That dict is what
  goes to the bridge as ``quote``.
* ``so_byte_trich_dan`` measures compact JSON of ``quote.raw`` (``separators=(",", ":")``,
  ``ensure_ascii=False``), the same bytes as ``JSON.stringify``.
* ``trich_dan_trong_ngan_sach`` returns a ``QuoteBudget`` dataclass instead of an object literal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pema_contracts.channel import InboundMessage, QuoteRef

# Các trường `SendMessageQuote` cần: msgType, content, propertyExt, uidFrom, msgId, cliMsgId, ts, ttl.


def la_loai_trich_dan_duoc(msg_type: str, content: object) -> bool:
    """Loại tin này trích dẫn được không.

    Hai điều kiện dưới đây SAO CHÉP đúng phần kiểm của zca-js (`src/apis/sendMessage.ts`, khối `if (quote)`
    trong `handleMessage`):

      if (typeof quote.content != "string" && quote.msgType == "webchat") throw
      if (quote.msgType == "group.poll") throw

    Phải lọc TRƯỚC chứ không đợi bắt lỗi: zca-js ném `ZaloApiError` KHÔNG kèm mã số cho hai ca này, mà
    `laLoiMayChuTuChoi` nhận diện lỗi máy chủ bằng chính `typeof err.code === "number"`. Lỗi không mã sẽ bị
    ném thẳng lên và cả câu trả lời mất trắng - đúng lớp hỏng đã trả giá ngày 05/08 với tổ hợp style.

    Bản zca-js sau này thêm điều kiện thứ ba thì chỗ này lạc hậu. Đó là lý do đường lui ở
    `send_reply_in_parts` vẫn bỏ trích dẫn khi máy chủ từ chối: hai lớp, không phải một.
    """
    if msg_type == "group.poll":
        return False
    return not (msg_type == "webchat" and not isinstance(content, str))


def _is_js_number(value: object) -> bool:
    """JS `typeof value === "number"` for a JSON value (a Python ``bool`` is not a number in JS)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _js_number_to_string(value: int | float) -> str:
    """JS `String(number)` for the values a Zalo timestamp takes: integers, with or without a ``.0``."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _ts_to_string(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and _is_js_number(value):
        return _js_number_to_string(value)
    return ""


def _ttl_of(value: object) -> int | float:
    """`typeof goc.ttl === "number" ? goc.ttl : 0`."""
    if isinstance(value, int | float) and _is_js_number(value):
        return int(value) if isinstance(value, float) and value.is_integer() else value
    return 0


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def trich_dan_tu_tin(msg: InboundMessage) -> QuoteRef | None:
    """Dựng trích dẫn từ một tin đã nhận. `None` = không trích (và đó là nhánh bình thường, không phải lỗi).

    Nhận tin nào là quyết định của caller. `message_turn_processor` truyền tin ĐẦU batch - tin mở lượt,
    thường mang câu hỏi chính, và không xê dịch khi có tin chen giữa lượt.
    """
    # Chat riêng: hai người, trích dẫn không thêm thông tin gì
    if not msg.is_group:
        return None

    goc = msg.raw
    msg_type = _as_str(goc.get("msgType"))
    if not msg_type or not la_loai_trich_dan_duoc(msg_type, goc.get("content")):
        return None

    # `ts` về dạng chuỗi trong payload thật nhưng nhận cả số cho chắc
    ts = _ts_to_string(goc.get("ts"))
    msg_id = _as_str(goc.get("msgId"))
    cli_msg_id = _as_str(goc.get("cliMsgId"))
    uid_from = _as_str(goc.get("uidFrom"))

    # Thiếu một trong bốn định danh là Zalo không tìm ra tin gốc. Đây cũng là cửa chặn tin TỔNG HỢP của lượt
    # theo lịch (`buildSyntheticMessage` để msgId rỗng có chủ đích) - không có tin thật nào để mà trích.
    if not ts or not msg_id or not cli_msg_id or not uid_from:
        return None

    # Dựng cả object ở ĐÂY, sau khi đã kiểm từng trường: `content` và `propertyExt` là union rộng của
    # zca-js, kiểm sâu hơn cũng không thêm an toàn vì chúng được chuyển tiếp nguyên vẹn.
    quote: dict[str, Any] = {}
    if "content" in goc:
        quote["content"] = goc["content"]
    quote["msgType"] = msg_type
    if "propertyExt" in goc:
        quote["propertyExt"] = goc["propertyExt"]
    quote["uidFrom"] = uid_from
    quote["msgId"] = msg_id
    quote["cliMsgId"] = cli_msg_id
    quote["ts"] = ts
    quote["ttl"] = _ttl_of(goc.get("ttl"))
    return QuoteRef(msg_id=msg_id, cli_msg_id=cli_msg_id, sender_id=uid_from, raw=quote)


def so_byte_trich_dan(quote: QuoteRef) -> int:
    """Trích dẫn chiếm bao nhiêu byte trên đường dây.

    ƯỚC LƯỢNG THỪA có chủ đích: zca-js rải các trường này ra `qmsg`, `qmsgAttach`, `qmsgOwner`... còn đây đo
    cả object dạng JSON. Thừa thì chỉ tốn thêm một chỗ cắt, thiếu thì tin đầu vượt trần và bị Zalo chối -
    hai hậu quả không cùng cỡ.
    """
    payload = json.dumps(quote.raw, separators=(",", ":"), ensure_ascii=False)
    # JS `Buffer.byteLength` counts a lone surrogate as 3 bytes; `surrogatepass` does the same.
    return len(payload.encode("utf-8", "surrogatepass"))


# Trích dẫn dài nhất được phép, tính theo phần của trần byte.
#
# Vì sao phải có trần riêng: `chia_theo_ngan_sach_byte` chia chữ của BOT theo ngân sách byte, nó không biết gì
# về phần trích dẫn cộng thêm. Người ta dán một đoạn 4000 ký tự rồi bot trích lại là riêng khối trích dẫn đã
# vượt trần, mà bộ cắt thì vẫn báo mọi đoạn đều lọt.
TY_LE_TOI_DA = 0.3


@dataclass(frozen=True)
class QuoteBudget:
    quote: QuoteRef | None
    tran_con_lai: int
    bo_vi_qua_dai: bool


def trich_dan_trong_ngan_sach(quote: QuoteRef | None, tran_byte: int) -> QuoteBudget:
    """Chốt xem có trích dẫn được trong ngân sách không, và trần byte còn lại cho chữ của bot.

    Trừ trần cho MỌI đoạn chứ không riêng đoạn đầu (chỉ đoạn đầu mang trích dẫn): cách này hơi rộng tay,
    nhiều nhất là đẻ thêm một đoạn cho câu trả lời dài. Đổi lại `chia_theo_ngan_sach_byte` không phải biết
    tới khái niệm "ngân sách riêng cho đoạn đầu" - một tham số mà chỉ một caller dùng tới.
    """
    if quote is None:
        return QuoteBudget(quote=None, tran_con_lai=tran_byte, bo_vi_qua_dai=False)

    chi_phi = so_byte_trich_dan(quote)
    if chi_phi > tran_byte * TY_LE_TOI_DA:
        return QuoteBudget(quote=None, tran_con_lai=tran_byte, bo_vi_qua_dai=True)
    return QuoteBudget(quote=quote, tran_con_lai=tran_byte - chi_phi, bo_vi_qua_dai=False)
