"""The live objects of one process, built together (ST-R).

New module (not a port). ``LiveServices`` is what the composition root puts in the ``Runtime`` and in
``app.state.live``: the bus, the publisher (both processes), the hub (the API only, started by its lifecycle)
and presence (the API only). ``build_redis_live_services`` is the production wiring,
``build_memory_live_services`` the one tests use.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pema.live.bus import InMemoryLiveEventBus, LiveEventBus, channel_name
from pema.live.hub import LiveHub
from pema.live.presence import InMemoryPresenceStore, PresenceService, PresenceStore, RedisPresenceStore
from pema.live.publisher import LivePublisher
from pema.live.redis_bus import RedisLiveEventBus


@dataclass
class LiveServices:
    bus: LiveEventBus
    publisher: LivePublisher
    hub: LiveHub
    presence: PresenceService

    async def aclose(self) -> None:
        """Shutdown: stop the streams, send what is pending, forget the expiry timers."""
        await self.hub.aclose()
        await self.publisher.aclose()
        self.presence.aclose()


def build_redis_live_services(client: Any, clinic_id: Callable[[], UUID]) -> LiveServices:
    """``client``: the shared ``redis.asyncio`` client of the runtime; ``clinic_id``: the installation id,
    read when a message is sent (it is loaded from the database after the runtime is built)."""
    bus = RedisLiveEventBus(client, lambda: channel_name(clinic_id()))
    return LiveServices(
        bus=bus,
        publisher=LivePublisher(bus),
        hub=LiveHub(bus),
        presence=PresenceService(RedisPresenceStore(client)),
    )


def build_memory_live_services(
    *,
    bus: InMemoryLiveEventBus | None = None,
    store: PresenceStore | None = None,
    debounce_s: float = 0.0,
    max_per_user: int = 5,
    max_total: int = 200,
) -> LiveServices:
    the_bus = bus or InMemoryLiveEventBus()
    return LiveServices(
        bus=the_bus,
        publisher=LivePublisher(the_bus, debounce_s=debounce_s),
        hub=LiveHub(the_bus, max_per_user=max_per_user, max_total=max_total, reconnect_delays_s=(0.05,)),
        presence=PresenceService(store or InMemoryPresenceStore()),
    )
