"""``OutboundDelivery`` of B1 over the running channels and the shared send pipeline of C2 (package G).

A staff reply and an approved review item reach the patient through here. The Inbox conversation knows the
channel KIND and the thread id (``external_ref``) but not which Zalo account serves it, so the account is the
first ENABLED account of that kind in the clinic that is RUNNING in this process (several accounts of one kind
in one clinic: the first by id, open item in the report).

The text was approved by a person, so the policy hook ``on_outbound`` is not asked again; what still
applies is what the channel itself enforces: the kill switch, the cap and the send window (``proactive``
selects the guarded path), and the per-thread queue with its human-like gap.
"""

from __future__ import annotations

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
from pema_contracts.errors import ErrorCode

log = create_logger("composition.outbound")


class RegistryOutboundDelivery:
    def __init__(self, accounts: AccountStore, registry: ChannelRegistry) -> None:
        self._accounts = accounts
        self._registry = registry

    async def _running_channel(self, request: OutboundRequest) -> tuple[AccountConfig, ChannelPort] | None:
        for config in sorted(await self._accounts.list_accounts(request.clinic_id), key=lambda c: c.id):
            if config.channel is not request.channel or not config.enabled:
                continue
            channel = self._registry.get_running(request.clinic_id, config.id)
            if channel is not None:
                return config, channel
        return None

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
