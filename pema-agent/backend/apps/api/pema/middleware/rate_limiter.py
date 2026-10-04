# ported from: src/middleware/rate-limiter.ts
"""Send sequentially per thread, with a random delay before each send.

Purpose: human-like behaviour, which lowers the risk of Zalo flagging the account as spam.

Forced deviation: ``Promise`` chains become an ``asyncio.Lock`` per thread key (FIFO) plus a waiter count.
``enqueue_send`` is a plain function that returns a task, so the thread is registered as busy
SYNCHRONOUSLY, exactly like the original ``queues.set`` (``dang_gui_tren`` is true right after the call).
The state is process local on purpose: sending runs in the worker that holds the thread lock.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pema.config.runtime_tuning_settings import get_tuning_int


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


_queues: dict[str, _Entry] = {}


def _random_send_delay_ms() -> int:
    minimum = get_tuning_int("SEND_DELAY_MIN_MS")
    spread = max(0, get_tuning_int("SEND_DELAY_MAX_MS") - minimum)
    return minimum + random.randint(0, spread)  # noqa: S311 - a human-like delay, not a secret


async def _run[T](thread_key: str, entry: _Entry, task: Callable[[], Awaitable[T]]) -> T:
    try:
        async with entry.lock:
            await asyncio.sleep(_random_send_delay_ms() / 1000)
            return await task()
    finally:
        # Drop the entry when the thread has nothing left to send: a resident bot meets thousands of
        # threads, and keeping one settled entry per thread is a slow memory leak. A failing task still
        # reaches its caller (the error propagates) and does not kill the queue of the thread.
        entry.waiters -= 1
        if entry.waiters == 0 and _queues.get(thread_key) is entry:
            del _queues[thread_key]


def enqueue_send[T](thread_key: str, task: Callable[[], Awaitable[T]]) -> asyncio.Task[T]:
    entry = _queues.get(thread_key)
    if entry is None:
        entry = _Entry()
        _queues[thread_key] = entry
    entry.waiters += 1
    return asyncio.get_running_loop().create_task(_run(thread_key, entry, task))


def pending_send_thread_count() -> int:
    """Number of threads with something to send (memory-leak tests)."""
    return len(_queues)


def dang_gui_tren(thread_key: str) -> bool:
    """Is a message of this thread being sent or waiting to be sent.

    Used to NOT squeeze a side message into the middle of the parts of a reply that is being split:
    ``send_reply_in_parts`` queues the parts one by one, so between two parts the queue is empty and any
    other ``enqueue_send`` can slip in; the reader would see the reply cut in half by an unrelated message."""
    return thread_key in _queues
