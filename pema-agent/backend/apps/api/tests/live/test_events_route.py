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

from pema.api.clinic_testing import ClientFactory
from pema.api.routers import live as live_router
from pema.bootstrap import create_app
from pema.clinic.actions.seed_demo import SeedResult
from pema.live import sse
from pema.live.bus import InMemoryLiveEventBus
from pema.live.services import LiveServices
from pema.live.testing import OpenStream, session_cookie
from pema_contracts.live import LiveEventType

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


def _an_open_task(admin: Engine) -> tuple[str, str]:
    with admin.connect() as conn:
        row = conn.execute(
            text("SELECT id, patient_id FROM clinic.crm_task WHERE status = 'open' ORDER BY id LIMIT 1")
        ).one()
    return str(row.id), str(row.patient_id)


async def _log_contact(client: httpx.AsyncClient, admin: Engine, note: str) -> httpx.Response:
    task_id, patient_id = _an_open_task(admin)
    return await client.post(
        "/api/v1/crm/activities",
        json={"patient_id": patient_id, "task_id": task_id, "channel": "internal_note", "note": note},
    )


async def test_an_event_names_no_note_text_no_patient_and_no_phone(
    app: FastAPI,
    live: LiveServices,
    client_factory: ClientFactory,
    world: SeedResult,
    admin: Engine,
    streams: list[OpenStream],
) -> None:
    stream = await open_events(app, await client_factory("cs.maianh"), streams)
    await stream.read_until("retry:")
    logged = await _log_contact(await client_factory("cs.maianh"), admin, SECRET_TEXT)
    assert logged.status_code == 201, logged.text
    await flush(live)
    await stream.read_until("tasks.changed")
    frames = [line for line in stream.body.split("\n") if line.startswith("data: ")]
    assert frames
    for frame in frames:
        assert set(json.loads(frame.removeprefix("data: "))) == {"type", "id"}
    for forbidden in (SECRET_TEXT, "đau răng", "Bệnh nhân mẫu", "P0"):
        assert forbidden not in stream.body


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
    live.publisher.emit(LiveEventType.TASKS_CHANGED, uuid4())
    await flush(live)
    assert data_of(await stream.read_until("tasks.changed")) == {"type": "tasks.changed", "id": None}


async def test_reception_receives_no_task_events_only_the_schedule(
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
    # the desk reads appointments (package U, step U2), nothing else
    data_lines = [line for line in stream.body.splitlines() if line.startswith("data:")]
    assert len(data_lines) == 1
    assert json.loads(data_lines[0].removeprefix("data:"))["type"] == "appointments.changed"


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
    admin: Engine,
) -> None:
    bus.fail_publish = True
    logged = await _log_contact(await client_factory("cs.maianh"), admin, "ghi chú mẫu khi bus hỏng")
    assert logged.status_code == 201, logged.text  # the contact log is stored
    await flush(live)  # the publisher fails quietly
    assert bus.published == []
