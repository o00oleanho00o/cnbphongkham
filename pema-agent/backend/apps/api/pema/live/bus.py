"""The port between the process that changes something and the process that serves the browser (ST-R).

New module (not a port). The worker (turns, drafts) and the API (webhooks, staff routes) are two
processes, so a
change made in one must reach the streams served by the other: they meet in Redis pub/sub, ONE channel per
installation (``pema:live:<clinic_id>``). This file holds the ``LiveEventBus`` Protocol, the wire encoding and
the in-memory adapter the tests use; ``redis_bus`` is the Redis adapter.

What travels is a ``LiveEvent`` (type + id, see ``pema_contracts.live``): never message text or a name.
Delivery is best effort and at most once: a missed event costs one refetch of a screen, and the browser
refetches anyway after any gap (``live-connection.ts``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from pema_contracts.live import LiveEvent

CHANNEL_PREFIX = "pema:live"


def channel_name(clinic_id: UUID) -> str:
    """The pub/sub channel of this installation."""
    return f"{CHANNEL_PREFIX}:{clinic_id}"


def encode_event(event: LiveEvent) -> str:
    """``{"type": "inbox.changed", "id": "<uuid or null>"}``: exactly the two keys, nothing else."""
    return json.dumps({"type": event.type.value, "id": None if event.id is None else str(event.id)})


def decode_event(raw: str) -> LiveEvent | None:
    """``None`` for anything that is not a valid event (another publisher, a corrupt frame): it is skipped."""
    try:
        return LiveEvent.model_validate_json(raw)
    except ValidationError:
        return None


class BusListener(Protocol):
    """One subscription to the channel. ``get`` raises when the connection broke (the caller reconnects)."""

    async def get(self, wait_s: float) -> LiveEvent | None:
        """The next event, or ``None`` when nothing arrived within ``wait_s`` seconds."""
        ...

    async def aclose(self) -> None: ...


class LiveEventBus(Protocol):
    async def publish(self, event: LiveEvent) -> None: ...

    async def listen(self) -> BusListener:
        """Subscribe; returns once the subscription is active, so nothing published afterwards is missed."""
        ...


class InMemoryLiveEventBus:
    """Process-local bus for tests (and a single-process dev run). ``fail_publish`` / ``fail_listen`` make it
    behave like Redis being down."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[LiveEvent | None]] = []  # None in a queue = the connection broke
        self.published: list[LiveEvent] = []
        self.fail_publish = False
        self.fail_listen = False
        self.listeners_opened = 0

    async def publish(self, event: LiveEvent) -> None:
        if self.fail_publish:
            raise ConnectionError("bus is down")
        self.published.append(event)
        for queue in list(self._queues):
            queue.put_nowait(event)

    async def listen(self) -> BusListener:
        if self.fail_listen:
            raise ConnectionError("bus is down")
        queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue()
        self._queues.append(queue)
        self.listeners_opened += 1
        return _InMemoryListener(self, queue)

    def break_listeners(self) -> None:
        """Make every open listener raise on its next ``get`` (the connection to Redis dropped)."""
        for queue in self._queues:
            queue.put_nowait(None)

    def forget(self, queue: asyncio.Queue[LiveEvent | None]) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    @property
    def listener_count(self) -> int:
        return len(self._queues)


class _InMemoryListener:
    def __init__(self, bus: InMemoryLiveEventBus, queue: asyncio.Queue[LiveEvent | None]) -> None:
        self._bus = bus
        self._queue = queue

    async def get(self, wait_s: float) -> LiveEvent | None:
        try:
            event = await asyncio.wait_for(self._queue.get(), wait_s)
        except TimeoutError:
            return None
        if event is None:
            raise ConnectionError("bus connection lost")
        return event

    async def aclose(self) -> None:
        self._bus.forget(self._queue)
