"""Presence: entries expire by themselves, a leave removes at once, the service never fails when the store is
down, and ``presence.changed`` is announced when the set of viewers changes."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest

from pema.live.bus import InMemoryLiveEventBus
from pema.live.presence import (
    PRESENCE_TTL_S,
    InMemoryPresenceStore,
    PresenceEntry,
    PresenceService,
)
from pema.live.publisher import LivePublisher, install_live_publisher
from pema_contracts.live import LiveEventType, PresenceState


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def bus() -> Iterator[InMemoryLiveEventBus]:
    the_bus = InMemoryLiveEventBus()
    install_live_publisher(LivePublisher(the_bus, debounce_s=0.0))
    yield the_bus
    install_live_publisher(None)


async def _drain() -> None:
    await asyncio.sleep(0.02)


def test_the_ttl_is_thirty_seconds() -> None:
    assert PRESENCE_TTL_S == 30.0


async def test_an_entry_expires_thirty_seconds_after_the_last_heartbeat() -> None:
    clock = Clock()
    store = InMemoryPresenceStore(clock=clock)
    conversation, user = uuid4(), uuid4()
    await store.touch(conversation, user, PresenceState.VIEWING)
    clock.now += 29
    assert await store.viewers([conversation]) == {conversation: [PresenceEntry(user, PresenceState.VIEWING)]}
    clock.now += 2
    assert await store.viewers([conversation]) == {}


async def test_a_heartbeat_renews_the_entry() -> None:
    clock = Clock()
    store = InMemoryPresenceStore(clock=clock)
    conversation, user = uuid4(), uuid4()
    await store.touch(conversation, user, PresenceState.VIEWING)
    for _ in range(4):
        clock.now += 15
        assert not await store.touch(conversation, user, PresenceState.VIEWING)
    assert await store.viewers([conversation])


async def test_touch_reports_a_change_for_a_new_person_a_new_state_and_an_expired_entry() -> None:
    clock = Clock()
    store = InMemoryPresenceStore(clock=clock)
    conversation, user = uuid4(), uuid4()
    assert await store.touch(conversation, user, PresenceState.VIEWING)
    assert not await store.touch(conversation, user, PresenceState.VIEWING)
    assert await store.touch(conversation, user, PresenceState.REPLYING)
    clock.now += 31
    assert await store.touch(conversation, user, PresenceState.REPLYING)


async def test_leave_removes_the_person_at_once() -> None:
    store = InMemoryPresenceStore()
    conversation, user = uuid4(), uuid4()
    await store.touch(conversation, user, PresenceState.VIEWING)
    assert await store.leave(conversation, user)
    assert await store.viewers([conversation]) == {}
    assert not await store.leave(conversation, user)


async def test_viewers_of_many_conversations_in_one_call() -> None:
    store = InMemoryPresenceStore()
    one, two, empty = uuid4(), uuid4(), uuid4()
    alice, bob = uuid4(), uuid4()
    await store.touch(one, alice, PresenceState.VIEWING)
    await store.touch(one, bob, PresenceState.REPLYING)
    await store.touch(two, bob, PresenceState.VIEWING)
    result = await store.viewers([one, two, empty])
    assert {e.user_id for e in result[one]} == {alice, bob}
    assert [e.user_id for e in result[two]] == [bob]
    assert empty not in result


async def test_a_new_viewer_announces_presence_changed_for_that_conversation(
    bus: InMemoryLiveEventBus,
) -> None:
    service = PresenceService(InMemoryPresenceStore())
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    assert [(e.type, e.id) for e in bus.published] == [(LiveEventType.PRESENCE_CHANGED, conversation)]
    service.aclose()


async def test_a_repeated_heartbeat_announces_nothing_more(bus: InMemoryLiveEventBus) -> None:
    service = PresenceService(InMemoryPresenceStore())
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    bus.published.clear()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    assert bus.published == []
    await service.beat(conversation, user, PresenceState.REPLYING)  # a new state is a change
    await _drain()
    assert len(bus.published) == 1
    service.aclose()


async def test_leaving_announces_presence_changed(bus: InMemoryLiveEventBus) -> None:
    service = PresenceService(InMemoryPresenceStore())
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    bus.published.clear()
    await service.leave(conversation, user)
    await _drain()
    assert [e.id for e in bus.published] == [conversation]
    service.aclose()


async def test_the_screens_are_told_again_once_the_heartbeats_stopped(bus: InMemoryLiveEventBus) -> None:
    """A closed tab sends no leave call: after the entry expired the colleagues' screens are told to look
    again (one event, after the last heartbeat)."""
    service = PresenceService(InMemoryPresenceStore(ttl_s=0.05), ttl_s=0.05, expiry_slack_s=0.0)
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    bus.published.clear()
    await asyncio.sleep(0.2)
    assert [(e.type, e.id) for e in bus.published] == [(LiveEventType.PRESENCE_CHANGED, conversation)]
    service.aclose()


async def test_every_heartbeat_pushes_the_expiry_notice_back(bus: InMemoryLiveEventBus) -> None:
    service = PresenceService(InMemoryPresenceStore(ttl_s=0.2), ttl_s=0.2, expiry_slack_s=0.0)
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    bus.published.clear()
    for _ in range(4):
        await asyncio.sleep(0.1)
        await service.beat(conversation, user, PresenceState.VIEWING)
    await _drain()
    assert bus.published == []  # still beating: no notice
    service.aclose()


async def test_a_store_that_is_down_never_fails_the_heartbeat_or_the_leave(bus: InMemoryLiveEventBus) -> None:
    store = InMemoryPresenceStore()
    service = PresenceService(store)
    store.fail = True
    conversation, user = uuid4(), uuid4()
    await service.beat(conversation, user, PresenceState.VIEWING)  # no exception
    await service.leave(conversation, user)
    assert await service.viewers([conversation]) == {}
    await _drain()
    assert bus.published == []
    service.aclose()
