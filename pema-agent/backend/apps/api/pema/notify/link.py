"""Linking an operator's personal Zalo to the bell, and keeping the internal account out of the Inbox
(package O,
step O3). New module, no zalo-agent original.

The flow (decision 4 of the plan, the recipe's "bell linking"):

1. the operator calls ``POST /me/notify-zalo/link`` and gets a one-time code (8 characters, valid 10 minutes);
2. they send that code, as a message, from their personal Zalo to the clinic's internal account;
3. the inbound path of that account hands the message to ``LinkHandler.handle`` instead of the customer
   pipeline; a live code binds the sender's Zalo id (and the time of consent) to the operator's staff profile.

What the internal account never does (it is not a customer identity):

* it never creates a ``clinic.conversation`` and never starts an agent turn: ``InternalAccountRegistry`` is
  asked by the intake wiring, which answers "do not respond, do not record" for its messages and hands every
  message that reaches the Inbox writer to ``InternalInboxGuard`` first;
* it never answers an unknown sender: a message with no live code gets no reply at all (it may be a customer
  who found the number). Only a successful link is confirmed, to the Zalo id that was just bound to an
  operator.

A few wrong codes in a row from one sender silence that sender for a while (``MAX_FAILURES``): the code space
is ~40 bits and short-lived, this keeps it from being guessed through the chat.
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pema.clinic.actions.notification_chain import LinkOutcome
from pema.notify.types import InternalSender, InternalTarget, InternalTargetKind
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.channel import InboundMessage
from pema_contracts.clinic_actions import InboxRef

log = create_logger("notify.link")

LINKED_REPLY = "Đã liên kết Zalo cá nhân của bạn với Pema. Từ giờ bạn sẽ nhận thông báo ở đây."
MAX_FAILURES = 5
FAILURE_WINDOW_S = 600.0
PURPOSE_TTL_S = 15.0
NO_CONVERSATION = UUID(int=0)
CODE_LENGTH = 8

_TOKEN = re.compile(r"[A-Z0-9]+")


def extract_codes(text: str, *, limit: int = 3) -> list[str]:
    """Candidate codes in a message, upper case without separators: a token of 8 characters ("ABCD2345") or
    two tokens of 4 ("abcd-2345", "ABCD 2345"). Words around the code ("pema abcd-2345 nhé") are ignored."""
    tokens = _TOKEN.findall(text.upper())
    found: list[str] = []
    for index, token in enumerate(tokens):
        if len(token) == CODE_LENGTH:
            found.append(token)
        elif (
            len(token) == CODE_LENGTH // 2
            and index + 1 < len(tokens)
            and len(tokens[index + 1]) == len(token)
        ):
            found.append(token + tokens[index + 1])
    return found[:limit]


class LinkStore(Protocol):
    async def consume_link_code(self, code: str, zalo_user_id: str, at: datetime) -> LinkOutcome: ...


class LinkHandler:
    def __init__(
        self,
        store: LinkStore,
        sender: InternalSender | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._sender = sender
        self._clock = clock
        self._monotonic = monotonic
        self._failures: dict[str, list[float]] = {}

    def _recent_failures(self, sender_id: str) -> list[float]:
        horizon = self._monotonic() - FAILURE_WINDOW_S
        kept = [stamp for stamp in self._failures.get(sender_id, []) if stamp > horizon]
        self._failures[sender_id] = kept
        return kept

    async def handle(self, message: InboundMessage) -> bool:
        """Try to link the sender of ``message``. ``True`` when a code matched. Never raises for a bad
        code."""
        sender_id = message.sender_id
        if not sender_id or message.is_group:
            return False
        codes = extract_codes(message.text or "")
        if not codes:
            return False
        if len(self._recent_failures(sender_id)) >= MAX_FAILURES:
            log.warning("linking attempts from one sender are paused")
            return False
        for code in codes:
            outcome = await self._store.consume_link_code(code, sender_id, self._clock())
            if outcome.linked:
                log.info("personal zalo linked", user_id=str(outcome.user_id))
                await self._confirm(sender_id)
                return True
        self._failures.setdefault(sender_id, []).append(self._monotonic())  # one strike per message
        return False

    async def _confirm(self, sender_id: str) -> None:
        if self._sender is None:
            return
        try:
            await self._sender.send(InternalTarget(InternalTargetKind.STAFF, sender_id), LINKED_REPLY)
        except Exception as err:
            log.error("link confirmation failed", err=err)


MessageHandler = Callable[[UUID, InboundMessage], Awaitable[None]]
AccountIdLoader = Callable[[], Awaitable[frozenset[str]]]


class InternalAccountRegistry:
    """Which accounts are internal, as the last read of the database says (refreshed every ``ttl_s``).

    ``is_internal`` is synchronous on purpose: the intake wiring asks it from the (synchronous) respond
    decision. ``loader`` and ``handler`` are set by the composition: the loader reads ``agent.accounts``
    (both processes), the handler binds links and needs the clinic database (the API process only; without it
    the message of an internal account is dropped and logged)."""

    def __init__(
        self, *, ttl_s: float = PURPOSE_TTL_S, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self.loader: AccountIdLoader | None = None
        self.handler: MessageHandler | None = None
        self._ttl = ttl_s
        self._monotonic = monotonic
        self._ids: frozenset[str] = frozenset()
        self._loaded_at: float | None = None

    def is_internal(self, account_id: str) -> bool:
        return account_id in self._ids

    def set_ids(self, ids: frozenset[str]) -> None:
        self._ids = ids
        self._loaded_at = self._monotonic()

    async def refresh(self) -> None:
        if self.loader is None:
            return
        self.set_ids(await self.loader())

    async def ensure_fresh(self) -> None:
        if self.loader is None:
            return
        if self._loaded_at is None or self._monotonic() - self._loaded_at >= self._ttl:
            await self.refresh()

    async def handle(self, clinic_id: UUID, message: InboundMessage) -> None:
        if self.handler is None:
            log.warning("a message reached an internal account but no link handler is wired here")
            return
        try:
            await self.handler(clinic_id, message)
        except Exception as err:
            log.error("internal account message handler failed", err=err)


class InboxWriter(Protocol):
    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef: ...


class InternalInboxGuard:
    """Wraps the Inbox writer of the intake path. A message to an internal account never becomes a
    conversation: it goes to the registry's handler and the caller is told ``duplicate`` (nothing written, no
    turn). Every other message goes to the real writer unchanged."""

    def __init__(self, inner: InboxWriter, registry: InternalAccountRegistry) -> None:
        self._inner = inner
        self._registry = registry

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        await self._registry.ensure_fresh()
        if self._registry.is_internal(message.account_id):
            await self._registry.handle(ctx.clinic_id, message)
            return InboxRef(conversation_id=NO_CONVERSATION, duplicate=True)
        return await self._inner.record_inbound_message(ctx, message)
