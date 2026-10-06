"""The senders of the delivery chain (package O, step O3). New module, no zalo-agent original.

* ``InAppProvider``: the notice is already in the outbox (``GET /me/notifications`` reads it); this step only
  tells the open screens to reload, through ``emit_live`` (a live event with the notice id and nothing else);
* ``PushProvider`` (Protocol) with ``FakePushProvider`` for tests and ``FcmApnsPushProvider``, a DISABLED
  skeleton: it refuses to start without credentials and, in this step, even with them (there is no KMP client
  to receive a push yet), so a production wiring cannot believe a push was sent;
* ``ZaloBellProvider``: the operator's personal Zalo, through the internal account, to the id they linked;
* ``TeamGroupProvider``: the configured team group, through the same internal account;
* ``OnCallBellProvider``: the 24/7 contact of package M, through the same internal account.

Every ``send`` answers a ``StepResult`` and does not raise: a refusal or a transport error is a result with a
short code. The text of a notice is composed in ``pema.notify.text`` from the PII-free payload.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pema.care.oncall import pick_on_call
from pema.care.routing_types import OnCallRow
from pema.clinic.actions.notification_chain import NotifyTarget, PushTarget
from pema.live import emit_live
from pema.notify.text import PushMessage, UnsafeTextError, render_chat_text, render_push
from pema.notify.types import (
    ERR_DISABLED,
    ERR_EXCEPTION,
    ERR_GROUP_UNSET,
    ERR_NO_ON_CALL,
    ERR_NO_TOKEN,
    ERR_NO_ZALO_LINK,
    ERR_PROVIDER_DISABLED,
    ERR_UNSAFE_TEXT,
    InternalSender,
    InternalTarget,
    InternalTargetKind,
    StepResult,
)
from pema.shared.logger import create_logger
from pema_contracts.live import LiveEventType
from pema_contracts.ops import NotifySettingsOut

log = create_logger("notify.providers")

type EmitLive = Callable[[LiveEventType, UUID | None], None]


# ------------------------------------------------------------------------------------------- in-app
class InAppProvider:
    def __init__(self, emit: EmitLive = emit_live) -> None:
        self._emit = emit

    async def send(self, notice_id: UUID) -> StepResult:
        try:
            self._emit(LiveEventType.NOTIFICATIONS_CHANGED, notice_id)
        except Exception as err:
            log.error("in-app live event failed", err=err)
            return StepResult.failed(ERR_EXCEPTION)
        return StepResult.sent()


# --------------------------------------------------------------------------------------------- push
class PushCredentialsMissingError(RuntimeError):
    """FCM / APNs credentials are not configured: the real provider does not start."""


class PushNotImplementedError(RuntimeError):
    """The provider skeleton has no transport yet (the KMP push client is a later step)."""


@dataclass(frozen=True)
class PushResult:
    sent: int
    """Devices the provider accepted the message for."""
    dead_token_ids: tuple[UUID, ...] = ()
    """Tokens the provider reported as unregistered: the consumer forgets them."""
    error_code: str | None = None


@runtime_checkable
class PushProvider(Protocol):
    @property
    def enabled(self) -> bool:
        """``False``: the chain skips the push step and logs why."""
        ...

    async def send(self, tokens: Sequence[PushTarget], message: PushMessage) -> PushResult: ...


@dataclass
class FakePushProvider:
    """Records every push; ``fail_code`` makes it refuse, ``dead`` names tokens it reports as unregistered."""

    enabled: bool = True
    fail_code: str | None = None
    dead: frozenset[UUID] = frozenset()
    sent: list[tuple[tuple[UUID, ...], PushMessage]] = field(
        default_factory=list[tuple[tuple[UUID, ...], PushMessage]]
    )

    async def send(self, tokens: Sequence[PushTarget], message: PushMessage) -> PushResult:
        if self.fail_code is not None:
            return PushResult(sent=0, error_code=self.fail_code)
        live = [token for token in tokens if token.id not in self.dead]
        self.sent.append((tuple(token.id for token in live), message))
        return PushResult(
            sent=len(live), dead_token_ids=tuple(token.id for token in tokens if token.id in self.dead)
        )


@dataclass(frozen=True)
class PushCredentials:
    """What FCM (Android, web) and APNs (iOS) need. Read from the secret store by the wiring; never logged."""

    fcm_project_id: str
    fcm_service_account_json: str
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_key_pem: str | None = None


class FcmApnsPushProvider:
    """Skeleton of the real provider. ``start`` raises ``PushCredentialsMissingError`` without credentials and
    ``PushNotImplementedError`` with them; ``enabled`` is ``False`` until a later step writes the
    transport."""

    def __init__(self, credentials: PushCredentials | None = None) -> None:
        self._credentials = credentials

    @property
    def enabled(self) -> bool:
        return False

    def start(self) -> None:
        creds = self._credentials
        if creds is None or not creds.fcm_project_id or not creds.fcm_service_account_json:
            raise PushCredentialsMissingError("FCM/APNs credentials are not configured")
        raise PushNotImplementedError("the push transport is not written yet (KMP client is a later step)")

    async def send(self, tokens: Sequence[PushTarget], message: PushMessage) -> PushResult:
        return PushResult(sent=0, error_code=ERR_PROVIDER_DISABLED)


def _push_step(result: PushResult) -> StepResult:
    if result.error_code is not None:
        return StepResult.failed(result.error_code)
    if result.sent == 0:
        return StepResult.skipped(ERR_NO_TOKEN)
    return StepResult.sent()


async def send_push(
    provider: PushProvider | None, target: NotifyTarget, payload: Mapping[str, Any]
) -> tuple[StepResult, PushResult | None]:
    """The push step of one notice: skipped without a provider, with it switched off, or without a token."""
    if provider is None or not provider.enabled:
        return StepResult.skipped(ERR_PROVIDER_DISABLED), None
    if not target.push_tokens:
        return StepResult.skipped(ERR_NO_TOKEN), None
    try:
        message = render_push(payload)
    except UnsafeTextError:
        return StepResult.failed(ERR_UNSAFE_TEXT), None
    try:
        result = await provider.send(target.push_tokens, message)
    except Exception as err:
        log.error("push provider failed", err=err)
        return StepResult.failed(ERR_EXCEPTION, retryable=True), None
    return _push_step(result), result


# ------------------------------------------------------------------- the personal Zalo and the group
async def _send_chat(
    sender: InternalSender, target: InternalTarget, payload: Mapping[str, Any], settings: NotifySettingsOut
) -> StepResult:
    try:
        text = render_chat_text(payload, settings.public_base_url)
    except UnsafeTextError:
        return StepResult.failed(ERR_UNSAFE_TEXT)
    try:
        return await sender.send(target, text)
    except Exception as err:
        log.error("internal sender failed", err=err)
        return StepResult.failed(ERR_EXCEPTION, retryable=True)


class ZaloBellProvider:
    """The notification bell: the operator's personal Zalo, written by the internal account."""

    def __init__(self, sender: InternalSender) -> None:
        self._sender = sender

    async def send(
        self, payload: Mapping[str, Any], target: NotifyTarget, settings: NotifySettingsOut
    ) -> StepResult:
        if not settings.bell_enabled:
            return StepResult.skipped(ERR_DISABLED)
        if not target.zalo_user_id:
            return StepResult.skipped(ERR_NO_ZALO_LINK)
        return await _send_chat(
            self._sender, InternalTarget(InternalTargetKind.STAFF, target.zalo_user_id), payload, settings
        )


class TeamGroupProvider:
    """The team group, posted once per notice."""

    def __init__(self, sender: InternalSender) -> None:
        self._sender = sender

    async def send(self, payload: Mapping[str, Any], settings: NotifySettingsOut) -> StepResult:
        if not settings.group_enabled:
            return StepResult.skipped(ERR_DISABLED)
        if not settings.team_group_id:
            return StepResult.skipped(ERR_GROUP_UNSET)
        return await _send_chat(
            self._sender, InternalTarget(InternalTargetKind.GROUP, settings.team_group_id), payload, settings
        )


class OnCallBellProvider:
    """The 24/7 contact: the number is chosen from the rows at the moment of sending (package M's rule: it is
    read again whenever it is used) and is never stored with the notice."""

    def __init__(self, sender: InternalSender) -> None:
        self._sender = sender

    async def send(
        self,
        payload: Mapping[str, Any],
        rows: Sequence[OnCallRow],
        settings: NotifySettingsOut,
        now: datetime,
    ) -> StepResult:
        row = pick_on_call(rows, now)
        if row is None:
            return StepResult.failed(ERR_NO_ON_CALL, retryable=True)
        return await _send_chat(
            self._sender, InternalTarget(InternalTargetKind.ON_CALL, row.zalo_number), payload, settings
        )
