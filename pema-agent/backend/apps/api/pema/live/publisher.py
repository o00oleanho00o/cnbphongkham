"""Publishing side of the live events: coalescing, never failing the caller (ST-R).

New module (not a port). The business code calls ``emit_live(type, id)`` AFTER its transaction committed
(never
inside it). The call is synchronous, cheap and never raises: it only notes the event. A timer then sends each
distinct ``(type, id)`` of the last ``DEBOUNCE_S`` once, so a burst (ten messages of one conversation, a CRM
rule run creating forty tasks) becomes a handful of events. A bus that is down is logged once in a while
(without any content) and the business operation is not affected in any way.

``install_live_publisher`` follows the pattern of ``install_runtime_settings``: the composition root installs
the process-wide publisher (API and worker each have one); with none installed ``emit_live`` does nothing, so
tests and tools that never wire it are unaffected.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from uuid import UUID

from pema.live.bus import LiveEventBus
from pema.shared.logger import create_logger
from pema_contracts.live import LiveEvent, LiveEventType

log = create_logger("live.publisher")

DEBOUNCE_S = 0.2
"""Same ``(type, id)`` within this window is sent once."""
PUBLISH_TIMEOUT_S = 2.0
"""A bus that hangs must not pile up tasks: one publish gets this long."""
LOG_EVERY_S = 30.0
"""A broken bus is reported at most this often."""


class LivePublisher:
    def __init__(
        self,
        bus: LiveEventBus,
        *,
        debounce_s: float = DEBOUNCE_S,
        publish_timeout_s: float = PUBLISH_TIMEOUT_S,
    ) -> None:
        self._bus = bus
        self._debounce_s = debounce_s
        self._publish_timeout_s = publish_timeout_s
        self._pending: dict[tuple[LiveEventType, UUID | None], None] = {}
        self._timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._last_logged = float("-inf")

    def emit(self, event_type: LiveEventType, entity_id: UUID | None = None) -> None:
        """Note an event; sent after the debounce window. Needs a running loop (else it is dropped)."""
        key = (event_type, entity_id)
        if key in self._pending:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._pending[key] = None
        if self._timer is None:
            self._timer = loop.call_later(self._debounce_s, self._fire, loop)

    def _fire(self, loop: asyncio.AbstractEventLoop) -> None:
        self._timer = None
        task = loop.create_task(self.flush())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """Send what is pending now (the timer calls this; tests and shutdown call it directly)."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        batch = list(self._pending)
        self._pending.clear()
        for event_type, entity_id in batch:
            await self._publish(LiveEvent(type=event_type, id=entity_id))

    async def _publish(self, event: LiveEvent) -> None:
        try:
            await asyncio.wait_for(self._bus.publish(event), self._publish_timeout_s)
        except Exception as err:
            self._report(err, event)

    def _report(self, err: Exception, event: LiveEvent) -> None:
        stamp = time.monotonic()
        if stamp - self._last_logged < LOG_EVERY_S:
            return
        self._last_logged = stamp
        log.warning("live event not published", err=err, event_type=event.type.value)

    async def aclose(self) -> None:
        """Send the last pending events and wait for the ones in flight (shutdown)."""
        await self.flush()
        tasks = list(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


_publisher: LivePublisher | None = None


def install_live_publisher(publisher: LivePublisher | None) -> None:
    """Composition root: the publisher of this process (``None`` removes it)."""
    global _publisher
    _publisher = publisher


def installed_live_publisher() -> LivePublisher | None:
    return _publisher


def emit_live(event_type: LiveEventType, entity_id: UUID | None = None) -> None:
    """Tell the browsers that something changed. Call it after the commit. Never raises."""
    publisher = _publisher
    if publisher is None:
        return
    with contextlib.suppress(Exception):
        publisher.emit(event_type, entity_id)
