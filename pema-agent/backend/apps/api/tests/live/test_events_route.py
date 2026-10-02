"""``GET /api/v1/events``: who may open it, what it carries, when it ends, and the business side that feeds it.

Streams are read with ``OpenStream`` (``httpx`` buffers a whole response, so it cannot read a stream)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory, record_inbound
from pema.api.routers import live as live_router
from pema.bootstrap import create_app
from pema.clinic.actions import ClinicAgentFacingActions
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema.live import sse
from pema.live.bus import InMemoryLiveEventBus
from pema.live.publisher import LivePublisher, install_live_publisher
from pema.live.services import LiveServices
from pema.live.testing import OpenStream, session_cookie
from pema_contracts.actions import ActionContext
from pema_contracts.live import LiveEventType
from pema_contracts.review import ReviewItemCreate, ReviewKind, ReviewOrigin, RiskLevel
from pema_contracts.roles import ActorType

pytestmark = pytest.mark.db

SECRET_TEXT = "Em bị đau răng số 36 từ hôm qua (tin mẫu)"
EVENTS = "/api/v1/events"


def data_of(chunk: str) -> dict[str, object]:
    assert chunk.startswith("data: "), chunk
    payload: dict[str, object] = json.loads(chunk.removeprefix("data: "))
    return payload


@pytest_asyncio.fixture
async def streams() -> AsyncIterator[list[OpenStream]]:
    opened: list[OpenStream] = []
    yield opened
    for stream in opened:
        await stream.close()


async def open_events(app: FastAPI, client: httpx.AsyncClient, streams: list[OpenStream]) -> OpenStream:
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(client)).start()
    streams.append(stream)
    return stream


async def flush(live: LiveServices) -> None:
    await live.publisher.flush()
    await asyncio.sleep(0.05)


# ------------------------------------------------------------------------------------- who may open it


async def test_the_stream_needs_a_session_without_any_cookie() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(), raise_app_exceptions=False), base_url="http://test"
    ) as http:
        response = await http.get(EVENTS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_a_tampered_cookie_is_refused(app: FastAPI, live: LiveServices) -> None:
    stream = await OpenStream(app, EVENTS, cookie="pema_session=not-a-jwt").start()
    assert stream.status == 401
    assert live.hub.stream_count == 0
    await stream.close()


async def test_a_signed_in_member_gets_an_event_stream_that_nobody_may_buffer(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    assert stream.status == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "no-cache" in stream.headers["cache-control"]
    assert "no-transform" in stream.headers["cache-control"]
    assert stream.headers["x-accel-buffering"] == "no"
    assert (await stream.read()).startswith("retry:")


async def test_the_stream_is_503_while_the_live_bus_is_down(
    app: FastAPI,
    bus: InMemoryLiveEventBus,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_router, "BUS_WAIT_S", 0.1)
    bus.fail_listen = True
    bus.break_listeners()  # the hub loses its subscription and cannot get a new one
    await asyncio.sleep(0.1)
    assert not live.hub.available
    client = await client_factory("cs.maianh")
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(client)).start()
    await stream.wait_finished()
    assert stream.status == 503
    await stream.close()


# ------------------------------------------------------------------------------------- what it carries


async def test_the_stream_receives_inbox_changed_after_an_inbound_message_is_processed(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    db: ClinicDatabase,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    await stream.read_until("retry:")
    ref = await record_inbound(db, world, text=SECRET_TEXT)
    await flush(live)
    chunk = await stream.read_until("inbox.changed")
    assert data_of(chunk) == {"type": "inbox.changed", "id": str(ref.conversation_id)}


async def test_an_event_names_no_message_text_no_patient_and_no_phone(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    db: ClinicDatabase,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    await stream.read_until("retry:")
    await record_inbound(db, world, text=SECRET_TEXT)
    await flush(live)
    await stream.read_until("inbox.changed")
    frames = [line for line in stream.body.split("\n") if line.startswith("data: ")]
    assert frames
    for frame in frames:
        assert set(json.loads(frame.removeprefix("data: "))) == {"type", "id"}
    for forbidden in (SECRET_TEXT, "đau răng", "Khách mẫu", "Bệnh nhân mẫu", "P025", "demo-uid"):
        assert forbidden not in stream.body


async def test_a_duplicate_delivery_of_the_same_update_announces_nothing(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    db: ClinicDatabase,
    streams: list[OpenStream],
) -> None:
    update_id = uuid4().hex
    await record_inbound(db, world, update_id=update_id, thread="dup-thread")
    await flush(live)
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    await stream.read_until("retry:")
    again = await record_inbound(db, world, update_id=update_id, thread="dup-thread")
    assert again.duplicate
    await flush(live)
    assert "inbox.changed" not in stream.body


async def test_a_change_made_through_the_api_reaches_the_other_screens(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    stream = await open_events(app, thu, streams)
    await stream.read_until("retry:")
    response = await mai_anh.post(f"/api/v1/conversations/{world.conversation_id}/read")
    assert response.status_code == 204
    await flush(live)
    chunk = await stream.read_until("inbox.changed")
    assert data_of(chunk) == {"type": "inbox.changed", "id": str(world.conversation_id)}


async def test_a_new_review_item_announces_the_queue_and_the_conversation(
    app: FastAPI,
    bus: InMemoryLiveEventBus,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    db: ClinicDatabase,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    await stream.read_until("retry:")
    item = await ClinicAgentFacingActions(db).create_review_item(
        ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT),
        ReviewItemCreate(
            job_id=f"job-{uuid4().hex}",
            clinic_id=world.clinic_id,
            patient_ref="P025",
            conversation_ref=str(world.conversation_id),
            kind=ReviewKind.REPLY_DRAFT,
            origin=ReviewOrigin.AGENT_TURN,
            draft_text="Chào bạn (nội dung mẫu).",
            risk_level=RiskLevel.NORMAL,
        ),
    )
    await flush(live)
    await stream.read_until("review.changed")
    published = {(e.type, e.id) for e in bus.published}
    assert (LiveEventType.REVIEW_CHANGED, item.id) in published
    assert (LiveEventType.INBOX_CHANGED, world.conversation_id) in published


async def test_a_burst_of_inbound_messages_is_one_event_per_conversation(
    bus: InMemoryLiveEventBus, live: LiveServices, world: SeedResult, db: ClinicDatabase
) -> None:
    publisher = LivePublisher(bus, debounce_s=0.5)  # the real window is 0.2 s; the test must not race it
    install_live_publisher(publisher)
    thread = "burst-thread"
    for _ in range(6):
        await record_inbound(db, world, thread=thread, text="tin mẫu")
    assert bus.published == []
    await publisher.flush()
    inbox = [e for e in bus.published if e.type is LiveEventType.INBOX_CHANGED]
    assert len(inbox) == 1


# ------------------------------------------------------------------------------------- who gets what


async def test_a_doctor_stream_carries_no_ids_because_a_doctor_sees_only_their_own_patients(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("doctor.mai"), streams)
    await stream.read_until("retry:")
    live.publisher.emit(LiveEventType.INBOX_CHANGED, world.conversation_id)
    await flush(live)
    assert data_of(await stream.read_until("inbox.changed")) == {"type": "inbox.changed", "id": None}


async def test_reception_receives_no_inbox_review_or_task_events(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_S", 0.1)
    stream = await open_events(app, await client_factory("reception.lan"), streams)
    await stream.read_until("retry:")
    for event_type in LiveEventType:
        live.publisher.emit(event_type, uuid4())
    await flush(live)
    await stream.read_until(": keep-alive")
    assert "data:" not in stream.body


# ------------------------------------------------------------------------------------- keep-alive, end


async def test_an_idle_stream_gets_a_keep_alive_comment(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_S", 0.1)
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    assert (await stream.read_until(": keep-alive")).startswith(":")


async def test_a_closed_connection_releases_the_stream(
    app: FastAPI, live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    client = await client_factory("cs.maianh")
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(client)).start()
    await stream.read_until("retry:")
    assert live.hub.stream_count == 1
    await stream.close()
    assert stream.finished
    assert live.hub.stream_count == 0


async def test_a_person_cannot_open_more_streams_than_the_cap(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    streams: list[OpenStream],
) -> None:
    cs = await client_factory("cs.maianh")
    for _ in range(2):
        await open_events(app, cs, streams)
    third = await OpenStream(app, EVENTS, cookie=session_cookie(cs)).start()
    await third.wait_finished()
    assert third.status == 429
    assert json.loads(third.body)["error"]["code"] == "rate_limited"
    assert live.hub.stream_count == 2
    other = await open_events(app, await client_factory("cs.thu"), streams)  # somebody else is not affected
    assert other.status == 200
    await streams[0].close()  # a slot is free again
    again = await open_events(app, cs, streams)
    assert again.status == 200


async def test_logging_out_ends_the_stream(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_S", 0.1)
    monkeypatch.setattr(sse, "RECHECK_S", 0.1)
    cs = await client_factory("cs.maianh")
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(cs)).start()
    await stream.read_until("retry:")
    assert (await cs.post("/api/v1/auth/logout")).status_code == 204
    await stream.wait_finished()
    assert live.hub.stream_count == 0
    await stream.close()


async def test_deactivating_the_account_ends_the_stream(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_S", 0.1)
    monkeypatch.setattr(sse, "RECHECK_S", 0.1)
    email = "cs.thu@example.test"
    cs = await client_factory("cs.thu")
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(cs)).start()
    await stream.read_until("retry:")
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.user_account SET active = false WHERE email = :e"), {"e": email})
    try:
        await stream.wait_finished()
    finally:
        with admin.begin() as conn:
            conn.execute(text("UPDATE clinic.user_account SET active = true WHERE email = :e"), {"e": email})
        await stream.close()
    assert live.hub.stream_count == 0


async def test_an_expired_session_ends_the_stream(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sse, "KEEPALIVE_S", 0.1)
    monkeypatch.setattr(sse, "RECHECK_S", 0.1)
    cs = await client_factory("cs.maianh")
    stream = await OpenStream(app, EVENTS, cookie=session_cookie(cs)).start()
    await stream.read_until("retry:")
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE clinic.auth_session SET expires_at = '2000-01-01T00:00:00+00', "
                "absolute_expires_at = '2000-01-01T00:00:00+00' WHERE user_id = "
                "(SELECT id FROM clinic.user_account WHERE email = 'cs.maianh@example.test')"
            )
        )
    await stream.wait_finished()
    await stream.close()


# ------------------------------------------------------------------------------------- the business side


async def test_a_bus_that_cannot_publish_never_breaks_the_business_operation(
    app: FastAPI,
    bus: InMemoryLiveEventBus,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    db: ClinicDatabase,
) -> None:
    bus.fail_publish = True
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world, text="tin mẫu khi bus hỏng")  # the inbound message is stored
    assert not ref.duplicate
    assert (await cs.post(f"/api/v1/conversations/{ref.conversation_id}/read")).status_code == 204
    detail = await cs.get(f"/api/v1/conversations/{ref.conversation_id}")
    assert detail.status_code == 200
    patched = await cs.patch(
        f"/api/v1/conversations/{ref.conversation_id}",
        json={"version": detail.json()["version"], "assigned_user_id": str(world.users["cs.maianh"])},
    )
    assert patched.status_code == 200
    await flush(live)  # the publisher fails quietly
    assert bus.published == []
