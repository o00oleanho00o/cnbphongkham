"""The SQL-backed stores of ``pema.notify`` (package O, step O3). New module.

Thin classes over ``pema.clinic.actions`` (``notification_chain``, ``sla_checks``): the SQL lives there, this
package only holds the clinic id and the database. They run in the process that owns the ``be_app`` role (the
API process), like the CRM rule runner.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pema.care.routing_types import OnCallRow
from pema.clinic.actions import notification_chain as chain
from pema.clinic.actions import sla_checks
from pema.clinic.actions.notification_chain import LinkOutcome, NotifyTarget
from pema.clinic.actions.notifications import OutboxNotification
from pema.clinic.actions.sla_checks import DueCheck
from pema.core.db import ClinicDatabase
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationState,
    NotifySettingsOut,
)


class SqlNotifyStore:
    """``ChainStore`` and ``InternalDirectory`` of one clinic."""

    def __init__(self, db: ClinicDatabase, clinic_id: UUID) -> None:
        self._db = db
        self._clinic_id = clinic_id

    # ------------------------------------------------------------------ ChainStore
    async def claim_due(self, now: datetime, limit: int) -> list[OutboxNotification]:
        return await chain.claim_due(self._db, self._clinic_id, now, limit=limit)

    async def record_attempt(
        self,
        outbox_id: UUID,
        provider: NotificationProvider,
        *,
        attempt: int,
        status: NotificationLogStatus,
        latency_ms: int | None,
        error_code: str | None,
    ) -> None:
        await chain.record_attempt(
            self._db,
            self._clinic_id,
            outbox_id,
            provider,
            attempt=attempt,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    async def settle(
        self,
        outbox_id: UUID,
        *,
        state: NotificationState,
        chain_step: str | None,
        next_attempt_at: datetime,
        attempts: int,
    ) -> None:
        await chain.settle(
            self._db,
            self._clinic_id,
            outbox_id,
            state=state,
            chain_step=chain_step,
            next_attempt_at=next_attempt_at,
            attempts=attempts,
        )

    async def is_acked(self, outbox_id: UUID) -> bool:
        return await chain.is_acked(self._db, self._clinic_id, outbox_id)

    async def load_settings(self) -> NotifySettingsOut:
        return await chain.load_settings(self._db, self._clinic_id)

    async def load_target(self, user_id: UUID) -> NotifyTarget:
        return await chain.load_target(self._db, self._clinic_id, user_id)

    async def drop_push_token(self, token_id: UUID) -> None:
        await chain.drop_push_token(self._db, self._clinic_id, token_id)

    async def list_on_call(self) -> Sequence[OnCallRow]:
        return await chain.list_on_call(self._db, self._clinic_id)

    # ------------------------------------------------------------------ LinkStore
    async def consume_link_code(self, code: str, zalo_user_id: str, at: datetime) -> LinkOutcome:
        return await chain.consume_link_code(self._db, self._clinic_id, code, zalo_user_id, at)

    async def list_internal_account_ids(self) -> frozenset[str]:
        return await chain.list_internal_account_ids(self._db, self._clinic_id)

    # ------------------------------------------------------------------ InternalDirectory
    async def internal_account_id(self) -> str | None:
        return await chain.internal_account_id(self._db, self._clinic_id)

    async def account_purpose(self, account_id: str) -> str | None:
        return await chain.account_purpose(self._db, self._clinic_id, account_id)

    async def is_customer_thread(self, ref: str) -> bool:
        return await chain.is_customer_thread(self._db, self._clinic_id, ref)


class SqlSlaStore:
    """``SlaStore`` of one clinic."""

    def __init__(self, db: ClinicDatabase, clinic_id: UUID) -> None:
        self._db = db
        self._clinic_id = clinic_id

    async def schedule(self, *, request_id: UUID, idx: int, due_at: datetime, dedupe_key: str) -> None:
        await sla_checks.schedule(
            self._db, self._clinic_id, request_id=request_id, idx=idx, due_at=due_at, dedupe_key=dedupe_key
        )

    async def claim_due(self, now: datetime, limit: int) -> list[DueCheck]:
        return await sla_checks.claim_due(self._db, self._clinic_id, now, limit=limit)

    async def finish(self, check: DueCheck, *, ok: bool, now: datetime) -> bool:
        return await sla_checks.finish(self._db, self._clinic_id, check, ok=ok, now=now)
