# ported from: src/zalo/message-receipts.ts
"""Báo trạng thái "đã nhận" / "đã xem" về cho người gửi.

Vì sao cần: bot đọc tin qua listener chứ không mở cửa sổ chat, nên Zalo không tự bắn hai sự kiện này - phía
người nhắn thấy tin dừng ở "Đã gửi" mãi mãi, trông như bot đã chết. Client Zalo thật gửi "đã nhận" ngay
khi tin
về máy và gửi "đã xem" khi người dùng mở hội thoại ra đọc; mình bám đúng nếp đó:

* deliver receipt: MỌI tin nhận được, kể cả tin bot sẽ bỏ qua
* seen receipt: chỉ tin bot thật sự xử lý (giống người mở chat lên đọc)

Cả hai đều là best-effort: lỗi chỉ log debug, không bao giờ được làm chậm hay chết đường trả lời (cùng nguyên
tắc với auto-react).

Chữ ký hàm zca-js đã đối chiếu source thật (``src/apis/sendSeenEvent.ts``,
``src/apis/sendDeliveredEvent.ts``):
cần đủ 9 field của ``ReceiptParams``, và mọi tin trong một lần gọi phải cùng thread.

Forced deviation (sync fire-and-forget -> asyncio): ``send_delivered_receipt`` / ``send_seen_receipt``
schedule a
task (strong reference kept until it ends, otherwise the loop may garbage-collect it) and return at once, like
``void api.sendX().catch(...)``. The awaitable cores ``deliver_receipt_now`` / ``seen_receipt_now`` are
what the
task runs; tests await them. The call goes through the bridge, so it needs a running event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from typing import Any

from pema.channels.zalo_personal.bridge_client import ReceiptParams, ZaloApi
from pema.shared.logger import create_logger
from pema_contracts.channel import InboundMessage, ThreadKind

log = create_logger("message-receipts")

# Tối đa 50 tin mỗi lần gọi (MAX_MESSAGES_PER_SEND của zca-js)
MAX_MESSAGES_PER_CALL = 50

_tasks: set[asyncio.Task[None]] = set()


def _text(value: object, default: str = "") -> str:
    return default if value is None else str(value)


def _number(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def to_receipt_params(msg: InboundMessage) -> ReceiptParams | None:
    """Dựng tham số từ payload gốc. zca-js đã quy "0" về uid thật trong constructor của Message nên lấy
    thẳng từ
    ``raw`` là đúng - đừng tự bịa lại từ ``InboundMessage``."""
    raw = msg.raw
    msg_id = _text(raw.get("msgId"))
    cli_msg_id = _text(raw.get("cliMsgId"))
    uid_from = _text(raw.get("uidFrom"))
    id_to = _text(raw.get("idTo"))
    if not msg_id or not uid_from or not id_to:
        return None

    ts = raw.get("ts")
    return ReceiptParams(
        msgId=msg_id,
        cliMsgId=cli_msg_id or msg_id,
        uidFrom=uid_from,
        idTo=id_to,
        msgType=_text(raw.get("msgType"), "webchat"),
        st=_number(raw.get("st")),
        at=_number(raw.get("at")),
        cmd=_number(raw.get("cmd")),
        ts=ts if isinstance(ts, str | int) and not isinstance(ts, bool) else 0,
    )


def build_batch(messages: Sequence[InboundMessage]) -> tuple[list[ReceiptParams], ThreadKind] | None:
    """Gom batch thành tham số cùng thread; bỏ tin thiếu field bắt buộc."""
    if not messages:
        return None
    first = messages[0]

    params: list[ReceiptParams] = []
    for message in messages:
        if message.thread_id != first.thread_id:
            continue
        if len(params) >= MAX_MESSAGES_PER_CALL:
            break
        item = to_receipt_params(message)
        if item is not None:
            params.append(item)

    return (params, first.thread_kind) if params else None


async def deliver_receipt_now(api: ZaloApi, message: InboundMessage) -> None:
    batch = build_batch([message])
    if batch is None:
        return
    params, thread_kind = batch
    try:
        # isSeen = false: đây mới là "đã nhận", "đã xem" đi bằng sendSeenEvent riêng
        await api.send_delivered_event(False, params, thread_kind)
    except Exception as err:
        log.debug("Báo đã nhận thất bại", thread_id=message.thread_id, err=err)


async def seen_receipt_now(api: ZaloApi, messages: Sequence[InboundMessage]) -> None:
    batch = build_batch(messages)
    if batch is None:
        return
    params, thread_kind = batch
    try:
        await api.send_seen_event(params, thread_kind)
    except Exception as err:
        log.debug("Báo đã xem thất bại", thread_id=messages[0].thread_id, err=err)


def _spawn(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def send_delivered_receipt(api: ZaloApi, message: InboundMessage) -> None:
    """ "Đã nhận" - fire-and-forget, gọi ngay khi tin về tới listener."""
    if build_batch([message]) is None:
        return
    _spawn(deliver_receipt_now(api, message))


def send_seen_receipt(api: ZaloApi, messages: Sequence[InboundMessage]) -> None:
    """ "Đã xem" - fire-and-forget, gọi khi bot bắt đầu xử lý lượt tin."""
    if build_batch(messages) is None:
        return
    _spawn(seen_receipt_now(api, messages))


async def drain_pending_receipts() -> None:
    """Wait for the receipt tasks scheduled so far (tests and shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
