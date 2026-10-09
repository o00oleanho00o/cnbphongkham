# ported from: src/zalo/message-receipts.ts, src/zalo/reply-quote.ts
"""What the personal channel builds from a received message's raw zca-js ``data``: the parameters of the
"delivered" / "seen" receipts and the quote block of a reply in a group. Pure: no network, no logging.

Receipts: the bot reads through the listener, not an open chat window, so Zalo fires neither event by itself
and the sender's message would stay "Sent" for ever, as if the bot were dead. A real Zalo client sends
"delivered" as soon as a message arrives and "seen" when the chat is opened: delivered for EVERY message,
seen only for the messages the bot actually handles. zca-js needs all nine fields of a receipt.

Quotes: in a group several people write at once, so a reply quotes the message it answers; in a one-to-one
chat a quote adds nothing. The two checks below copy zca-js's own (``sendMessage`` throws without a numeric
code for them, which would lose the whole reply), so they are filtered here first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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


def receipt_params(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """The zca-js ``sendSeenEvent`` / ``sendDeliveredEvent`` item of one message; None without ids."""
    msg_id = _text(raw.get("msgId"))
    uid_from = _text(raw.get("uidFrom"))
    id_to = _text(raw.get("idTo"))
    if not msg_id or not uid_from or not id_to:
        return None
    ts = raw.get("ts")
    return {
        "msgId": msg_id,
        "cliMsgId": _text(raw.get("cliMsgId")) or msg_id,
        "uidFrom": uid_from,
        "idTo": id_to,
        "msgType": _text(raw.get("msgType"), "webchat"),
        "st": _number(raw.get("st")),
        "at": _number(raw.get("at")),
        "cmd": _number(raw.get("cmd")),
        "ts": ts if isinstance(ts, str | int) and not isinstance(ts, bool) else 0,
    }


def quotable(msg_type: str, content: object) -> bool:
    """zca-js refuses to quote a poll, and a ``webchat`` message whose content is not text."""
    if msg_type == "group.poll":
        return False
    return not (msg_type == "webchat" and not isinstance(content, str))


def _ts_to_string(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return ""


def _ttl_of(value: object) -> int | float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value) if isinstance(value, float) and value.is_integer() else value
    return 0


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def quote_from(raw: Mapping[str, Any], *, is_group: bool) -> dict[str, Any] | None:
    """The zca-js ``SendMessageQuote`` of a received message (key order of the original), or None: not in a
    group, a kind that cannot be quoted, or a missing id (Zalo would not find the message)."""
    if not is_group:
        return None
    msg_type = _as_str(raw.get("msgType"))
    if not msg_type or not quotable(msg_type, raw.get("content")):
        return None
    ts = _ts_to_string(raw.get("ts"))
    msg_id = _as_str(raw.get("msgId"))
    cli_msg_id = _as_str(raw.get("cliMsgId"))
    uid_from = _as_str(raw.get("uidFrom"))
    if not ts or not msg_id or not cli_msg_id or not uid_from:
        return None
    quote: dict[str, Any] = {}
    if "content" in raw:
        quote["content"] = raw["content"]
    quote["msgType"] = msg_type
    if "propertyExt" in raw:
        quote["propertyExt"] = raw["propertyExt"]
    quote["uidFrom"] = uid_from
    quote["msgId"] = msg_id
    quote["cliMsgId"] = cli_msg_id
    quote["ts"] = ts
    quote["ttl"] = _ttl_of(raw.get("ttl"))
    return quote
