# ported from: src/middleware/thread-run-chain.ts
"""Chain the runs of the SAME thread into a serial queue: the next run waits until the previous one is done.

Prevents the race where a later turn reads history before the earlier turn has written its reply (two
overlapping turns answer each other inconsistently). It is a shared primitive, not part of batching: the
scheduler delivery holds the same lock without going through the batcher, so both must use exactly one lock.

This module knows nothing about batches. It only fires the ``on_thread_free`` hooks each time a run ends;
whoever cares registers itself, so the dependency goes one way (the batcher knows the lock, the lock does not
know the batcher).

Forced deviations (one process -> API process + worker, PLAN-AI01 section 3):

* ``ThreadRef`` replaces the ``${accountId}:${threadId}`` key: account ids are unique per clinic only, so the
  key carries the clinic id (``clinic|account|thread``) and can be parsed back.
* ``InProcessThreadRunChain`` is the faithful port (promise chain -> FIFO ``asyncio.Lock``), used when the API
  and the turn run in one process (tests, single-process mode) and by the scheduler of that process.
* ``ThreadBusy`` is the view the batcher needs. With the turn in the worker, the lock is held there, so the
  API process asks a Redis-backed implementation (``pema.middleware.redis_backends.RedisThreadRunChain``).
* Both implementations offer ``hold_key`` and ``ClinicThreadLock`` adapts them to ``pema_contracts``
  ``ThreadLock`` (whose ``hold(account_id, thread_id)`` carries no clinic id).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from pema_contracts.agent_turn import ThreadLockHandle

type FreeHook = Callable[[str], None]
"""Called with the thread key each time a run on that thread ends."""


@dataclass(frozen=True)
class ThreadRef:
    clinic_id: UUID
    account_id: str
    thread_id: str

    @property
    def key(self) -> str:
        return f"{self.clinic_id}|{self.account_id}|{self.thread_id}"

    @classmethod
    def parse(cls, key: str) -> ThreadRef:
        clinic, account, thread = key.split("|", 2)
        return cls(UUID(clinic), account, thread)


def thread_key_of(clinic_id: UUID, account_id: str, thread_id: str) -> str:
    return ThreadRef(clinic_id, account_id, thread_id).key


class ThreadBusy(Protocol):
    """What the batcher and the busy-wait notice need to know about a thread."""

    async def is_busy(self, thread_key: str) -> bool:
        """``dangBanThread``: does any run hold the lock of this thread."""
        ...

    async def busy_for_ms(self, thread_key: str) -> int | None:
        """``daBanBaoLau``: milliseconds since the thread became busy, ``None`` when idle."""
        ...

    def on_thread_free(self, fn: FreeHook) -> None:
        """``khiThreadRanh``: register a hook fired each time a run on any thread ends."""
        ...

    def active_count(self) -> int:
        """``soThreadDangChay``: live entries of THIS process (memory-leak tests)."""
        ...


class ThreadRunner(ThreadBusy, Protocol):
    """``ThreadBusy`` plus the way the batcher hands a closed batch over."""

    async def run(self, thread_key: str, fn: Callable[[], Awaitable[None]]) -> None:
        """Hand ``fn`` over so the thread counts as busy by the time this returns. It does NOT wait for ``fn``
        to finish (the batcher must not block on a turn that can take minutes)."""
        ...


class HoldsThreadKey(Protocol):
    def hold_key(self, thread_key: str) -> ThreadLockHandle: ...


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


class InProcessThreadRunChain:
    def __init__(self, *, now_ms: Callable[[], float] | None = None) -> None:
        self._now_ms = now_ms or (lambda: time.monotonic() * 1000)
        self._entries: dict[str, _Entry] = {}
        # Start of the FIRST run of the chain that holds the lock. Measured from when the thread became busy,
        # not from the current run: whoever waits does not care how many turns run back to back, only how long
        # they have waited.
        self._busy_since: dict[str, float] = {}
        self._free_hooks: list[FreeHook] = []

    # ------------------------------------------------------------------ ThreadBusy
    def on_thread_free(self, fn: FreeHook) -> None:
        # Registered at construction, never removed: the list is fixed by design, not a dynamic subscription.
        self._free_hooks.append(fn)

    async def is_busy(self, thread_key: str) -> bool:
        return thread_key in self._entries

    async def busy_for_ms(self, thread_key: str) -> int | None:
        since = self._busy_since.get(thread_key)
        return None if since is None else int(self._now_ms() - since)

    def active_count(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------ chaining
    def register_run(self, thread_key: str) -> _Entry:
        entry = self._entries.get(thread_key)
        if entry is None:
            entry = _Entry()
            self._entries[thread_key] = entry
        entry.waiters += 1
        # Only the run that OPENS the chain sets the mark; a run appended to a running chain must not refresh
        # it.
        #
        # KNOWN LIMIT (kept from the original): this clock measures "how long the current chain has run", NOT
        # "how long this person has waited for the reply". Because the batcher PARKS a batch instead of
        # appending it to the running chain, the next turn opens a NEW chain and the clock restarts at 0.
        # Measuring it properly means tracking from the INCOMING message (the oldest unanswered one); not done
        # yet.
        self._busy_since.setdefault(thread_key, self._now_ms())
        return entry

    def _unregister(self, thread_key: str, entry: _Entry) -> None:
        entry.waiters -= 1
        if entry.waiters == 0 and self._entries.get(thread_key) is entry:
            # Drop the entry when the thread is done: these maps live as long as the process, and keeping a
            # settled entry for every thread that ever wrote or had a job is a slow leak.
            del self._entries[thread_key]
            self._busy_since.pop(thread_key, None)
        # Fire UNCONDITIONALLY, even when the entry above is not ours: another run may have piled on, the
        # thread is then still busy, and the listener re-checks and waits again. One extra fire beats a missed
        # one: a missed fire leaves a parked batch forever and the sender is never answered.
        #
        # Each hook is wrapped on its own: a hook that raises would swallow the ones after it.
        for hook in list(self._free_hooks):
            # No log here on purpose: this module does not depend on the logger. A hook that needs a diagnosis
            # wraps its own try/except.
            with contextlib.suppress(Exception):
                hook(thread_key)

    async def acquire_run(self, thread_key: str, entry: _Entry) -> None:
        try:
            await entry.lock.acquire()
        except BaseException:
            self._unregister(thread_key, entry)
            raise

    def release_run(self, thread_key: str, entry: _Entry) -> None:
        entry.lock.release()
        self._unregister(thread_key, entry)

    def run_on_thread_chain[T](self, thread_key: str, fn: Callable[[], Awaitable[T]]) -> asyncio.Task[T]:
        """``runOnThreadChain``: wait for the previous run of ``thread_key`` and then run ``fn``.

        Generic so the caller gets the real result of ``fn``. The thread is registered as busy
        synchronously, before this returns; an error of ``fn`` reaches whoever awaits the task and the lock
        is released all the same."""
        entry = self.register_run(thread_key)

        async def _run() -> T:
            await self.acquire_run(thread_key, entry)
            try:
                return await fn()
            finally:
                self.release_run(thread_key, entry)

        return asyncio.get_running_loop().create_task(_run())

    async def run(self, thread_key: str, fn: Callable[[], Awaitable[None]]) -> None:
        task = self.run_on_thread_chain(thread_key, fn)
        # Whoever calls ``run`` does not await the task; its error is the handler's business (the batcher
        # wraps the handler), so retrieve the exception here to avoid "never retrieved" noise.
        task.add_done_callback(lambda t: t.cancelled() or t.exception())

    def hold_key(self, thread_key: str) -> ThreadLockHandle:
        return _Hold(self, thread_key)


class _Hold:
    def __init__(self, chain: InProcessThreadRunChain, thread_key: str) -> None:
        self._chain = chain
        self._key = thread_key
        self._entry: _Entry | None = None

    async def __aenter__(self) -> None:
        self._entry = self._chain.register_run(self._key)
        await self._chain.acquire_run(self._key, self._entry)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._entry is not None:
            self._chain.release_run(self._key, self._entry)
            self._entry = None


class ClinicThreadLock:
    """Adapts a chain to ``pema_contracts.agent_turn.ThreadLock``. ``clinic_id`` of the constructor is the
    default for a caller that does not pass one; a worker serving several clinics builds it without a default
    and every caller passes its clinic (a missing clinic is an error, never a shared key)."""

    def __init__(self, chain: HoldsThreadKey, clinic_id: UUID | None = None) -> None:
        self._chain = chain
        self._clinic_id = clinic_id

    def hold(self, account_id: str, thread_id: str, clinic_id: UUID | None = None) -> ThreadLockHandle:
        clinic = clinic_id if clinic_id is not None else self._clinic_id
        if clinic is None:
            raise ValueError("a thread lock needs the clinic of the thread")
        return self._chain.hold_key(thread_key_of(clinic, account_id, thread_id))


class QueueThreadRunner:
    """``ThreadRunner`` for the split deployment: the batcher only ENQUEUES a turn job; the worker holds the
    thread lock. ``run`` awaits the hand-over itself (an enqueue is fast) and busy-ness is read from ``busy``.
    """

    def __init__(self, busy: ThreadBusy) -> None:
        self._busy = busy

    async def is_busy(self, thread_key: str) -> bool:
        return await self._busy.is_busy(thread_key)

    async def busy_for_ms(self, thread_key: str) -> int | None:
        return await self._busy.busy_for_ms(thread_key)

    def on_thread_free(self, fn: FreeHook) -> None:
        self._busy.on_thread_free(fn)

    def active_count(self) -> int:
        return self._busy.active_count()

    async def run(self, thread_key: str, fn: Callable[[], Awaitable[None]]) -> None:
        await fn()


__all__ = [
    "ClinicThreadLock",
    "FreeHook",
    "HoldsThreadKey",
    "InProcessThreadRunChain",
    "QueueThreadRunner",
    "ThreadBusy",
    "ThreadRef",
    "ThreadRunner",
    "thread_key_of",
]
