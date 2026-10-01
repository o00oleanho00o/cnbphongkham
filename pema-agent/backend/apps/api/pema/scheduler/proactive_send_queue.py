# ported from: src/scheduler/proactive-send-queue.ts
"""The GLOBAL spaced queue between PROACTIVE messages (``SCHEDULER_SEND_GAP_MS``) - unlike the per-thread
queue of the rate limiter in ``middleware`` which only queues INSIDE one thread. Split from
``proactive_send_guard`` (which keeps the condition checks) to keep that file small.

There is NO timeout at this layer (there was one in an earlier version, then removed for good): a timeout
wrapped OUTSIDE the thread lock blocks the WRONG place - it also wraps the time spent WAITING for the thread
lock, which a turn of a USER can hold for minutes (``LLM_TURN_TIMEOUT_MS`` default 900000 ms), perfectly
NORMAL, not a hang. When the timeout fires the work INSIDE keeps running with nobody able to cancel it, so
the message still goes out but: it does not count against the cap (under-counting is more dangerous than
over-counting), the run ledger says 'error' although the send succeeded, and (kind='agent') the real usage
is overwritten with {0,0,0}. An upper bound for the real send, if still wanted, must wrap CLOSE INSIDE the
lock, around EXACTLY the send step, not the wait for the turn. The HTTP client of the channel already has its
own request timeouts, which is a sufficient upper bound.

Forced deviations: the promise ``queueTail`` becomes an ``asyncio.Lock`` (FIFO fair, so tasks run in the order
they were enqueued, each preceded by the gap); ``runOnThreadChain`` becomes the Redis-backed ``ThreadLock``
of the contracts; and an optional ``SendGate`` spaces the same account across worker PROCESSES, which the one
global queue of a single process did for free.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.scheduler.ports import SendGate
from pema.scheduler.redis_locks import send_gate_key
from pema_contracts.agent_turn import ThreadLock


class ProactiveSendQueue:
    def __init__(self, thread_lock: ThreadLock, send_gate: SendGate | None = None) -> None:
        self._thread_lock = thread_lock
        self._send_gate = send_gate
        self._lock = asyncio.Lock()

    async def enqueue_proactive_send[T](
        self, task: Callable[[], Awaitable[T]], *, gate_key: str | None = None
    ) -> T:
        """Put 1 job in the GLOBAL queue, ``SCHEDULER_SEND_GAP_MS`` apart. Takes care only of the TIMING - it
        does not enter any thread chain itself (see ``deliver_proactively`` below, which is where this is
        REALLY used to send).

        The queue stays alive whether the task fails or succeeds - the error of this task still goes back to
        its caller; only the "queue tail" does not break with it."""
        async with self._lock:
            gap_ms = get_tuning_int("SCHEDULER_SEND_GAP_MS")
            await asyncio.sleep(gap_ms / 1000)
            if self._send_gate is not None and gate_key is not None:
                await self._send_gate.wait_turn(gate_key, gap_ms)
            return await task()

    async def deliver_proactively[T](
        self, clinic_id: UUID, account_id: str, thread_id: str, fn: Callable[[], Awaitable[T]]
    ) -> T:
        """Send 1 PROACTIVE message the right way: wait for the turn in the GLOBAL queue FIRST (WITHOUT
        holding the thread lock while waiting), and only once it is our turn enter the thread chain so ``fn``
        (send + write history) runs.

        The nesting order is REVERSED from the first design: the thread chain OUTSIDE and the global queue
        INSIDE made a job waiting in the global queue hold the lock of its own thread - the REAL messages of
        the user on that very thread had to queue behind it, possibly for minutes when the queue is deep. Now
        the global queue wraps OUTSIDE: waiting here touches no thread at all, only when it is OUR TURN do we
        ask into the thread chain - the window that holds the lock shrinks to exactly the real send time."""

        async def locked() -> T:
            async with self._thread_lock.hold(account_id, thread_id):
                return await fn()

        return await self.enqueue_proactive_send(locked, gate_key=send_gate_key(clinic_id, account_id))

    def reset(self) -> None:
        """Tests only - bring the queue back to a clean state between cases."""
        self._lock = asyncio.Lock()
