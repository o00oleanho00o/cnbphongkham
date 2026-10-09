"""The durable inbound queue, conversations and per-session run locks: the types, and in-process versions for
the CLI without a database and for tests. The Postgres versions are in ``agent_app.ingress_store``.

Every inbound message is stored before it runs. A message a channel delivers twice (same external id) is
stored once. At most one turn runs per session at a time, across processes with Postgres; messages for a
busy session wait in the queue and run in arrival order.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from agentcore import TurnResult, Usage
from agentcore.channels import InboundMessage

IngressStatus = Literal["queued", "processing", "done", "failed", "dead"]
FINISHED: frozenset[IngressStatus] = frozenset({"done", "failed", "dead"})


class SessionBusyError(RuntimeError):
    """Another run holds the session and did not let go in time."""


@dataclass(frozen=True, slots=True)
class TurnReply:
    turn_id: str
    text: str
    stop: str
    steps: int
    usage: Usage

    @classmethod
    def of(cls, result: TurnResult) -> TurnReply:
        return cls(result.turn_id, result.text, result.stop, result.steps, result.usage)

    def to_json(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "text": self.text,
            "stop": self.stop,
            "steps": self.steps,
            "usage": self.usage.model_dump(),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> TurnReply:
        return cls(
            str(data["turn_id"]),
            str(data["text"]),
            str(data["stop"]),
            int(data["steps"]),
            Usage.model_validate(data["usage"]),
        )


@dataclass(frozen=True, slots=True)
class IngressRecord:
    id: int
    tenant_id: str
    channel: str
    external_id: str
    conversation_id: str
    user_id: str
    session_id: str
    text: str
    status: IngressStatus
    attempts: int = 0
    error_kind: str | None = None
    reply: TurnReply | None = None
    metadata: Mapping[str, str] = field(default_factory=dict[str, str])

    @property
    def finished(self) -> bool:
        return self.status in FINISHED


class IngressStore(Protocol):
    async def accept(
        self, tenant_id: str, inbound: InboundMessage, session_id: str
    ) -> tuple[IngressRecord, bool]:
        """The stored record and whether it is new; a known external id returns the first record."""
        ...

    async def get(self, tenant_id: str, ingress_id: int) -> IngressRecord | None: ...

    async def next_queued(self, tenant_id: str, session_id: str) -> IngressRecord | None:
        """The oldest queued message of the session."""
        ...

    async def claim(self, ingress_id: int) -> IngressRecord | None:
        """Queued -> processing (one more attempt); None when someone else claimed it first."""
        ...

    async def finish(self, ingress_id: int, reply: TurnReply) -> None: ...

    async def fail(self, ingress_id: int, error_kind: str) -> None: ...

    async def processing(self) -> list[IngressRecord]:
        """Every message marked processing, for the sweeper to find the ones nobody runs any more."""
        ...

    async def requeue(self, ingress_id: int, *, max_attempts: int) -> IngressStatus | None:
        """An orphaned message goes back to the queue, or to ``dead`` after ``max_attempts`` attempts; None
        when it is no longer processing."""
        ...

    async def queued_sessions(self) -> list[tuple[str, str]]:
        """(tenant, session) pairs that have queued messages."""
        ...


class ConversationStore(Protocol):
    async def epoch(self, tenant_id: str, channel: str, conversation_id: str) -> int: ...

    async def reset(self, tenant_id: str, channel: str, conversation_id: str) -> int:
        """Starts the conversation over; returns the new epoch."""
        ...


class SessionLocks(Protocol):
    def hold(
        self, tenant_id: str, session_id: str, *, timeout_s: float | None
    ) -> contextlib.AbstractAsyncContextManager[None]:
        """Holds the session's run lock; ``SessionBusyError`` after ``timeout_s`` (None waits, 0 tries
        once)."""
        ...


class InMemoryIngressStore:
    def __init__(self) -> None:
        self._records: dict[int, IngressRecord] = {}
        self._by_external: dict[tuple[str, str, str], int] = {}

    async def accept(
        self, tenant_id: str, inbound: InboundMessage, session_id: str
    ) -> tuple[IngressRecord, bool]:
        key = (tenant_id, inbound.channel, inbound.message_id)
        known = self._by_external.get(key)
        if known is not None:
            return self._records[known], False
        record = IngressRecord(
            id=len(self._records) + 1,
            tenant_id=tenant_id,
            channel=inbound.channel,
            external_id=inbound.message_id,
            conversation_id=inbound.conversation_id,
            user_id=inbound.user_id,
            session_id=session_id,
            text=inbound.text,
            status="queued",
            metadata=dict(inbound.metadata),
        )
        self._records[record.id] = record
        self._by_external[key] = record.id
        return record, True

    async def get(self, tenant_id: str, ingress_id: int) -> IngressRecord | None:
        record = self._records.get(ingress_id)
        return record if record is not None and record.tenant_id == tenant_id else None

    async def next_queued(self, tenant_id: str, session_id: str) -> IngressRecord | None:
        return next(
            (
                r
                for r in self._records.values()
                if (r.tenant_id, r.session_id, r.status) == (tenant_id, session_id, "queued")
            ),
            None,
        )

    async def claim(self, ingress_id: int) -> IngressRecord | None:
        record = self._records[ingress_id]
        if record.status != "queued":
            return None
        return self._set(replace(record, status="processing", attempts=record.attempts + 1))

    async def finish(self, ingress_id: int, reply: TurnReply) -> None:
        self._set(replace(self._records[ingress_id], status="done", reply=reply, error_kind=None))

    async def fail(self, ingress_id: int, error_kind: str) -> None:
        self._set(replace(self._records[ingress_id], status="failed", error_kind=error_kind))

    async def processing(self) -> list[IngressRecord]:
        return [r for r in self._records.values() if r.status == "processing"]

    async def requeue(self, ingress_id: int, *, max_attempts: int) -> IngressStatus | None:
        record = self._records[ingress_id]
        if record.status != "processing":
            return None
        status: IngressStatus = "dead" if record.attempts >= max_attempts else "queued"
        self._set(replace(record, status=status, error_kind="interrupted" if status == "dead" else None))
        return status

    async def queued_sessions(self) -> list[tuple[str, str]]:
        return sorted({(r.tenant_id, r.session_id) for r in self._records.values() if r.status == "queued"})

    def _set(self, record: IngressRecord) -> IngressRecord:
        self._records[record.id] = record
        return record


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._epochs: dict[tuple[str, str, str], int] = {}

    async def epoch(self, tenant_id: str, channel: str, conversation_id: str) -> int:
        return self._epochs.get((tenant_id, channel, conversation_id), 0)

    async def reset(self, tenant_id: str, channel: str, conversation_id: str) -> int:
        key = (tenant_id, channel, conversation_id)
        self._epochs[key] = self._epochs.get(key, 0) + 1
        return self._epochs[key]


class InMemorySessionLocks:
    """One asyncio lock per session, dropped when nobody holds or waits for it."""

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], tuple[asyncio.Lock, int]] = {}

    @contextlib.asynccontextmanager
    async def hold(self, tenant_id: str, session_id: str, *, timeout_s: float | None) -> AsyncGenerator[None]:
        key = (tenant_id, session_id)
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            if timeout_s == 0:
                if lock.locked():
                    raise SessionBusyError(session_id)
                await lock.acquire()  # free, so this does not wait; wait_for(timeout=0) would give up first
            else:
                try:
                    await asyncio.wait_for(lock.acquire(), timeout=timeout_s)
                except TimeoutError as err:
                    raise SessionBusyError(session_id) from err
            try:
                yield
            finally:
                lock.release()
        finally:
            lock, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)
