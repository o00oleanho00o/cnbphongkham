# ported from: src/zalo/zalo-message-parser.ts
"""Đọc một tin của listener zca-js (đã chuyển qua bridge dạng JSON) thành ``InboundMessage``.

Forced deviations:

* ``ParsedMessage`` (a TS type) becomes the contract model ``pema_contracts.channel.InboundMessage``.
Field names
  are the snake_case of the original (``threadId`` -> ``thread_id``, ``rawData`` -> ``raw`` ...).
  ``thread_type``
  (zca-js ``ThreadType`` 0/1) becomes ``thread_kind`` (``ThreadKind``); ``sent_at`` is an aware datetime (the
  model normalises it to +07:00) instead of an ISO UTC string.
* New fields of the contract: ``channel`` (always ``zalo_personal``), ``kind`` (``image`` when an image was
  picked) and ``update_id`` (the de-duplication key, equal to the Zalo ``msgId``; a stable fallback when the
  payload has none).
* The model strips surrounding whitespace of ``text`` (``ApiModel.str_strip_whitespace``). The original
kept it;
  nothing downstream depends on leading or trailing blanks.
* ``text`` is cut at 20000 characters, the limit of the contract. A Zalo message is far below it.

The parser NEVER raises: a malformed payload yields a message with empty strings, exactly like the original,
so the router can report the anomaly (``payload_anomaly_watch``) instead of crashing the listener.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from pema.channels.zalo_personal.zalo_image_variant import pick_image_variant
from pema.channels.zalo_personal.zalo_message_timestamp import moc_gui_cua_tin_zalo
from pema_contracts.channel import (
    ChannelKind,
    InboundImage,
    InboundKind,
    InboundMessage,
    ThreadKind,
)
from pema_contracts.common import JsonObject

_TEXT_LIMIT = 20000


def _js_string(value: object, default: str = "") -> str:
    """JS ``String(value ?? default)`` for the shapes a Zalo payload can carry."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(value)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def describe_for_history(msg: InboundMessage) -> str:
    """Nội dung ghi vào history cho 1 tin đến. Ảnh không vào được cột text nên để lại dấu vết đếm được;
    tin chỉ
    có ảnh vẫn phải có chữ, nếu không lượt sau model đọc history thấy một dòng trống không hiểu chuyện gì đã
    xảy ra."""
    image_note = f" [gửi kèm {len(msg.images)} ảnh]" if msg.images else ""
    return f"{msg.text}{image_note}".strip() or "[ảnh]"


def parse_incoming_message(
    account_id: str,
    self_id: str,
    message: Mapping[str, object],
    image_quality: str = "normal",
    nhan_luc: datetime | None = None,
) -> InboundMessage:
    """``image_quality``: cỡ ảnh lấy từ payload Zalo - caller truyền ``get_tuning("ZALO_IMAGE_QUALITY")`` vào
    để module này thuần, test khỏi cần cài provider (cùng lý do với ``botEnabledForThread`` của
    allowlist-filter)."""
    data = _mapping(message.get("data"))
    content = data.get("content")
    msg_type = _js_string(data.get("msgType"))

    text = ""
    images: list[InboundImage] = []

    if isinstance(content, str):
        text = content
    elif isinstance(content, Mapping):
        content_map: Mapping[str, object] = content  # pyright: ignore[reportUnknownVariableType]
        # Tin nhắn media: content là object có href/thumb + title (caption)
        title = content_map.get("title")
        description = content_map.get("description")
        text = _js_string(title if title is not None else description)
        # Zalo gửi kèm nhiều cỡ của cùng 1 ảnh. Lấy `hd` (bản to nhất) là tốn token vô ích: ảnh HD 977x2128
        # ~2500 token mỗi lần vào context.
        picked = pick_image_variant(content_map, image_quality) if "photo" in msg_type else None
        if picked is not None:
            images.append(InboundImage(url=picked.url))

    raw_mentions = data.get("mentions")
    mentions: list[object] = list(raw_mentions) if isinstance(raw_mentions, list) else []  # pyright: ignore[reportUnknownArgumentType]
    mentions_me = any(_js_string(_mapping(m).get("uid"), "undefined") == self_id for m in mentions)

    raw_type = message.get("type")
    is_group = raw_type == 1 and not isinstance(raw_type, bool)
    thread_kind = ThreadKind.GROUP if is_group else ThreadKind.USER

    thread_id = _js_string(message.get("threadId"))
    msg_id = _js_string(data.get("msgId"))
    cli_msg_id = _js_string(data.get("cliMsgId"))
    sent_at = moc_gui_cua_tin_zalo(data.get("ts"), nhan_luc)
    update_id = msg_id or f"{thread_id}:{cli_msg_id or sent_at.isoformat()}"

    raw: JsonObject = dict(data)

    return InboundMessage(
        channel=ChannelKind.ZALO_PERSONAL,
        account_id=account_id,
        update_id=update_id,
        kind=InboundKind.IMAGE if images else InboundKind.TEXT,
        thread_id=thread_id,
        thread_kind=thread_kind,
        is_group=is_group,
        sender_id=_js_string(data.get("uidFrom")),
        sender_name=_js_string(data.get("dName"), "Người dùng"),
        text=text[:_TEXT_LIMIT],
        images=images,
        msg_id=msg_id,
        cli_msg_id=cli_msg_id,
        is_self=bool(message.get("isSelf")),
        mentions_me=mentions_me,
        sent_at=sent_at,
        raw=raw,
    )
