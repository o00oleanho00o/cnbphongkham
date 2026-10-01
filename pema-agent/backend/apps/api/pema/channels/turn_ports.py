"""Seams of the shared turn pipeline (``message_turn_processor``, ``deliver_chat_reply``) to other packages.

New module. The original called sibling modules directly (``media-store.ts``, ``thread-summarizer.ts``,
``message-batcher.ts``); in the Pema monorepo those belong to packages that do not exist in the worktree
of C2, so
the pipeline reaches them through the small Protocols below. Package G wires the real objects; everything the
package needs from ``pema_contracts`` (``AgentEngine``, ``HistoryStore``, ``UsageStore``, ``PendingInbox``,
``PolicyHooks``, ``AgentFacingClinicActions`` ...) is imported from there directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from pema_contracts.channel import InboundMessage
from pema_contracts.policy import OutboundOrigin


class ImagePersister(Protocol):
    """``persistBatchImages`` (package D2 ``media_store``): downloads the images of the messages and stamps
    ``InboundImage.local_path``. Never raises."""

    async def __call__(self, clinic_id: UUID, account_id: str, messages: list[InboundMessage]) -> None: ...


class ThreadSummarizer(Protocol):
    """``maybeSummarizeThread`` (package D2 ``thread_summarizer``): fold old messages into the rolling
    summary.
    Swallows its own errors."""

    async def __call__(self, clinic_id: UUID, account_id: str, thread_id: str) -> None: ...


@runtime_checkable
class SenderAwarePendingInbox(Protocol):
    """``layTinDangDo(threadKey, senderId)``: the original takes the waiting messages of ONE sender,
    because the
    batcher keys its queues by ``(thread, sender)`` and a turn must never steal another person's message (that
    person has a turn of their own). ``pema_contracts.PendingInbox.take_injected`` has no sender argument; a
    batcher that implements this method is used in preference. Without it a direct chat (one possible sender)
    falls back to ``take_injected`` and a group injects nothing."""

    async def take_injected_for_sender(
        self, account_id: str, thread_id: str, sender_id: str
    ) -> list[InboundMessage]: ...


class HoldForReview(Protocol):
    """Creates the ``review_item`` that holds an outbound text for a human (``patient_channel``). Returns the
    review item id as text, or ``None`` when it could not be created (the text is then NOT sent)."""

    async def __call__(
        self,
        text: str,
        *,
        origin: OutboundOrigin,
        extra: dict[str, object] | None = None,
    ) -> str | None: ...


type FailureNotifier = Callable[[str | None], Awaitable[None]]
"""``notifyTechnicalError(target, loaiLoi)`` bound to the turn: sends the canned apology through the
policy gate
(sent directly in ``staff_assistant``, held as a draft in ``patient_channel``)."""
