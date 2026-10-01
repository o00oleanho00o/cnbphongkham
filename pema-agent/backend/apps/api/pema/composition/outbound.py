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
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pema.channels.send_reply_in_parts import (
    ChannelSendRejectedError,
    reply_target_from_channel,
    send_reply_in_parts,
)
from pema.clinic.actions.outbound import OutboundRequest
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.channel import ChannelPort, ChannelRegistry, SendResult, SendStatus, ThreadKind
from pema_contracts.conversation import ThreadRow
from pema_contracts.errors import ErrorCode

log = create_logger("composition.outbound")


class ThreadLookup(Protocol):
    """The part of the thread store this class needs (``PostgresConversationStore.get_thread``)."""

    async def get_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadRow | None: ...


class RegistryOutboundDelivery:
    def __init__(
        self, accounts: AccountStore, registry: ChannelRegistry, threads: ThreadLookup | None = None
    ) -> None:
        self._accounts = accounts
        self._registry = registry
        self._threads = threads

    async def _running_candidates(self, request: OutboundRequest) -> list[tuple[AccountConfig, ChannelPort]]:
        found: list[tuple[AccountConfig, ChannelPort]] = []
        for config in sorted(await self._accounts.list_accounts(request.clinic_id), key=lambda c: c.id):
            if config.channel is not request.channel or not config.enabled:
                continue
            channel = self._registry.get_running(request.clinic_id, config.id)
            if channel is not None:
                found.append((config, channel))
        return found

    async def _running_channel(self, request: OutboundRequest) -> tuple[AccountConfig, ChannelPort] | None:
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
        target = reply_target_from_channel(
            channel,
            request.external_ref,
            ThreadKind.USER,
            f"{config.id}:{request.external_ref}",
            proactive=request.proactive,
        )
        sent = await send_reply_in_parts(target, request.text)
        if sent.error is None and sent.sent_parts > 0:
            return SendResult(status=SendStatus.SENT)
        error = sent.error
        if isinstance(error, ChannelSendRejectedError):
            return SendResult(status=SendStatus.REJECTED, error_code=error.error_code, detail=error.detail)
        log.warning("outbound send failed", err=error, account_id=config.id)
        return SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE)
