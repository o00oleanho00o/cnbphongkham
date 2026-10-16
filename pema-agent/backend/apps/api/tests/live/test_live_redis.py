"""The Redis adapters against a THROWAWAY Redis (``PEMA_TEST_REDIS_URL``): pub/sub between two connections (the
way the worker and the API are two processes) and Redis being down."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio

from pema.composition.app_runtime import make_redis_client
from pema.live.bus import channel_name
from pema.live.hub import LiveHub
from pema.live.publisher import LivePublisher, install_live_publisher
from pema.live.redis_bus import RedisLiveEventBus
from pema_contracts.live import LiveEvent, LiveEventType

pytestmark = pytest.mark.redis

REDIS_URL = os.environ.get("PEMA_TEST_REDIS_URL")
DEAD_URL = "redis://127.0.0.1:1/0"


@pytest.fixture
def redis_url() -> str:
    if not REDIS_URL:
        pytest.skip("PEMA_TEST_REDIS_URL not set; no Redis to test against")
    return REDIS_URL


@pytest_asyncio.fixture
async def two_clients(redis_url: str) -> AsyncIterator[tuple[Any, Any]]:
    """The "worker" connection and the "API" connection."""
    first, second = make_redis_client(redis_url), make_redis_client(redis_url)
    try:
        yield first, second
    finally:
        await first.aclose()
        await second.aclose()


@pytest.fixture(autouse=True)
def _no_global_publisher() -> None:
    install_live_publisher(None)


async def test_an_event_published_on_one_connection_reaches_a_listener_on_another(
    two_clients: tuple[Any, Any],
) -> None:
    worker, api = two_clients
    clinic = uuid4()
    channel = lambda: channel_name(clinic)  # noqa: E731
    listener = await RedisLiveEventBus(api, channel).listen()
    event = LiveEvent(type=LiveEventType.APPOINTMENTS_CHANGED, id=uuid4())
    await RedisLiveEventBus(worker, channel).publish(event)
    assert await listener.get(2) == event
    assert await listener.get(0.1) is None
    await listener.aclose()


async def test_installations_do_not_hear_each_other() -> None:
    assert channel_name(uuid4()) != channel_name(uuid4())


async def test_a_listener_ignores_a_frame_that_is_not_a_live_event(two_clients: tuple[Any, Any]) -> None:
    worker, api = two_clients
    clinic = uuid4()
    channel = lambda: channel_name(clinic)  # noqa: E731
    listener = await RedisLiveEventBus(api, channel).listen()
    await worker.publish(channel(), "not json")
    await worker.publish(channel(), '{"type": "appointments.changed", "id": null, "text": "extra"}')
    assert await listener.get(0.3) is None
    await listener.aclose()


async def test_publisher_hub_and_stream_work_over_redis(two_clients: tuple[Any, Any]) -> None:
    worker, api = two_clients
    clinic = uuid4()
    channel = lambda: channel_name(clinic)  # noqa: E731
    hub = LiveHub(RedisLiveEventBus(api, channel))
    hub.start()
    assert await hub.wait_available(3)
    sub = hub.subscribe(uuid4())
    publisher = LivePublisher(RedisLiveEventBus(worker, channel), debounce_s=0.0)
    object_id = uuid4()
    publisher.emit(LiveEventType.APPOINTMENTS_CHANGED, object_id)
    publisher.emit(LiveEventType.APPOINTMENTS_CHANGED, object_id)
    await publisher.flush()
    batch = await sub.next_batch(2)
    assert [(e.type, e.id) for e in batch] == [(LiveEventType.APPOINTMENTS_CHANGED, object_id)]
    await hub.aclose()


async def test_with_redis_down_publishing_never_raises() -> None:
    dead = make_redis_client(DEAD_URL)
    try:
        publisher = LivePublisher(RedisLiveEventBus(dead, lambda: channel_name(uuid4())), debounce_s=0.0)
        publisher.emit(LiveEventType.APPOINTMENTS_CHANGED, uuid4())
        await asyncio.wait_for(publisher.flush(), 5)  # logged, not raised
        hub = LiveHub(RedisLiveEventBus(dead, lambda: channel_name(uuid4())), reconnect_delays_s=(0.05,))
        hub.start()
        assert not await hub.wait_available(0.3)
        await hub.aclose()
    finally:
        await dead.aclose()
