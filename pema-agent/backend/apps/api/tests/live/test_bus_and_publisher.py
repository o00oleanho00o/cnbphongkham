"""The bus, the wire format and the publisher: coalescing, and a broken bus never reaching the caller."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from uuid import uuid4

import pytest

from pema.live.bus import InMemoryLiveEventBus, channel_name, decode_event, encode_event
from pema.live.publisher import LivePublisher, emit_live, install_live_publisher
from pema_contracts.live import LiveEvent, LiveEventType


@pytest.fixture(autouse=True)
def _no_global_publisher() -> Iterator[None]:
    install_live_publisher(None)
    yield
    install_live_publisher(None)


def test_the_wire_payload_has_exactly_the_keys_type_and_id() -> None:
    conversation_id = uuid4()
    raw = encode_event(LiveEvent(type=LiveEventType.INBOX_CHANGED, id=conversation_id))
    assert json.loads(raw) == {"type": "inbox.changed", "id": str(conversation_id)}
    assert set(json.loads(encode_event(LiveEvent(type=LiveEventType.TASKS_CHANGED)))) == {"type", "id"}


def test_an_event_without_an_id_is_sent_with_a_null_id() -> None:
    assert json.loads(encode_event(LiveEvent(type=LiveEventType.REVIEW_CHANGED))) == {
        "type": "review.changed",
        "id": None,
    }


def test_the_channel_is_one_per_installation() -> None:
    clinic_id = uuid4()
    assert channel_name(clinic_id) == f"pema:live:{clinic_id}"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"type": "patient.changed", "id": null}',
        '{"type": "inbox.changed", "id": "not-a-uuid"}',
        '{"type": "inbox.changed", "id": null, "text": "Xin chào"}',
    ],
)
def test_a_frame_that_is_not_a_live_event_is_skipped(raw: str) -> None:
    assert decode_event(raw) is None


async def test_a_listener_receives_what_is_published_after_it_subscribed() -> None:
    bus = InMemoryLiveEventBus()
    listener = await bus.listen()
    event = LiveEvent(type=LiveEventType.INBOX_CHANGED, id=uuid4())
    await bus.publish(event)
    assert await listener.get(0.5) == event
    assert await listener.get(0.01) is None
    await listener.aclose()
    assert bus.listener_count == 0


async def test_a_burst_of_the_same_event_is_published_once() -> None:
    bus = InMemoryLiveEventBus()
    publisher = LivePublisher(bus, debounce_s=0.05)
    conversation_id = uuid4()
    for _ in range(10):
        publisher.emit(LiveEventType.INBOX_CHANGED, conversation_id)
    publisher.emit(LiveEventType.INBOX_CHANGED, uuid4())
    publisher.emit(LiveEventType.TASKS_CHANGED)
    assert bus.published == []  # nothing before the window ends
    await asyncio.sleep(0.15)
    kinds = sorted((e.type.value, e.id is None) for e in bus.published)
    assert kinds == [("inbox.changed", False), ("inbox.changed", False), ("tasks.changed", True)]


async def test_the_same_event_after_the_window_is_published_again() -> None:
    bus = InMemoryLiveEventBus()
    publisher = LivePublisher(bus, debounce_s=0.02)
    conversation_id = uuid4()
    publisher.emit(LiveEventType.INBOX_CHANGED, conversation_id)
    await asyncio.sleep(0.08)
    publisher.emit(LiveEventType.INBOX_CHANGED, conversation_id)
    await asyncio.sleep(0.08)
    assert len(bus.published) == 2


async def test_a_bus_that_is_down_does_not_raise_and_later_events_still_go_out() -> None:
    bus = InMemoryLiveEventBus()
    publisher = LivePublisher(bus, debounce_s=0.0)
    bus.fail_publish = True
    publisher.emit(LiveEventType.INBOX_CHANGED, uuid4())
    await publisher.flush()  # raises nothing
    assert bus.published == []
    bus.fail_publish = False
    publisher.emit(LiveEventType.TASKS_CHANGED)
    await publisher.flush()
    assert [e.type for e in bus.published] == [LiveEventType.TASKS_CHANGED]


async def test_a_bus_that_hangs_is_given_up_on_after_the_publish_timeout() -> None:
    class HangingBus(InMemoryLiveEventBus):
        async def publish(self, event: LiveEvent) -> None:
            await asyncio.sleep(30)

    publisher = LivePublisher(HangingBus(), debounce_s=0.0, publish_timeout_s=0.05)
    publisher.emit(LiveEventType.INBOX_CHANGED)
    await asyncio.wait_for(publisher.flush(), 2)


async def test_aclose_sends_what_is_still_pending() -> None:
    bus = InMemoryLiveEventBus()
    publisher = LivePublisher(bus, debounce_s=60.0)
    publisher.emit(LiveEventType.REVIEW_CHANGED)
    await publisher.aclose()
    assert [e.type for e in bus.published] == [LiveEventType.REVIEW_CHANGED]


async def test_emit_live_without_a_publisher_does_nothing() -> None:
    emit_live(LiveEventType.INBOX_CHANGED, uuid4())


async def test_emit_live_goes_through_the_installed_publisher() -> None:
    bus = InMemoryLiveEventBus()
    publisher = LivePublisher(bus, debounce_s=0.0)
    install_live_publisher(publisher)
    emit_live(LiveEventType.TASKS_CHANGED)
    await publisher.flush()
    assert [e.type for e in bus.published] == [LiveEventType.TASKS_CHANGED]


def test_emit_live_outside_an_event_loop_is_dropped_without_error() -> None:
    install_live_publisher(LivePublisher(InMemoryLiveEventBus()))
    emit_live(LiveEventType.INBOX_CHANGED)
