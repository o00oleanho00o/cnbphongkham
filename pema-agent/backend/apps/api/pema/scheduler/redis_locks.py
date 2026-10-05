"""Redis locks of the scheduler (new module, no zalo-agent source).

zalo-agent ran ONE process, so two things were free: "only one writer at a time" (``node:sqlite``) and "one
global send queue". With several worker processes the first is rebuilt as atomic SQL (the job claim and the
daily cap, see ``scheduled_job_store.claim_due_job`` and ``proactive_send_counter_store``: CORRECTNESS lives
there and never depends on Redis); Redis carries only what SQL cannot express cheaply:

* ``TickLease``: ONE worker scans a clinic per tick (the others skip it), so N workers do not all run the same
  ``SELECT`` every ``SCHEDULER_TICK_MS``. Failing open is safe: if Redis is down every worker scans and the
  atomic claim still lets exactly one of them run each job.
* ``LockSendGate``: spacing of proactive sends per (clinic, account) ACROSS processes, the cross-process half
  of the global queue ``SCHEDULER_SEND_GAP_MS`` (the in-process half is ``proactive_send_queue``).

``LockBackend`` has an in-memory implementation for tests and single-process runs and a Redis one
(``SET key token NX PX ttl`` to take, a compare-and-delete script to release, so a worker can never release a
lock that already expired and was taken by another).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis

from pema.shared.logger import create_logger

log = create_logger("scheduler-locks")

KEY_PREFIX = "pema:sched"

_RELEASE_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
)


class LockBackend(Protocol):
    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        """Take ``key`` for ``ttl_ms``; returns the owner token, or ``None`` when someone else holds it."""
        ...

    async def release(self, key: str, token: str) -> None:
        """Release ``key`` only if ``token`` still owns it."""
        ...

    async def remaining_ms(self, key: str) -> int:
        """Milliseconds until ``key`` expires; 0 when it is free."""
        ...


class InMemoryLockBackend:
    """Process-local backend for tests and single-process runs. ``clock`` returns seconds (monotonic)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._held: dict[str, tuple[str, float]] = {}

    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        now = self._clock()
        current = self._held.get(key)
        if current is not None and current[1] > now:
            return None
        token = secrets.token_hex(8)
        self._held[key] = (token, now + ttl_ms / 1000)
        return token

    async def release(self, key: str, token: str) -> None:
        current = self._held.get(key)
        if current is not None and current[0] == token:
            del self._held[key]

    async def remaining_ms(self, key: str) -> int:
        current = self._held.get(key)
        if current is None:
            return 0
        return max(0, int((current[1] - self._clock()) * 1000))


class RedisLockBackend:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        token = secrets.token_hex(8)
        taken = await self._redis.set(key, token, nx=True, px=ttl_ms)
        return token if taken else None

    async def release(self, key: str, token: str) -> None:
        await self._redis.eval(_RELEASE_SCRIPT, 1, key, token)  # type: ignore[no-untyped-call]

    async def remaining_ms(self, key: str) -> int:
        ttl = await self._redis.pttl(key)
        return max(0, int(ttl))


def tick_lease_key(clinic_id: UUID) -> str:
    return f"{KEY_PREFIX}:tick:{clinic_id}"


def send_gate_key(clinic_id: UUID, account_id: str) -> str:
    return f"{KEY_PREFIX}:gap:{clinic_id}:{account_id}"


class TickLease:
    """One worker per clinic per tick. The lease lasts one tick, so a dead holder blocks nobody for longer."""

    def __init__(self, backend: LockBackend, tick_ms: Callable[[], int]) -> None:
        self._backend = backend
        self._tick_ms = tick_ms

    async def try_hold(self, clinic_id: UUID) -> bool:
        """``True`` when this worker should scan the clinic now. Fails OPEN on any backend error."""
        try:
            ttl = max(1, int(self._tick_ms() * 0.8))
            return await self._backend.acquire(tick_lease_key(clinic_id), ttl) is not None
        except Exception as err:  # Redis unreachable: correctness does not depend on the lease
            log.warning("tick lease unavailable, scanning without it", err=err)
            return True


class LockSendGate:
    """``SendGate`` over a ``LockBackend``: at most one proactive send per ``gap_ms`` per (clinic, account)
    across processes. ``wait_turn`` returns when this caller owns the next slot; the key expires by itself
    after ``gap_ms`` (it is NOT released), which is what spaces the next sender."""

    def __init__(self, backend: LockBackend, poll_ms: int = 25) -> None:
        self._backend = backend
        self._poll = poll_ms / 1000

    async def wait_turn(self, key: str, gap_ms: int) -> None:
        if gap_ms <= 0:
            return
        while True:
            try:
                if await self._backend.acquire(key, gap_ms) is not None:
                    return
                remaining = await self._backend.remaining_ms(key)
            except Exception as err:  # fail open: the in-process queue still spaces this worker's sends
                log.warning("send gate unavailable, relying on the in-process gap", err=err)
                return
            await asyncio.sleep(min(max(remaining / 1000, 0.001), max(self._poll, 0.001)))
