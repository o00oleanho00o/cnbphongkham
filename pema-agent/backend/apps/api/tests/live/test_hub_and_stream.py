"""The hub (one bus subscription, many streams, limits) and the body of the SSE stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from pema.live.bus import InMemoryLiveEventBus
from pema.live.hub import MAX_PENDING_KEYS, LiveHub, TooManyStreamsError
from pema.live.sse import KEEPALIVE_FRAME, StreamAccess, event_stream
from pema_contracts.live import LiveEvent, LiveEventType

ALL = frozenset(LiveEventType)
EVERYTHING = StreamAccess(types=ALL, with_ids=True)


async def _started_hub(bus: InMemoryLiveEventBus) -> LiveHub:
    hub = LiveHub(bus, reconnect_delays_s=(0.02,))
    hub.start()
    assert await hub.wait_available(2)
    return hub


async def _always_valid() -> StreamAccess | None:
    return EVERYTHING


async def _next(stream: AsyncGenerator[str], wait_s: float = 2.0) -> str:
    return await asyncio.wait_for(anext(stream), wait_s)


# ------------------------------------------------------------------------------------------------ hub


async def test_an_event_reaches_every_open_stream() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    first = hub.subscribe(uuid4())
    second = hub.subscribe(uuid4())
    event = LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4())
    await bus.publish(event)
    assert await first.next_batch(1) == [event]
    assert await second.next_batch(1) == [event]
    await hub.aclose()


async def test_the_hub_listens_to_the_bus_once_however_many_streams_are_open() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    for _ in range(4):
        hub.subscribe(uuid4())
    assert bus.listener_count == 1
    await hub.aclose()
    assert bus.listener_count == 0


async def test_a_burst_of_identical_events_is_one_event_per_stream() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    conversation_id = uuid4()
    for _ in range(20):
        await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=conversation_id))
    await asyncio.sleep(0.05)
    assert len(await sub.next_batch(1)) == 1
    await hub.aclose()


async def test_a_slow_stream_keeps_a_bounded_set_and_then_only_the_types() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    for _ in range(MAX_PENDING_KEYS + 50):
        await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4()))
    await asyncio.sleep(0.2)
    batch = await sub.next_batch(1)
    assert len(batch) <= MAX_PENDING_KEYS + 1
    assert any(event.id is None for event in batch)
    await hub.aclose()


async def test_a_person_cannot_hold_more_streams_than_the_cap() -> None:
    hub = LiveHub(InMemoryLiveEventBus(), max_per_user=2)
    user = uuid4()
    first = hub.subscribe(user)
    hub.subscribe(user)
    with pytest.raises(TooManyStreamsError) as error:
        hub.subscribe(user)
    assert error.value.scope == "user"
    hub.subscribe(uuid4())  # another person is not affected
    hub.unsubscribe(first)
    hub.subscribe(user)  # a slot is free again
    assert hub.streams_of(user) == 2


async def test_the_installation_cap_stops_streams_of_everybody() -> None:
    hub = LiveHub(InMemoryLiveEventBus(), max_per_user=5, max_total=3)
    for _ in range(3):
        hub.subscribe(uuid4())
    with pytest.raises(TooManyStreamsError) as error:
        hub.subscribe(uuid4())
    assert error.value.scope == "installation"


async def test_unsubscribe_twice_counts_once() -> None:
    hub = LiveHub(InMemoryLiveEventBus())
    user = uuid4()
    sub = hub.subscribe(user)
    hub.unsubscribe(sub)
    hub.unsubscribe(sub)
    assert hub.streams_of(user) == 0
    assert hub.stream_count == 0


async def test_when_the_bus_connection_breaks_every_stream_is_closed_and_the_hub_reconnects() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    bus.break_listeners()
    assert await sub.next_batch(2) == []
    assert sub.closed
    # the hub is back on a new listener
    for _ in range(100):
        if hub.available and bus.listeners_opened >= 2:
            break
        await asyncio.sleep(0.02)
    assert hub.available
    assert bus.listeners_opened >= 2
    await hub.aclose()


async def test_the_hub_is_not_available_while_the_bus_is_unreachable_and_comes_up_with_it() -> None:
    bus = InMemoryLiveEventBus()
    bus.fail_listen = True
    hub = LiveHub(bus, reconnect_delays_s=(0.02,))
    hub.start()
    assert not await hub.wait_available(0.15)
    bus.fail_listen = False
    assert await hub.wait_available(2)
    await hub.aclose()


# ------------------------------------------------------------------------------------------------ stream


async def test_the_stream_opens_with_a_retry_line_and_sends_events_as_data_frames() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=5)
    assert await _next(stream) == "retry: 3000\n\n"
    conversation_id = uuid4()
    await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=conversation_id))
    frame = await _next(stream)
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame.removeprefix("data: ")) == {"type": "inbox.changed", "id": str(conversation_id)}
    await stream.aclose()
    await hub.aclose()


async def test_the_payload_of_an_event_has_only_type_and_id() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=5)
    await _next(stream)
    for event_type in LiveEventType:
        await bus.publish(LiveEvent(type=event_type, id=uuid4()))
    await asyncio.sleep(0.05)
    frames = [await _next(stream) for _ in range(len(LiveEventType))]
    for frame in frames:
        assert set(json.loads(frame.removeprefix("data: "))) == {"type", "id"}
    await stream.aclose()
    await hub.aclose()


async def test_a_comment_line_keeps_an_idle_stream_alive() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=0.05)
    await _next(stream)
    assert await _next(stream) == KEEPALIVE_FRAME
    assert await _next(stream) == KEEPALIVE_FRAME
    assert KEEPALIVE_FRAME.startswith(":")  # a comment: the browser ignores it
    await stream.aclose()
    await hub.aclose()


async def test_a_person_gets_only_the_event_types_they_may_read() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    access = StreamAccess(types=frozenset({LiveEventType.TASKS_CHANGED}), with_ids=True)
    stream = event_stream(hub, sub, access=access, refresh_access=_always_valid, keepalive_s=0.2)
    await _next(stream)
    await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4()))
    await bus.publish(LiveEvent(type=LiveEventType.TASKS_CHANGED, id=None))
    await asyncio.sleep(0.05)
    frame = await _next(stream)
    assert json.loads(frame.removeprefix("data: ")) == {"type": "tasks.changed", "id": None}
    await stream.aclose()
    await hub.aclose()


async def test_a_stream_without_ids_names_no_object() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    access = StreamAccess(types=ALL, with_ids=False)
    stream = event_stream(hub, sub, access=access, refresh_access=_always_valid, keepalive_s=5)
    await _next(stream)
    await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4()))
    frame = await _next(stream)
    assert json.loads(frame.removeprefix("data: ")) == {"type": "inbox.changed", "id": None}
    await stream.aclose()
    await hub.aclose()


async def test_the_stream_ends_when_the_session_is_no_longer_valid() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    user = uuid4()
    sub = hub.subscribe(user)
    checks: list[int] = []

    async def session_gone() -> StreamAccess | None:
        checks.append(1)
        return None

    stream = event_stream(
        hub, sub, access=EVERYTHING, refresh_access=session_gone, keepalive_s=0.03, recheck_s=0.03
    )
    await _next(stream)
    with pytest.raises(StopAsyncIteration):
        for _ in range(10):
            await _next(stream)
    assert checks
    assert hub.streams_of(user) == 0  # the slot is released


async def test_the_session_is_checked_again_every_interval_and_a_role_change_applies() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    narrowed = StreamAccess(types=frozenset(), with_ids=False)

    async def now_narrower() -> StreamAccess | None:
        return narrowed

    stream = event_stream(
        hub, sub, access=EVERYTHING, refresh_access=now_narrower, keepalive_s=0.03, recheck_s=0.03
    )
    await _next(stream)
    assert await _next(stream) == KEEPALIVE_FRAME  # first idle tick: access re-read, nothing allowed now
    await bus.publish(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4()))
    assert await _next(stream) == KEEPALIVE_FRAME
    await stream.aclose()
    await hub.aclose()


async def test_closing_a_stream_releases_its_slot() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    user = uuid4()
    sub = hub.subscribe(user)
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=5)
    await _next(stream)
    assert hub.streams_of(user) == 1
    await stream.aclose()
    assert hub.streams_of(user) == 0
    await hub.aclose()


async def test_cancelling_a_waiting_stream_releases_its_slot() -> None:
    """What the server does when the client disconnects: the task is cancelled while it waits."""
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    user = uuid4()
    sub = hub.subscribe(user)
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=30)

    async def drain() -> None:
        async for _ in stream:
            pass

    task = asyncio.get_running_loop().create_task(drain())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert hub.streams_of(user) == 0
    await hub.aclose()


async def test_the_stream_ends_when_the_bus_is_lost() -> None:
    bus = InMemoryLiveEventBus()
    hub = await _started_hub(bus)
    sub = hub.subscribe(uuid4())
    stream = event_stream(hub, sub, access=EVERYTHING, refresh_access=_always_valid, keepalive_s=5)
    await _next(stream)
    bus.break_listeners()
    with pytest.raises(StopAsyncIteration):
        await _next(stream)
    await hub.aclose()
