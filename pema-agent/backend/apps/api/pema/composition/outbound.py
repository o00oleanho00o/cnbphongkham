"""``OutboundDelivery`` of B1 over the running channels and the shared send pipeline of C2 (package G).

A staff reply and an approved review item reach the patient through here. The Inbox conversation knows the
channel KIND and the thread id (``external_ref``) but has no account column, so the account is found through
the agent side: every inbound message writes an ``agent.threads`` row keyed by (account, thread id), and the
thread id of the conversation IS ``external_ref``. When a clinic runs several accounts of one kind, the reply
goes out through the account that RECEIVED the patient's messages (the one whose thread was active most
recently when two of them know the patient), never through "the first account by id". Only when no running
account has a thread row for this patient (a conversation created by hand, a thread row not written yet) does
it fall back to the first ENABLED, RUNNING account of that kind by id, and it logs that.

The text was approved by a person, so the policy hook ``on_outbound`` is not asked again; what still
applies is what the channel itself enforces: the kill switch, the cap and the send window (``proactive``
selects the guarded path), and the per-thread queue with its human-like gap.

Package O, step O4: the clinic action now tells this delivery the identity (``request.account_id``, resolved
from ``conversation.account_id`` or the channel's single customer account), so the reply goes out through that
account and no other. Through ``IdentitySendQueue`` the message is first admitted (an ``internal`` identity,
a disabled one and a channel whose kill switch is on are refused; a proactive message reserves one slot of the
identity's daily cap) and every part then waits the one gap that the agent and all operators share. The
adapter's message id of the first part is returned in the ``SendResult`` (``external_message_id``). The
search by kind and thread below stays for a request without ``account_id``.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pema.channels.identity_send_queue import (
    IdentitySendQueue,
    RedisSendSlotBackend,
    install_identity_send_queue,
    installed_identity_send_queue,
)
from pema.channels.send_reply_in_parts import (
    ChannelSendRejectedError,
    reply_target_from_channel,
    send_reply_in_parts,
)
from pema.clinic.actions.identities import identity_for_send
from pema.clinic.actions.outbound import OutboundRequest
from pema.core.db import ClinicDatabase
from pema.scheduler.proactive_send_counter_store import ProactiveSendCounterStore
from pema.scheduler.proactive_send_guard import PgProactiveSendGuard
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.channel import ChannelPort, ChannelRegistry, SendResult, SendStatus, ThreadKind
from pema_contracts.conversation import ThreadRow
from pema_contracts.errors import ErrorCode
from pema_contracts.installation import installation_clinic_id
from pema_contracts.scheduler import ProactiveSlotResult

log = create_logger("composition.outbound")


class ThreadLookup(Protocol):
    """The part of the thread store this class needs (``PostgresConversationStore.get_thread``)."""

    async def get_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadRow | None: ...


class RegistryOutboundDelivery:
    requires_identity = True
    """The clinic action resolves the identity (``no_identity``, internal guard) before ``deliver``."""

    def __init__(
        self,
        accounts: AccountStore,
        registry: ChannelRegistry,
        threads: ThreadLookup | None = None,
        identity_queue: IdentitySendQueue | None = None,
    ) -> None:
        self._accounts = accounts
        self._registry = registry
        self._threads = threads
        self._queue = identity_queue

    async def _running_candidates(self, request: OutboundRequest) -> list[tuple[AccountConfig, ChannelPort]]:
        found: list[tuple[AccountConfig, ChannelPort]] = []
        for config in sorted(await self._accounts.list_accounts(request.clinic_id), key=lambda c: c.id):
            if config.channel is not request.channel or not config.enabled:
                continue
            if self._queue is not None and not await self._queue.is_customer_facing(config.id):
                continue  # an internal notifier is never a way to reach a customer
            channel = self._registry.get_running(request.clinic_id, config.id)
            if channel is not None:
                found.append((config, channel))
        return found

    async def _identity_channel(
        self, request: OutboundRequest, account_id: str
    ) -> tuple[AccountConfig, ChannelPort] | None:
        """The running channel of exactly this account: the identity of the thread, not "an account of the
        same kind"."""
        for config in await self._accounts.list_accounts(request.clinic_id):
            if config.id == account_id and config.channel is request.channel and config.enabled:
                channel = self._registry.get_running(request.clinic_id, config.id)
                return None if channel is None else (config, channel)
        return None

    async def _running_channel(self, request: OutboundRequest) -> tuple[AccountConfig, ChannelPort] | None:
        if request.account_id is not None:
            return await self._identity_channel(request, request.account_id)
        candidates = await self._running_candidates(request)
        if len(candidates) <= 1 or self._threads is None:
            return candidates[0] if candidates else None
        # Several accounts of one kind are running: the one that received this patient's messages.
        latest: tuple[AccountConfig, ChannelPort] | None = None
        latest_at = None
        for config, channel in candidates:
            thread = await self._threads.get_thread(request.clinic_id, config.id, request.external_ref)
            if thread is None:
                continue
            at = thread.last_message_at
            if latest is None or (at is not None and (latest_at is None or at > latest_at)):
                latest, latest_at = (config, channel), at
        if latest is not None:
            return latest
        log.warning(
            "no running account has a thread for this conversation; using the first by id",
            channel=request.channel.value,
            candidates=len(candidates),
        )
        return candidates[0]

    async def deliver(self, ctx: ActionContext, request: OutboundRequest) -> SendResult:
        found = await self._running_channel(request)
        if found is None:
            log.warning("no running account for the channel", channel=request.channel.value)
            return SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE)
        config, channel = found
        admission = None
        if self._queue is not None:
            admission = await self._queue.admit(config.id, proactive=request.proactive)
            if admission.rejection is not None:
                return admission.rejection
        target = reply_target_from_channel(
            channel,
            request.external_ref,
            ThreadKind.USER,
            f"{config.id}:{request.external_ref}",
            proactive=request.proactive,
            identity_queue=self._queue,
        )
        sent = await send_reply_in_parts(target, request.text)
        left = sent.error is None and sent.sent_parts > 0
        if admission is not None and self._queue is not None:
            await self._queue.settle(admission, sent=sent.sent_parts > 0)
        if left:
            first_id = sent.external_message_ids[0] if sent.external_message_ids else None
            return SendResult(status=SendStatus.SENT, external_message_id=first_id)
        error = sent.error
        if isinstance(error, ChannelSendRejectedError):
            return SendResult(status=SendStatus.REJECTED, error_code=error.error_code, detail=error.detail)
        log.warning("outbound send failed", err=error, account_id=config.id)
        return SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE)


def build_identity_send_queue(db: ClinicDatabase, redis_client: Any) -> IdentitySendQueue:
    """The one send queue of the process (O4): limits and kill switch read from the database on every send,
    the lock and the last-send time in Redis (shared by the API and the agent worker), the daily cap of a
    proactive message in the same Postgres counter as the scheduler's, under its own ``identity:`` key. The
    installation clinic id is read lazily: it is loaded after the wiring."""
    return IdentitySendQueue(
        clinic_id=installation_clinic_id,
        lookup=lambda account_id: identity_for_send(db, installation_clinic_id(), account_id),
        backend=RedisSendSlotBackend(redis_client),
        counter=_LazyCounter(db),
    )


class _LazyCounter:
    """``ProactiveSendGuard`` bound to the installation clinic once it is loaded."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._counters = ProactiveSendCounterStore(db)

    def _guard(self) -> PgProactiveSendGuard:
        return PgProactiveSendGuard(self._counters, installation_clinic_id())

    async def reserve_slot(self, scope_key: str, day_key: str, max_per_day: int) -> ProactiveSlotResult:
        return await self._guard().reserve_slot(scope_key, day_key, max_per_day)

    async def refund_slot(self, scope_key: str, day_key: str) -> None:
        await self._guard().refund_slot(scope_key, day_key)

    async def reserve_cap_notice(self, scope_key: str, day_key: str) -> bool:
        return await self._guard().reserve_cap_notice(scope_key, day_key)

    async def revert_cap_notice(self, scope_key: str, day_key: str) -> None:
        await self._guard().revert_cap_notice(scope_key, day_key)


def install_identity_queue(db: ClinicDatabase, redis_client: Any) -> IdentitySendQueue:
    """Build the queue and install it for ``reply_target_from_channel`` (the agent's reply path and the
    scheduler use it without knowing). Called by both processes, the API and the agent worker, and by each of
    their stacks: the first call builds it, later calls return the same queue (one in-process lock)."""
    existing = installed_identity_send_queue()
    if existing is not None:
        return existing
    queue = build_identity_send_queue(db, redis_client)
    install_identity_send_queue(queue)
    return queue
