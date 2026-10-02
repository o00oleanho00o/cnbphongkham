"""Fixtures of the live tests: the Postgres fixtures of the clinic tests plus in-memory live services wired into
the app (no Redis needed except in ``test_live_redis``)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.clinic_testing import (
    admin,
    app,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    worker_db,
    world,
)
from pema.live.bus import InMemoryLiveEventBus
from pema.live.presence import InMemoryPresenceStore
from pema.live.publisher import install_live_publisher
from pema.live.services import LiveServices, build_memory_live_services

__all__ = [
    "admin",
    "app",
    "bus",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "live",
    "pg_url",
    "worker_db",
    "world",
]

MAX_STREAMS_PER_USER = 2


@pytest.fixture
def bus() -> InMemoryLiveEventBus:
    return InMemoryLiveEventBus()


@pytest_asyncio.fixture
async def live(app: FastAPI, bus: InMemoryLiveEventBus) -> AsyncIterator[LiveServices]:
    """In-memory bus and presence, the publisher installed the way the composition root does it."""
    services = build_memory_live_services(
        bus=bus, store=InMemoryPresenceStore(), max_per_user=MAX_STREAMS_PER_USER
    )
    app.state.live = services
    install_live_publisher(services.publisher)
    services.hub.start()
    yield services
    install_live_publisher(None)
    await services.aclose()


@pytest.fixture(autouse=True)
def _reset_publisher() -> None:
    install_live_publisher(None)
