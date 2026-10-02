"""The fan-out inside one API process: one bus subscription, many browser streams (ST-R).

New module (not a port). Every open ``GET /api/v1/events`` stream owns a ``Subscription``; the hub listens to
the bus ONCE (one Redis connection per process, not one per stream) and drops each event into the
subscriptions. A subscription keeps the not-yet-sent events as a set of ``(type, id)``: a slow browser costs a
set, never an unbounded queue, and ten identical events become one. Past ``MAX_PENDING_KEYS`` distinct entries
the ids are dropped and only the types are kept ("something of this kind changed"): the browser refetches
anyway.

Limits (exhaustion): ``max_per_user`` streams per staff member (5: a few tabs and a phone) and ``max_total``
per process. Past either, ``subscribe`` raises ``TooManyStreamsError`` and the route answers 429.

When the bus connection breaks, every stream is closed on purpose (the browser reconnects, gets a 503
while the
bus is down, and falls back to polling by itself); the hub reconnects with a growing delay.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from uuid import UUID

from pema.live.bus import LiveEventBus
from pema.shared.logger import create_logger
from pema_contracts.live import LiveEvent, LiveEventType

log = create_logger("live.hub")

MAX_STREAMS_PER_USER = 5
MAX_STREAMS_TOTAL = 200
MAX_PENDING_KEYS = 200
LISTEN_POLL_S = 1.0
RECONNECT_DELAYS_S: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0)


class TooManyStreamsError(Exception):
    """``scope`` is ``"user"`` or ``"installation"``."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"too many live streams ({scope})")
        self.scope = scope


class Subscription:
    """One browser stream. ``next_batch`` is what the SSE generator awaits."""

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.closed = False
        self._pending: dict[tuple[LiveEventType, UUID | None], None] = {}
        self._wake = asyncio.Event()

    def push(self, event: LiveEvent) -> None:
        if self.closed:
            return
        if len(self._pending) >= MAX_PENDING_KEYS:
            self._pending = {(key[0], None): None for key in self._pending}
            self._pending[(event.type, None)] = None
        else:
            self._pending[(event.type, event.id)] = None
        self._wake.set()

    def close(self) -> None:
        self.closed = True
        self._wake.set()

    async def next_batch(self, wait_s: float) -> list[LiveEvent]:
        """The events that arrived, waiting up to ``wait_s`` seconds for the first one. Empty on timeout or
        when the subscription was closed (check ``closed``)."""
        if not self._pending and not self.closed:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), wait_s)
        self._wake.clear()
        batch = [LiveEvent(type=key[0], id=key[1]) for key in self._pending]
        self._pending.clear()
        return batch


class LiveHub:
    def __init__(
        self,
        bus: LiveEventBus,
        *,
        max_per_user: int = MAX_STREAMS_PER_USER,
        max_total: int = MAX_STREAMS_TOTAL,
        reconnect_delays_s: tuple[float, ...] = RECONNECT_DELAYS_S,
    ) -> None:
        self._bus = bus
        self._max_per_user = max_per_user
        self._max_total = max_total
        self._delays = reconnect_delays_s
        self._subscriptions: set[Subscription] = set()
        self._per_user: defaultdict[UUID, int] = defaultdict(int)
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def aclose(self) -> None:
        task, self._task = self._task, None
        for sub in list(self._subscriptions):
            sub.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @property
    def available(self) -> bool:
        """The bus subscription is active: events can reach the streams."""
        return self._ready.is_set()

    async def wait_available(self, wait_s: float) -> bool:
        if self._task is None:
            self.start()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._ready.wait(), wait_s)
        return self.available

    # ---------------------------------------------------------------- subscriptions
    def subscribe(self, user_id: UUID) -> Subscription:
        if len(self._subscriptions) >= self._max_total:
            raise TooManyStreamsError("installation")
        if self._per_user[user_id] >= self._max_per_user:
            raise TooManyStreamsError("user")
        sub = Subscription(user_id)
        self._subscriptions.add(sub)
        self._per_user[user_id] += 1
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Idempotent: the stream calls it from its ``finally`` and again from the response's cleanup."""
        sub.close()
        if sub not in self._subscriptions:
            return
        self._subscriptions.discard(sub)
        self._per_user[sub.user_id] -= 1
        if self._per_user[sub.user_id] <= 0:
            del self._per_user[sub.user_id]

    @property
    def stream_count(self) -> int:
        return len(self._subscriptions)

    def streams_of(self, user_id: UUID) -> int:
        return self._per_user.get(user_id, 0)

    # ---------------------------------------------------------------- the bus loop
    def _deliver(self, event: LiveEvent) -> None:
        for sub in self._subscriptions:
            sub.push(event)

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                listener = await self._bus.listen()
            except Exception as err:
                log.warning("live bus not reachable", err=err)
                await asyncio.sleep(self._delays[min(attempt, len(self._delays) - 1)])
                attempt += 1
                continue
            attempt = 0
            self._ready.set()
            try:
                while True:
                    event = await listener.get(LISTEN_POLL_S)
                    if event is not None:
                        self._deliver(event)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                log.warning("live bus connection lost", err=err)
            finally:
                self._ready.clear()
                await listener.aclose()
            # The streams end: the browser reconnects, and gets a 503 until the bus is back.
            for sub in list(self._subscriptions):
                sub.close()
            await asyncio.sleep(self._delays[0])
