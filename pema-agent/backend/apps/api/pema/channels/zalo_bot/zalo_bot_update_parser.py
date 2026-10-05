# ported from: src/zalo-bot/zalo-bot-update-parser.ts
"""Turn one Zalo Bot API update into the normalised message the whole system uses (``InboundMessage``, the
``ParsedMessage`` of the original: the batcher, the agent loop and the history all take this type).

This is the ONLY place that knows the shape of the Bot API data, so the rest of the system does not have to
tell which channel a message came from.

Forced deviations:

* ``ParsedMessage`` -> ``InboundMessage``; ``ThreadType`` of zca-js -> ``ThreadKind``; ``rawData`` -> ``raw``.
* ``InboundMessage`` needs a channel-unique ``update_id`` (de-duplication of webhook retries) but the Bot API
  update has none: the key is the Zalo ``message_id``, or a hash of the payload when even that is missing.
* ``text`` is capped at the contract limit (20000 characters) instead of letting validation reject the update.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotMessage, ZaloBotUpdate
from pema_contracts.channel import ChannelKind, InboundImage, InboundKind, InboundMessage, ThreadKind

_MAX_TEXT = 20000


def nhan_loai_tin_khong_co_chu(event_name: str, m: ZaloBotMessage) -> str:
    """Label for a message kind that carries no text. The Bot API sends a sticker/voice/odd kind without
    ``text``; returning an empty string runs an agent turn on a blank message."""
    if event_name == "message.sticker.received" or m.sticker:
        return "[gửi một sticker]"
    if event_name == "message.voice.received" or m.voice_url:
        return "[gửi một tin thoại]"
    # An image whose url WAS extracted stays empty: it is already in ``images``, a label would be redundant.
    if m.photo or m.photo_url:
        return ""
    # An image whose url could NOT be extracted (Zalo renamed the field) MUST have a label: empty text plus
    # empty ``images`` makes ``should_respond`` return ``skip`` with ``record: False``, i.e. the message never
    # enters history and leaves one debug line. On a channel with no ``offset`` that is a permanent silent
    # loss, and the safety net ``report_payload_anomalies`` cannot catch it either: its image branch reads
    # ``rawData.msgType``, a field that does not exist here.
    if event_name == "message.image.received":
        return "[gửi một ảnh bot chưa đọc được]"
    return "[gửi một nội dung bot chưa đọc được]"


def lay_anh(m: ZaloBotMessage) -> list[InboundImage]:
    """The Bot API image is in ``photo``; the goclaw port also reads ``photo_url``."""
    url = m.photo or m.photo_url
    return [InboundImage(url=url)] if url else []


def _kind_of(event_name: str, m: ZaloBotMessage, images: list[InboundImage]) -> InboundKind:
    if event_name == "message.sticker.received" or m.sticker:
        return InboundKind.STICKER
    if event_name == "message.voice.received" or m.voice_url:
        return InboundKind.VOICE
    if event_name == "message.unsupported.received":
        return InboundKind.UNSUPPORTED
    if event_name == "message.image.received" or images:
        return InboundKind.IMAGE
    return InboundKind.TEXT


def _sent_at(date_ms: float | None) -> datetime:
    # ``date`` is MILLISECONDS (webhook documentation), unlike Telegram's seconds. Multiplying by 1000 again
    # would move the time label in the prompt to the year 57xxx unnoticed: ``sent_at`` only shows as "[dd/mm
    # hh:mm]".
    if date_ms is not None and date_ms > 0:
        try:
            return datetime.fromtimestamp(date_ms / 1000, UTC)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(UTC)


def _update_id(m: ZaloBotMessage, update: ZaloBotUpdate) -> str:
    if m.message_id:
        return m.message_id
    canonical = json.dumps(update.model_dump(by_alias=True, mode="json"), sort_keys=True, default=str)
    return "h:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def doi_update_sang_parsed_message(account_id: str, update: ZaloBotUpdate) -> InboundMessage | None:
    m = update.message
    if m is None:
        return None

    # The bot does NOT process its own messages nor another bot's: entering the agent loop easily becomes an
    # endless loop of two bots talking to each other.
    if m.from_ is not None and m.from_.is_bot:
        return None

    la_nhom = m.chat is not None and m.chat.chat_type == "GROUP"
    images = lay_anh(m)

    # Sticker, voice and ``message.unsupported.received`` carry neither ``text`` nor ``caption``. Leaving it
    # empty builds a blank agent turn: the model gets an empty message, cannot tell what happened and answers
    # at random. An explicit label tells it what was just sent that the bot cannot read.
    chu = m.text if m.text is not None else m.caption
    if chu is None:
        chu = nhan_loai_tin_khong_co_chu(update.event_name, m)

    raw: dict[str, Any] = m.model_dump(by_alias=True, exclude_none=True, mode="json")
    chat_id = m.chat.id if m.chat is not None else None
    from_id = m.from_.id if m.from_ is not None else None

    return InboundMessage(
        channel=ChannelKind.ZALO_BOT,
        account_id=account_id,
        update_id=_update_id(m, update),
        kind=_kind_of(update.event_name, m, images),
        thread_id=chat_id or from_id or "",
        thread_kind=ThreadKind.GROUP if la_nhom else ThreadKind.USER,
        is_group=la_nhom,
        sender_id=from_id or "",
        sender_name=(m.from_.display_name if m.from_ is not None else None) or "",
        text=chu[:_MAX_TEXT],
        images=images,
        msg_id=m.message_id or "",
        # The Bot API has no client message id. ``message_id`` is reused so de-duplication on the pair
        # (msg_id, cli_msg_id) still works.
        cli_msg_id=m.message_id or "",
        is_self=False,
        # In a GROUP, Zalo only pushes an event when the bot is @mentioned or someone replies to a bot message
        # (the documentation says so). So any group message that reaches here is ALREADY aimed at the bot; no
        # mention filter of its own is needed like on the personal channel. (Groups are still internal beta on
        # Zalo's side.)
        mentions_me=True,
        sent_at=_sent_at(m.date),
        raw=raw,
    )
