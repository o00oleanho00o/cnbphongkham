"""Vocabulary and seams of ``pema.notify`` (package O, step O3). New module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pema.care.routing_types import OnCallRow
from pema.clinic.actions.notification_chain import NotifyTarget
from pema.clinic.actions.notifications import OutboxNotification
from pema.clinic.actions.sla_checks import DueCheck
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationState,
    NotifySettingsOut,
)

# Codes of ``StepResult.error_code``: short, no text, no recipient.
ERR_DISABLED = "disabled"
ERR_NO_ZALO_LINK = "no_zalo_link"
ERR_NO_TOKEN = "no_token"  # noqa: S105  - an error code, not a password
ERR_PROVIDER_DISABLED = "provider_disabled"
ERR_GROUP_UNSET = "group_unset"
ERR_QUIET_HOURS = "quiet_hours"
ERR_NO_INTERNAL_ACCOUNT = "no_internal_account"
ERR_NOT_INTERNAL = "account_not_internal"
ERR_ACCOUNT_NOT_RUNNING = "account_not_running"
ERR_CUSTOMER_RECIPIENT = "customer_recipient"
ERR_UNSAFE_TEXT = "unsafe_text"
ERR_NO_ON_CALL = "no_on_call"
ERR_SEND_REJECTED = "send_rejected"
ERR_EXCEPTION = "exception"


@dataclass(frozen=True)
class StepResult:
    """What one provider did for one notice. ``error_code`` is a short code, never text."""

    status: NotificationLogStatus
    error_code: str | None = None
    retryable: bool = False
    """Only for ``failed``: a later attempt may work (a transport error), as opposed to a refusal by a
    guard."""

    @staticmethod
    def sent() -> StepResult:
        return StepResult(NotificationLogStatus.SENT)

    @staticmethod
    def skipped(code: str) -> StepResult:
        return StepResult(NotificationLogStatus.SKIPPED, code)

    @staticmethod
    def failed(code: str, *, retryable: bool = False) -> StepResult:
        return StepResult(NotificationLogStatus.FAILED, code, retryable)


class InternalTargetKind(StrEnum):
    STAFF = "staff"
    """The personal Zalo id of an operator who linked it."""
    GROUP = "group"
    """The team group."""
    ON_CALL = "on_call"
    """The 24/7 contact of package M."""


@dataclass(frozen=True)
class InternalTarget:
    kind: InternalTargetKind
    ref: str
    """Zalo user id, group id or the on-call contact number; never logged."""


@runtime_checkable
class InternalSender(Protocol):
    """The one way to write through the internal Zalo account (``pema.notify.internal``)."""

    async def send(self, target: InternalTarget, text: str) -> StepResult: ...


class InternalDirectory(Protocol):
    """What the guards of the internal sender ask the clinic database."""

    async def internal_account_id(self) -> str | None: ...

    async def account_purpose(self, account_id: str) -> str | None: ...

    async def is_customer_thread(self, ref: str) -> bool: ...


class ChainStore(Protocol):
    """The bookkeeping of the consumer. ``SqlNotifyStore`` is the real one, ``InMemoryChainStore`` the
    fake."""

    async def claim_due(self, now: datetime, limit: int) -> list[OutboxNotification]: ...

    async def record_attempt(
        self,
        outbox_id: UUID,
        provider: NotificationProvider,
        *,
        attempt: int,
        status: NotificationLogStatus,
        latency_ms: int | None,
        error_code: str | None,
    ) -> None: ...

    async def settle(
        self,
        outbox_id: UUID,
        *,
        state: NotificationState,
        chain_step: str | None,
        next_attempt_at: datetime,
        attempts: int,
    ) -> None: ...

    async def is_acked(self, outbox_id: UUID) -> bool: ...

    async def load_settings(self) -> NotifySettingsOut: ...

    async def load_target(self, user_id: UUID) -> NotifyTarget: ...

    async def drop_push_token(self, token_id: UUID) -> None: ...

    async def list_on_call(self) -> Sequence[OnCallRow]: ...


class SlaStore(Protocol):
    async def schedule(self, *, request_id: UUID, idx: int, due_at: datetime, dedupe_key: str) -> None: ...

    async def claim_due(self, now: datetime, limit: int) -> list[DueCheck]: ...

    async def finish(self, check: DueCheck, *, ok: bool, now: datetime) -> bool: ...
