"""In-memory fakes of the seams of ``pema.notify`` for tests (not imported by production code). New module.

Nothing here sleeps and nothing touches a database or the network: a test moves a ``FakeClock`` and calls
``run_once``. Everything is synthetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pema.care.routing_types import OnCallRow
from pema.clinic.actions.notification_chain import NotifyTarget
from pema.clinic.actions.notifications import OutboxNotification
from pema.clinic.actions.sla_checks import MAX_ATTEMPTS as SLA_MAX_ATTEMPTS
from pema.clinic.actions.sla_checks import DueCheck
from pema.notify.types import InternalTarget, StepResult
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationRecipientKind,
    NotificationState,
    NotifySettingsOut,
)

EPOCH = datetime(2026, 9, 20, 2, 0, tzinfo=UTC)
"""A demo day, 09:00 on the clinic clock."""


class FakeClock:
    def __init__(self, now: datetime = EPOCH) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        self.now = self.now + timedelta(**delta)
        return self.now


class StepClock:
    """A ``perf`` counter that moves by ``step`` seconds each time it is read (stable latency numbers)."""

    def __init__(self, step: float = 0.005) -> None:
        self._value = 0.0
        self._step = step

    def __call__(self) -> float:
        self._value += self._step
        return self._value


def settings(**changes: Any) -> NotifySettingsOut:
    base = NotifySettingsOut(
        ack_timeout_s=180,
        team_group_id="group-fixture",
        in_app_enabled=True,
        push_enabled=False,
        bell_enabled=True,
        group_enabled=True,
        public_base_url="https://pema.example.test",
    )
    return base.model_copy(update=changes)


def target(
    user_id: UUID, *, zalo: str | None = "zalo-op-fixture", pushes: tuple[Any, ...] = (), **changes: Any
) -> NotifyTarget:
    return replace(
        NotifyTarget(
            user_id=user_id, zalo_user_id=zalo, quiet_start=None, quiet_end=None, push_tokens=pushes
        ),
        **changes,
    )


@dataclass
class Row:
    note: OutboxNotification
    state: NotificationState = NotificationState.PENDING
    chain_step: str | None = None
    next_attempt_at: datetime = EPOCH
    attempts: int = 0
    lease_until: datetime | None = None
    acked: bool = False


@dataclass(frozen=True)
class LogRow:
    outbox_id: UUID
    provider: NotificationProvider
    attempt: int
    status: NotificationLogStatus
    latency_ms: int | None
    error_code: str | None


def payload(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event": "takeover",
        "short_code": "#A1B2",
        "identity_label": "Long",
        "urgency": "normal",
        "summary": "Hội thoại #A1B2 đã được tiếp quản",
        "deep_link": "/inbox?conversation=a1b2c3d4-0000-4000-8000-000000000001",
    }
    return {**base, **changes}


class InMemoryChainStore:
    """``ChainStore`` over a dict of rows."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.rows: dict[UUID, Row] = {}
        self.log: list[LogRow] = []
        self.settings = settings()
        self.targets: dict[UUID, NotifyTarget] = {}
        self.on_call: list[OnCallRow] = []
        self.dropped_tokens: list[UUID] = []

    # ------------------------------------------------------------------ arranging
    def add(
        self,
        kind: NotificationRecipientKind,
        user_id: UUID | None = None,
        *,
        body: dict[str, Any] | None = None,
        notice_kind: str = "assignment.takeover",
    ) -> UUID:
        note = OutboxNotification(
            id=uuid4(),
            kind=notice_kind,
            recipient_kind=kind,
            recipient_user_id=user_id,
            conversation_id=None,
            payload=body or payload(),
        )
        self.rows[note.id] = Row(note=note, next_attempt_at=self.clock.now)
        return note.id

    def ack(self, outbox_id: UUID) -> None:
        row = self.rows[outbox_id]
        row.acked = True
        row.chain_step = "done"
        if row.state is NotificationState.PENDING:
            row.state = NotificationState.SENT

    def providers_logged(self, outbox_id: UUID) -> list[tuple[NotificationProvider, NotificationLogStatus]]:
        return [(entry.provider, entry.status) for entry in self.log if entry.outbox_id == outbox_id]

    # ------------------------------------------------------------------ ChainStore
    async def claim_due(self, now: datetime, limit: int) -> list[OutboxNotification]:
        claimed: list[OutboxNotification] = []
        for row in self.rows.values():
            if len(claimed) >= limit:
                break
            if row.state is not NotificationState.PENDING or row.next_attempt_at > now:
                continue
            if row.lease_until is not None and row.lease_until >= now:
                continue
            row.lease_until = now + timedelta(seconds=90)
            claimed.append(
                replace(row.note, attempts=row.attempts, chain_step=row.chain_step, acked=row.acked)
            )
        return claimed

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
        self.log.append(LogRow(outbox_id, provider, attempt, status, latency_ms, error_code))

    async def settle(
        self,
        outbox_id: UUID,
        *,
        state: NotificationState,
        chain_step: str | None,
        next_attempt_at: datetime,
        attempts: int,
    ) -> None:
        row = self.rows[outbox_id]
        row.state = state
        row.chain_step = chain_step
        row.next_attempt_at = next_attempt_at
        row.attempts = attempts
        row.lease_until = None

    async def is_acked(self, outbox_id: UUID) -> bool:
        return self.rows[outbox_id].acked

    async def load_settings(self) -> NotifySettingsOut:
        return self.settings

    async def load_target(self, user_id: UUID) -> NotifyTarget:
        return self.targets.get(user_id) or target(user_id)

    async def drop_push_token(self, token_id: UUID) -> None:
        self.dropped_tokens.append(token_id)

    async def list_on_call(self) -> Sequence[OnCallRow]:
        return list(self.on_call)


@dataclass
class FakeInternalSender:
    """``InternalSender`` that records what it was asked and answers a canned result."""

    result: StepResult = field(default_factory=StepResult.sent)
    sent: list[tuple[InternalTarget, str]] = field(default_factory=list[tuple[InternalTarget, str]])
    raises: Exception | None = None

    async def send(self, target: InternalTarget, text: str) -> StepResult:
        self.sent.append((target, text))
        if self.raises is not None:
            raise self.raises
        return self.result


@dataclass
class FakeInternalDirectory:
    """``InternalDirectory`` for the guards of ``InternalZaloSender``."""

    account_id: str | None = "notifier"
    purpose: str | None = "internal"
    customer_refs: frozenset[str] = frozenset()

    async def internal_account_id(self) -> str | None:
        return self.account_id

    async def account_purpose(self, account_id: str) -> str | None:
        return self.purpose

    async def is_customer_thread(self, ref: str) -> bool:
        return ref in self.customer_refs


class InMemorySlaStore:
    """``SlaStore`` with M's dedupe, a lease and bounded retries."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def schedule(self, *, request_id: UUID, idx: int, due_at: datetime, dedupe_key: str) -> None:
        self.rows.setdefault(
            dedupe_key,
            {
                "id": uuid4(),
                "request_id": request_id,
                "idx": idx,
                "due_at": due_at,
                "state": "pending",
                "attempts": 0,
                "lease_until": None,
            },
        )

    async def claim_due(self, now: datetime, limit: int) -> list[DueCheck]:
        due: list[DueCheck] = []
        for row in sorted(self.rows.values(), key=lambda r: r["due_at"]):
            if len(due) >= limit or row["state"] != "pending" or row["due_at"] > now:
                continue
            if row["lease_until"] is not None and row["lease_until"] >= now:
                continue
            row["lease_until"] = now + timedelta(seconds=120)
            due.append(DueCheck(row["id"], row["request_id"], row["idx"], row["due_at"], row["attempts"]))
        return due

    async def finish(self, check: DueCheck, *, ok: bool, now: datetime) -> bool:
        row = next(r for r in self.rows.values() if r["id"] == check.id)
        row["lease_until"] = None
        if ok:
            row["state"] = "done"
            return True
        row["attempts"] += 1
        row["due_at"] = now + timedelta(seconds=30 * 2 ** (row["attempts"] - 1))
        if row["attempts"] >= SLA_MAX_ATTEMPTS:
            row["state"] = "failed"
            return True
        return False
