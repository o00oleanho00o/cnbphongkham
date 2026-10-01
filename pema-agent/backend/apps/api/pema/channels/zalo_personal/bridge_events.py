"""Events POSTed by the Node bridge to ``/webhooks/zalo-bridge/{clinic_slug}/{account_id}`` (already
authenticated).

New module: in zalo-agent ``zalo-listener.ts`` called the handlers in-process (``routeIncomingMessage``,
``handleFriendEvent``); with the bridge those calls arrive as signed HTTP events and this class
dispatches them.

| event | what happens |
|---|---|
| ``message`` | dedupe on the Zalo ``msgId`` (``agent.channel_update_seen``), then
``route_incoming_message`` |
| ``friend_event`` | ``handle_friend_event`` (pending friend requests) |
| ``credential_updated`` | the credential is stored ENCRYPTED through ``CredentialVault`` (never in
clear, never logged) |
| ``account_state`` | ``connected`` / ``disconnected`` update the bridge state; ``blocked``,
``logged_out`` and ``session_dead`` |
| | engage the KILL SWITCH (reason ``bridge_blocked`` ...), drop the channel from this process and notify
the |
| | ``ChannelBlockedListener`` s: every proactive send is then rejected with ``channel_kill_switch_on``,
which is the |
| | signal that moves the scheduled jobs of the account to manual sending |

A reconnect NEVER turns the kill switch off by itself: a person decides when sending resumes.

Logging: ids, event types and codes only. The payload of a ``message`` event carries personal content and the
``credential_updated`` one carries a secret: neither is ever logged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import text

from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.bridge_client import KillSwitchState
from pema.channels.zalo_personal.channel_settings import (
    AUTO_KILL_REASON_BLOCKED,
    AUTO_KILL_REASON_LOGGED_OUT,
    AUTO_KILL_REASON_SESSION_DEAD,
    ChannelSettingsRepository,
)
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.friend_event_handler import handle_friend_event
from pema.channels.zalo_personal.friend_request_store import FriendRequestPort
from pema.channels.zalo_personal.incoming_message_router import RouterDeps, route_incoming_message
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.admin import BridgeState
from pema_contracts.channel import ChannelKind
from pema_contracts.common import JsonObject
from pema_contracts.conversations import WebhookAck
from pema_contracts.errors import DomainError
from pema_contracts.roles import ActorType

log = create_logger("bridge-events")


class UpdateDedupe(Protocol):
    async def first_time(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        """``True`` exactly once per ``(account, update_id)``."""
        ...


class SqlUpdateDedupe:
    """``agent.channel_update_seen`` (PK clinic, account, update_id): ``INSERT ... ON CONFLICT DO
    NOTHING``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def first_time(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                text(
                    "INSERT INTO agent.channel_update_seen (clinic_id, account_id, update_id) "
                    "VALUES (:clinic_id, :account_id, :update_id) ON CONFLICT DO NOTHING"
                ),
                {"clinic_id": clinic_id, "account_id": account_id, "update_id": update_id},
            )
            return result.rowcount == 1  # type: ignore[attr-defined]


class ChannelBlockedListener(Protocol):
    """Told when the account is blocked or logged out. Package G wires the scheduler (S) here so its jobs
    move to
    the manual-send state; the kill switch already makes every proactive send fail with a recognisable
    code."""

    async def on_channel_blocked(self, clinic_id: UUID, account_id: str, state: str) -> None: ...


@dataclass(frozen=True)
class _StatePlan:
    bridge_state: BridgeState
    kill_reason: str | None
    drop_channel: bool


_STATE_PLANS: dict[str, _StatePlan] = {
    "connected": _StatePlan(BridgeState.CONNECTED, None, False),
    "disconnected": _StatePlan(BridgeState.DOWN, None, False),
    "blocked": _StatePlan(BridgeState.BLOCKED, AUTO_KILL_REASON_BLOCKED, True),
    "logged_out": _StatePlan(BridgeState.AWAITING_QR, AUTO_KILL_REASON_LOGGED_OUT, True),
    "session_dead": _StatePlan(BridgeState.AWAITING_QR, AUTO_KILL_REASON_SESSION_DEAD, True),
}


class BridgeEventHandler:
    def __init__(
        self,
        *,
        manager: AccountManager,
        router_deps: RouterDeps,
        vault: CredentialVault,
        friends: FriendRequestPort,
        settings: ChannelSettingsRepository,
        dedupe: UpdateDedupe,
        listeners: Sequence[ChannelBlockedListener] = (),
    ) -> None:
        self._manager = manager
        self._router_deps = router_deps
        self._vault = vault
        self._friends = friends
        self._settings = settings
        self._dedupe = dedupe
        self._listeners = tuple(listeners)

    async def handle(self, clinic_id: UUID, account_id: str, payload: Mapping[str, object]) -> WebhookAck:
        event_type = payload.get("type")
        if event_type == "message":
            return await self._message(clinic_id, account_id, payload)
        if event_type == "friend_event":
            await self._friend_event(clinic_id, account_id, payload)
        elif event_type == "credential_updated":
            await self._credential_updated(clinic_id, account_id, payload)
        elif event_type == "account_state":
            await self._account_state(clinic_id, account_id, payload)
        else:
            log.debug("unknown bridge event ignored", account_id=account_id, event_type=str(event_type))
        return WebhookAck()

    # ------------------------------------------------------------------------------------------ events

    async def _message(self, clinic_id: UUID, account_id: str, payload: Mapping[str, object]) -> WebhookAck:
        channel = await self._channel_for(clinic_id, account_id)
        if channel is None:
            # Account disabled, deleted or not startable: do not process, but ack so the bridge stops
            # retrying.
            log.warning("message for an account that is not running - dropped", account_id=account_id)
            return WebhookAck()
        parsed = channel.parse_inbound(payload)
        if parsed is not None and not await self._dedupe.first_time(clinic_id, account_id, parsed.update_id):
            return WebhookAck(duplicate=True)
        message = payload.get("message")
        if not isinstance(message, Mapping):
            return WebhookAck()
        self_id = payload.get("self_id")
        await route_incoming_message(
            self._router_deps,
            clinic_id,
            channel,
            message,  # pyright: ignore[reportUnknownArgumentType]
            self_id=self_id if isinstance(self_id, str) and self_id else None,
        )
        return WebhookAck()

    async def _friend_event(self, clinic_id: UUID, account_id: str, payload: Mapping[str, object]) -> None:
        channel = await self._channel_for(clinic_id, account_id)
        event = payload.get("event")
        if channel is None or not isinstance(event, Mapping):
            return
        await handle_friend_event(
            clinic_id,
            account_id,
            channel.api,
            event,  # pyright: ignore[reportUnknownArgumentType]
            self._friends,
        )

    async def _credential_updated(
        self, clinic_id: UUID, account_id: str, payload: Mapping[str, object]
    ) -> None:
        credential = payload.get("credential")
        if not isinstance(credential, dict) or not credential:
            log.warning("credential_updated without a credential", account_id=account_id)
            return
        typed: JsonObject = dict(credential)  # pyright: ignore[reportUnknownArgumentType]
        await self._vault.save_credentials(clinic_id, account_id, typed)
        log.info("Đã lưu credentials (mã hóa) cho các lần đăng nhập sau", account_id=account_id)

    async def _account_state(self, clinic_id: UUID, account_id: str, payload: Mapping[str, object]) -> None:
        state = str(payload.get("state", ""))
        plan = _STATE_PLANS.get(state)
        if plan is None:
            log.debug("unknown account state ignored", account_id=account_id, state=state)
            return
        ctx = ActionContext(clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.WEBHOOK)
        await self._settings.apply_bridge_report(
            ctx,
            ChannelKind.ZALO_PERSONAL,
            bridge_state=plan.bridge_state,
            kill_switch_reason=plan.kill_reason,
        )
        if plan.kill_reason:
            log.warning("bridge reported an account state", account_id=account_id, state=state)
        else:
            log.info("bridge reported an account state", account_id=account_id, state=state)
        if plan.drop_channel:
            self._manager.forget_without_bridge(clinic_id, account_id)
            try:
                await self._manager.push_kill_switch(
                    KillSwitchState(on=True, scope="proactive", reason=plan.kill_reason)
                )
            except Exception as err:
                # The row is already updated (every process reads it on the next send); the bridge also
                # keeps its
                # own breaker. Failing to push must not lose the report.
                log.warning("could not push the kill switch to the bridge", err=err)
            for listener in self._listeners:
                try:
                    await listener.on_channel_blocked(clinic_id, account_id, state)
                except Exception as err:
                    log.error("channel-blocked listener failed", account_id=account_id, err=err)

    # ---------------------------------------------------------------------------------------- helpers

    async def _channel_for(self, clinic_id: UUID, account_id: str) -> ZaloPersonalChannel | None:
        running = self._manager.get_running_account_kenh(clinic_id, account_id)
        if running is not None:
            return running
        try:
            await self._manager.start_account(clinic_id, account_id)
        except DomainError as err:
            log.debug("cannot attach the account for an event", account_id=account_id, code=err.code.value)
            return None
        return self._manager.get_running_account_kenh(clinic_id, account_id)
