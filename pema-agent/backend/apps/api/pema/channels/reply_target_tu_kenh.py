# ported from: src/zalo/reply-target-tu-kenh.ts
"""Build a ``ReplyTarget`` from a channel: the ONE place that knows which channel fields must travel down to
the send path.

Why gather it: there are FOUR places that need this (the personal channel turn, the bot channel busy-wait
notice, the scheduler send path, the daily-cap notice), and the fields it carries are all OPTIONAL
(``tran_ky_tu_mot_tin``, ``mang_dinh_dang``). Optional means that forgetting one is silent for the type
checker and the consequence is mute: a missing ``tran_ky_tu_mot_tin`` loses the whole reply on the bot channel
(the server refuses the entire message), a missing ``mang_dinh_dang`` budgets bytes for ``styles`` that are
about to be dropped and splits a message for nothing.

Do NOT set ``quote`` here: only a message turn in a group has a message to quote, and that caller adds it.

Forced deviations (package seams): ``KenhLuot`` is ``ChannelPort``; ``ThreadType`` is ``ThreadKind``.
``ReplyTarget`` and ``DoanCanGui`` are the ones of ``send_reply_in_parts`` (package C2), where the original
defines them: C1 and C2 share ONE shape (the field is ``thread_type``), and this module only builds it from a
channel through C2's ``reply_target_from_channel``. A part the channel refuses raises
``ChannelSendRejectedError`` (``SendRejectedError`` is the same class under C1's name), because the original
send path learns about a failed part from an exception and must not read a rejection as a delivery.
"""

from __future__ import annotations

from pema.channels.send_reply_in_parts import (
    ChannelSendRejectedError,
    DoanCanGui,
    ReplyTarget,
    reply_target_from_channel,
)
from pema_contracts.channel import ChannelPort, ThreadKind

SendRejectedError = ChannelSendRejectedError
"""C1's name of the exception the send path raises for a rejected ``SendResult``."""

__all__ = [
    "ChannelSendRejectedError",
    "DoanCanGui",
    "ReplyTarget",
    "SendRejectedError",
    "reply_target_tu_kenh",
]


def reply_target_tu_kenh(
    *,
    kenh: ChannelPort,
    thread_id: str,
    thread_kind: ThreadKind,
    thread_key: str,
    proactive: bool = False,
) -> ReplyTarget:
    return reply_target_from_channel(kenh, thread_id, thread_kind, thread_key, proactive=proactive)
