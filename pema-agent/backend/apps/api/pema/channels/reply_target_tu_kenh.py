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
``ReplyTarget`` and ``DoanCanGui`` are defined HERE because the original defines them in
``send-reply-in-parts.ts``, which is package C2's and does not exist in this worktree. C2's
``send_reply_in_parts`` must accept these shapes (same field names) or re-export them; see the C1 report.
``gui_mot_doan`` RAISES ``SendRejectedError`` when the channel answers a rejected ``SendResult``, because the
original send path learns about a failed part from an exception and must not read a rejection as a delivery.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pema_contracts.channel import ChannelPort, QuoteRef, SendResult, SendStatus, TextStyle, ThreadKind


class SendRejectedError(Exception):
    """The channel refused one part (cap, kill switch, API error). Carries the ``SendResult``; no message
    text."""

    def __init__(self, result: SendResult) -> None:
        super().__init__(f"channel rejected the part: {result.error_code} {result.detail or ''}".strip())
        self.result = result


@dataclass(frozen=True)
class DoanCanGui:
    """One already split part, ready for the channel."""

    text: str
    styles: Sequence[TextStyle] = ()
    quote: QuoteRef | None = None


@dataclass(frozen=True)
class ReplyTarget:
    gui_mot_doan: Callable[[DoanCanGui], Awaitable[SendResult]]
    """Send ONE part. The only boundary between the split/repair logic and the real channel API."""
    thread_key: str
    """Key of the send queue of the rate limiter (``ThreadRef.key``)."""
    thread_id: str
    thread_kind: ThreadKind
    tran_ky_tu_mot_tin: int | None = None
    """Cap of ONE message of this channel; ``None`` = ``ZALO_MAX_MESSAGE_CHARS``."""
    mang_dinh_dang: bool | None = None
    """Can the channel carry formatting; ``None`` = yes (the personal channel behaviour)."""
    quote: QuoteRef | None = None
    """Message quoted when replying (groups only). Only the FIRST part of a reply carries it."""


def reply_target_tu_kenh(
    *,
    kenh: ChannelPort,
    thread_id: str,
    thread_kind: ThreadKind,
    thread_key: str,
    proactive: bool = False,
) -> ReplyTarget:
    caps = kenh.capabilities()

    async def gui_mot_doan(doan: DoanCanGui) -> SendResult:
        result = await kenh.send_text(
            thread_id,
            doan.text,
            thread_kind=thread_kind,
            styles=doan.styles,
            quote=doan.quote,
            proactive=proactive,
        )
        if result.status is SendStatus.REJECTED:
            raise SendRejectedError(result)
        return result

    return ReplyTarget(
        gui_mot_doan=gui_mot_doan,
        tran_ky_tu_mot_tin=caps.max_text_length,
        mang_dinh_dang=caps.supports_formatting,
        thread_key=thread_key,
        thread_id=thread_id,
        thread_kind=thread_kind,
    )
