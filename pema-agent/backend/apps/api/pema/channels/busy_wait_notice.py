# ported from: src/zalo/busy-wait-notice.ts
"""Say one reassuring sentence when someone writes while the bot has been busy for a VERY long time.

Why so narrow instead of announcing "busy" every time: the sender already has three signals, the "typing..."
indicator that runs all turn, the "seen" receipt, and the automatic reaction. Stacking a text message on top
is noise and one more call to an unofficial API that the project rules say to limit.

A message added mid-turn gets all three signals ONLY when it is pulled into the turn. A turn that calls no
tool has exactly one step, so the mid-turn pull runs once at the start, before anyone could write more: the
message stays parked until the turn ends. That is exactly the case that generates the longest (the model
writes in one go), so the longest wait.

The real gap is elsewhere: the typing indicator switches itself off after 10 minutes while
``LLM_TURN_TIMEOUT_MS`` lets a turn run up to 15. Between those two marks there is complete silence, and it
has happened for real (log of 2026-08-04: "Typing ran too long - switching off", a minute later the turn
died). This sentence fills that gap.

Forced deviations:

* "how long has the thread been busy" comes from a ``ThreadBusy`` (in-process chain or Redis), so the check is
  ``await``-ed, and the send path is injected as ``send_in_parts`` because ``send_reply_in_parts`` belongs to
  package C2 (not in this worktree). The wiring passes C2's function.
* ``allowed`` (default True) is the clinic seam: the router passes False in ``patient_channel``. A canned text
  to a patient is still an outbound message that no human approved, and ``PolicyHooks.on_outbound`` has no
  origin for it; whether a fixed, doctor-approved reassurance template may go out automatically is a product
  decision (open item in the C1 report).
* Shared by both channels (C2 imports it).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from pema.channels.reply_target_tu_kenh import ReplyTarget
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.middleware.rate_limiter import dang_gui_tren
from pema.middleware.thread_run_chain import ThreadBusy
from pema.shared.logger import create_logger

_log = create_logger("busy-wait-notice")

CAU_TRAN_AN = (
    "Mình vẫn đang xử lý yêu cầu trước, hơi lâu một chút. "
    "Tin của bạn mình nhận rồi, xong mình trả lời ngay nhé."
)

_lan_tran_an_cuoi: dict[str, float] = {}
"""Last time each thread was reassured. Not repeated within the same wait: saying the same sentence twice only
makes people more impatient."""


class ReplyOutcome(Protocol):
    @property
    def sent_parts(self) -> int: ...


ReplySender = Callable[[ReplyTarget, str], Awaitable[ReplyOutcome]]
"""``send_reply_in_parts(target, text)`` of package C2."""

MucTieuTranAn = ReplyTarget
"""Exactly the part of ``ReplyTarget`` the sentence needs (no ``quote``: it answers no message). Today
``mang_dinh_dang`` is a dead field on this path: ``send_in_parts`` is called without ``styles``, and the gate
that drops styles is ``if mang_dinh_dang is False``, so there is nothing to drop. It stays because the shape
must match ``ReplyTarget``; do not read its presence as proof that this path guards the flag."""


async def maybe_notify_busy_wait(
    muc: MucTieuTranAn,
    *,
    busy: ThreadBusy,
    send_in_parts: ReplySender,
    allowed: bool = True,
) -> bool:
    """Send the reassurance if it is worth sending. Returns ``True`` when it was sent.

    Fire-and-forget at the call site: this is a side job and must not slow or block the intake path."""
    if not allowed:
        return False

    nguong = get_tuning_int("BUSY_ACK_AFTER_MS")
    if nguong <= 0:
        return False

    da_cho = await busy.busy_for_ms(muc.thread_key)
    if da_cho is None or da_cho < nguong:
        return False

    # Stay QUIET while the thread has messages going out. ``send_reply_in_parts`` queues the parts one by one,
    # so between two parts the queue is empty and this sentence could slip into the middle of a reply being
    # split; its content ("still working") would then be false because the bot is SENDING, not working. Same
    # gap as the 60-135 s between the "drawing the image" message and the real image of ``create_image``.
    if dang_gui_tren(muc.thread_key):
        _log.debug("Thread đang có tin đi ra - hoãn câu trấn an", thread_id=muc.thread_id)
        return False

    # The same threshold doubles as the quiet period: waiting that much more is worth a second sentence. One
    # constant, one meaning, nothing to keep in step.
    lan_cuoi = _lan_tran_an_cuoi.get(muc.thread_key, 0.0)
    bay_gio = time.time() * 1000
    if bay_gio - lan_cuoi < nguong:
        return False

    # Mark BEFORE sending: sending is async, and two messages arriving close together could both pass the
    # gates above and both send.
    _lan_tran_an_cuoi[muc.thread_key] = bay_gio

    _log.info("Bắt chờ quá lâu - nhắn một câu trấn an", thread_id=muc.thread_id, waited_ms=da_cho)
    ket = await send_in_parts(muc, CAU_TRAN_AN)
    return ket.sent_parts > 0


def reset_tran_an() -> None:
    """Clear the quiet-period memory; for tests only."""
    _lan_tran_an_cuoi.clear()
