# ported from: src/zalo-bot/zalo-bot-update-parser.ts
"""Turn one Zalo Bot API update into a ``ZaloInbound``. The ONLY place that knows the shape of the Bot API
data, so the rest of the plugin does not have to tell which kind of account a message came from."""

from __future__ import annotations

import hashlib
import json

from ..inbound import ZaloInbound
from .types import ZaloBotMessage, ZaloBotUpdate

MAX_TEXT = 20000


def nhan_loai_tin_khong_co_chu(event_name: str, m: ZaloBotMessage) -> str:
    """Label for a message kind that carries no text. The Bot API sends a sticker/voice/odd kind without
    ``text``; an empty string would run an agent turn on a blank message."""
    if event_name == "message.sticker.received" or m.sticker:
        return "[gửi một sticker]"
    if event_name == "message.voice.received" or m.voice_url:
        return "[gửi một tin thoại]"
    # An image whose url WAS extracted stays empty: it is already in ``image_urls``.
    if m.photo or m.photo_url:
        return ""
    # An image whose url could NOT be extracted (Zalo renamed the field) MUST have a label: empty text and no
    # image would drop the message for good on a channel with no ``offset``.
    if event_name == "message.image.received":
        return "[gửi một ảnh bot chưa đọc được]"
    return "[gửi một nội dung bot chưa đọc được]"


def _message_id(m: ZaloBotMessage, update: ZaloBotUpdate) -> str:
    if m.message_id:
        return m.message_id
    canonical = json.dumps(update.model_dump(by_alias=True, mode="json"), sort_keys=True, default=str)
    return "h:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def parse_update(account_id: str, update: ZaloBotUpdate) -> ZaloInbound | None:
    """None for an update without a message, without a chat or sender, or from a bot (two bots answering each
    other never stop)."""
    m = update.message
    if m is None or (m.from_ is not None and m.from_.is_bot):
        return None
    chat_id = m.chat.id if m.chat is not None else None
    sender_id = m.from_.id if m.from_ is not None else None
    if not chat_id or not sender_id:
        return None
    text = m.text if m.text is not None else m.caption
    if text is None:
        text = nhan_loai_tin_khong_co_chu(update.event_name, m)
    image = m.photo or m.photo_url
    return ZaloInbound(
        account_id=account_id,
        thread_id=chat_id,
        is_group=m.chat is not None and m.chat.chat_type == "GROUP",
        sender_id=sender_id,
        sender_name=(m.from_.display_name if m.from_ is not None else None) or "",
        message_id=_message_id(m, update),
        text=text[:MAX_TEXT],
        image_urls=(image,) if image else (),
        # In a GROUP, Zalo only pushes an event when the bot is @mentioned or someone replies to a bot message
        # (the documentation says so): any group message that reaches here is aimed at the bot.
        mentions_me=True,
    )
