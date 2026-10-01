# ported from: src/zalo/payload-anomaly-watch.ts
"""Warn when a channel payload no longer matches the assumptions of the parser.

Why: a parser that digs into a raw payload does not break loudly when Zalo renames a field; the bot just
silently stops seeing images or recognising an @mention. Worst of all is a missing thread id: the message is
dropped with no trace in the log.

Only the 3 signs that are certainly wrong are kept, no guessing: a sticker/system message with an odd content
shape is normal, and warning at random turns into noise that gets ignored.

Forced deviations: ``ParsedMessage`` is ``InboundMessage`` (``raw`` replaces ``rawData``); the log carries ids
and codes only, never message content. Shared by both channels (C2 imports it).
"""

from __future__ import annotations

import time

from pema.shared.logger import create_logger
from pema_contracts.channel import InboundMessage

_log = create_logger("payload-anomaly")

THROTTLE_MS = 10 * 60_000
"""A broken payload is broken for EVERY message and logging each time floods the file. Each anomaly kind of
each account is logged again only after 10 minutes."""

_last_logged_at: dict[str, float] = {}


def _msg_type_of(parsed: InboundMessage) -> str:
    return str(parsed.raw.get("msgType") or "")


def detect_payload_anomalies(parsed: InboundMessage) -> list[str]:
    anomalies: list[str] = []

    if not parsed.thread_id:
        anomalies.append("thiếu threadId - tin nhắn bị bỏ qua hoàn toàn")
    if not parsed.sender_id and not parsed.is_self:
        anomalies.append("thiếu uidFrom - không ghi được contact")
    if "photo" in _msg_type_of(parsed) and len(parsed.images) == 0:
        anomalies.append("tin ảnh nhưng không moi được URL - có thể Zalo đã đổi tên field")

    return anomalies


def report_payload_anomalies(
    account_id: str, parsed: InboundMessage, now_ms: float | None = None
) -> list[str]:
    """Returns the warnings that were REALLY logged (after the throttle), so a test can check them."""
    now = time.time() * 1000 if now_ms is None else now_ms
    logged: list[str] = []

    for anomaly in detect_payload_anomalies(parsed):
        key = f"{account_id}:{anomaly}"
        last = _last_logged_at.get(key)
        if last is not None and now - last < THROTTLE_MS:
            continue

        _last_logged_at[key] = now
        logged.append(anomaly)
        _log.warning(
            f"Payload Zalo không khớp giả định: {anomaly}",
            account_id=account_id,
            msg_type=_msg_type_of(parsed),
            thread_id=parsed.thread_id or "(rỗng)",
        )

    return logged


def reset_anomaly_throttle() -> None:
    """For tests, so each case runs without the throttle of the previous one."""
    _last_logged_at.clear()
