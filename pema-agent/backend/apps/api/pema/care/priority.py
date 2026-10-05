"""The 3-level priority queue of the care loop: patient message > due event > tick (PLAN-M section 2).

New module (not a port). One sequential worker takes from it (a 12 GB GPU runs one turn at a time), so the
order is the whole scheduling policy. Inside one level the oldest event (``occurred_at``) goes first, then
arrival order, so a burst from one source keeps its order and the pop order is deterministic.

``push`` never blocks and the queue is unbounded: the producers are the webhook and the rule engine, which
must never wait for the GPU; the backlog is visible through ``len`` and ``depth_by_priority``.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pema.care.events import CareEvent, Priority, priority_of


@dataclass(frozen=True, order=True)
class QueuedTurn:
    """One turn to run: the care agent and the event that woke it. Sorted by ``sort_key`` only."""

    sort_key: tuple[int, datetime, int]
    care_agent_id: UUID = field(compare=False)
    event: CareEvent = field(compare=False)

    @property
    def priority(self) -> Priority:
        return Priority(self.sort_key[0])


class CarePriorityQueue:
    def __init__(self) -> None:
        self._heap: list[QueuedTurn] = []
        self._sequence = itertools.count()
        self._wake = asyncio.Event()

    def push(self, care_agent_id: UUID, event: CareEvent) -> QueuedTurn:
        item = QueuedTurn(
            sort_key=(int(priority_of(event)), event.occurred_at, next(self._sequence)),
            care_agent_id=care_agent_id,
            event=event,
        )
        heapq.heappush(self._heap, item)
        self._wake.set()
        return item

    def pop_nowait(self) -> QueuedTurn | None:
        """The next turn, or ``None`` when the queue is empty."""
        if not self._heap:
            return None
        item = heapq.heappop(self._heap)
        if not self._heap:
            self._wake.clear()
        return item

    async def pop(self) -> QueuedTurn:
        """Wait for the next turn."""
        while True:
            item = self.pop_nowait()
            if item is not None:
                return item
            await self._wake.wait()

    def depth_by_priority(self) -> dict[Priority, int]:
        counts = dict.fromkeys(Priority, 0)
        for item in self._heap:
            counts[item.priority] += 1
        return counts

    def __len__(self) -> int:
        return len(self._heap)
