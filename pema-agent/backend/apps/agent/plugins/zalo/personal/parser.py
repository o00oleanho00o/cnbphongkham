# ported from: src/zalo/zalo-message-parser.ts
"""Read one message of the zca-js listener (passed on by the bridge as JSON) into a ``ZaloInbound``.

Never raises: a malformed payload gives empty fields (the message is then dropped for lack of ids) instead of
breaking the event route. Text is cut at 20000 characters.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from ..inbound import ZaloInbound
from .image_variant import pick_image_variant

TEXT_LIMIT = 20000


def _js_string(value: object, default: str = "") -> str:
    """JS ``String(value ?? default)`` for the shapes a Zalo payload can carry."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value)


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def parse_incoming_message(
    account_id: str, own_id: str, message: Mapping[str, Any], image_quality: str = "normal"
) -> ZaloInbound:
    data = _mapping(message.get("data"))
    content = data.get("content")
    msg_type = _js_string(data.get("msgType"))

    text = ""
    images: tuple[str, ...] = ()
    if isinstance(content, str):
        text = content
    elif isinstance(content, Mapping):
        content_map = _mapping(data.get("content"))
        title = content_map.get("title")
        text = _js_string(title if title is not None else content_map.get("description"))
        # Zalo sends several sizes of one image; ``hd`` costs ~2500 tokens each time it enters the context.
        picked = pick_image_variant(content_map, image_quality) if "photo" in msg_type else None
        if picked is not None:
            images = (picked.url,)

    raw_mentions = data.get("mentions")
    mentions = cast(list[Any], raw_mentions) if isinstance(raw_mentions, list) else []
    mentions_me = bool(own_id) and any(
        _js_string(_mapping(m).get("uid"), "undefined") == own_id for m in mentions
    )

    raw_type = message.get("type")
    is_group = isinstance(raw_type, int) and not isinstance(raw_type, bool) and raw_type == 1
    thread_id = _js_string(message.get("threadId"))
    msg_id = _js_string(data.get("msgId"))
    cli_msg_id = _js_string(data.get("cliMsgId"))
    return ZaloInbound(
        account_id=account_id,
        thread_id=thread_id,
        is_group=is_group,
        sender_id=_js_string(data.get("uidFrom")),
        sender_name=_js_string(data.get("dName"), "Người dùng"),
        message_id=msg_id or (f"{thread_id}:{cli_msg_id}" if cli_msg_id else ""),
        text=text[:TEXT_LIMIT],
        image_urls=images,
        mentions_me=mentions_me,
        is_self=bool(message.get("isSelf")),
    )
