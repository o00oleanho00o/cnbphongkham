"""Presence through the HTTP API: heartbeat, leave, ``viewers`` in the Inbox, authorization, degradation.

A warning, never a lock: nothing here may stop anybody from sending."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.live.bus import InMemoryLiveEventBus
from pema.live.presence import InMemoryPresenceStore
from pema.live.publisher import install_live_publisher
from pema.live.services import LiveServices, build_memory_live_services
from pema_contracts.live import LiveEventType

pytestmark = pytest.mark.db


class Clock:
    def __init__(self) -> None:
        self.now = 5_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> InMemoryPresenceStore:
    return InMemoryPresenceStore(clock=clock)


@pytest_asyncio.fixture
async def presence_live(
    app: FastAPI, bus: InMemoryLiveEventBus, store: InMemoryPresenceStore
) -> AsyncIterator[LiveServices]:
    services = build_memory_live_services(bus=bus, store=store)
    app.state.live = services
    install_live_publisher(services.publisher)
    yield services
    install_live_publisher(None)
    await services.aclose()


def path(world: SeedResult) -> str:
    return f"/api/v1/conversations/{world.conversation_id}"


async def viewers(client: httpx.AsyncClient, world: SeedResult) -> list[dict[str, str]]:
    response = await client.get(path(world))
    assert response.status_code == 200, response.text
    found: list[dict[str, str]] = response.json()["viewers"]
    return found


async def in_list(client: httpx.AsyncClient, world: SeedResult) -> list[dict[str, str]]:
    page = (await client.get("/api/v1/conversations", params={"limit": 200})).json()
    row = next(c for c in page["items"] if c["id"] == str(world.conversation_id))
    found: list[dict[str, str]] = row["viewers"]
    return found


async def beat(client: httpx.AsyncClient, world: SeedResult, state: str = "viewing") -> httpx.Response:
    return await client.post(f"{path(world)}/presence", json={"state": state})


# ------------------------------------------------------------------------------------- what colleagues see


async def test_a_colleague_sees_who_is_viewing_the_conversation_by_name(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    assert (await beat(mai_anh, world)).status_code == 204
    seen = await viewers(thu, world)
    assert seen == [
        {"user_id": str(world.users["cs.maianh"]), "name": "CSKH Mai Anh (mẫu)", "state": "viewing"}
    ]


async def test_the_caller_never_appears_in_their_own_viewers(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    await beat(mai_anh, world)
    assert await viewers(mai_anh, world) == []
    assert await in_list(mai_anh, world) == []


async def test_two_people_on_the_same_conversation_see_each_other(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    await beat(mai_anh, world, "viewing")
    await beat(thu, world, "replying")
    assert [v["user_id"] for v in await viewers(mai_anh, world)] == [str(world.users["cs.thu"])]
    assert [v["user_id"] for v in await viewers(thu, world)] == [str(world.users["cs.maianh"])]
    assert (await viewers(mai_anh, world))[0]["state"] == "replying"
    assert (await in_list(mai_anh, world))[0]["state"] == "replying"


async def test_a_third_person_sees_both(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory("owner")
    for key in ("cs.maianh", "cs.thu"):
        await beat(await client_factory(key), world)
    assert {v["user_id"] for v in await viewers(owner, world)} == {
        str(world.users["cs.maianh"]),
        str(world.users["cs.thu"]),
    }


async def test_leaving_removes_the_person_at_once(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    await beat(mai_anh, world)
    assert len(await viewers(thu, world)) == 1
    assert (await mai_anh.delete(f"{path(world)}/presence")).status_code == 204
    assert await viewers(thu, world) == []


async def test_presence_expires_thirty_seconds_after_the_last_heartbeat(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult, clock: Clock
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    await beat(mai_anh, world)
    clock.now += 29
    assert len(await viewers(thu, world)) == 1
    await beat(mai_anh, world)  # the heartbeat renews it
    clock.now += 29
    assert len(await viewers(thu, world)) == 1
    clock.now += 2
    assert await viewers(thu, world) == []
    assert await in_list(thu, world) == []


async def test_presence_never_blocks_sending(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    await beat(mai_anh, world, "replying")
    sent = await thu.post(f"{path(world)}/messages", json={"text": "Phòng khám xin chào (tin mẫu)"})
    assert sent.status_code == 201


async def test_a_heartbeat_announces_presence_changed_for_that_conversation_only_when_it_changes(
    presence_live: LiveServices, bus: InMemoryLiveEventBus, client_factory: ClientFactory, world: SeedResult
) -> None:
    mai_anh = await client_factory("cs.maianh")
    await beat(mai_anh, world)
    await presence_live.publisher.flush()
    changed = [(e.type, e.id) for e in bus.published if e.type is LiveEventType.PRESENCE_CHANGED]
    assert changed == [(LiveEventType.PRESENCE_CHANGED, world.conversation_id)]
    bus.published.clear()
    await beat(mai_anh, world)
    await presence_live.publisher.flush()
    assert bus.published == []
    await beat(mai_anh, world, "replying")
    await presence_live.publisher.flush()
    assert len(bus.published) == 1
    await mai_anh.delete(f"{path(world)}/presence")
    await presence_live.publisher.flush()
    assert len(bus.published) == 2
    await asyncio.sleep(0)


# ------------------------------------------------------------------------------------- authorization


async def test_a_heartbeat_without_a_session_is_401(presence_live: LiveServices, app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as anonymous:
        response = await anonymous.post(
            f"/api/v1/conversations/{uuid4()}/presence", json={"state": "viewing"}
        )
        assert response.status_code == 401
        assert (await anonymous.delete(f"/api/v1/conversations/{uuid4()}/presence")).status_code == 401


async def test_a_heartbeat_for_a_conversation_that_does_not_exist_is_404(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory("cs.maianh")
    response = await cs.post(f"/api/v1/conversations/{uuid4()}/presence", json={"state": "viewing"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert (await cs.delete(f"/api/v1/conversations/{uuid4()}/presence")).status_code == 404


async def test_a_role_that_cannot_read_conversations_cannot_announce_presence_there(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    assert (await reception.get(path(world))).status_code == 403
    response = await beat(reception, world)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_a_doctor_outside_the_scope_of_the_patient_gets_the_same_answer_as_for_reading(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    statuses: dict[str, tuple[int, int]] = {}
    for key in ("doctor.mai", "doctor.an"):
        doctor = await client_factory(key)
        reading = (await doctor.get(path(world))).status_code
        heartbeat = (await beat(doctor, world)).status_code
        statuses[key] = (reading, heartbeat)
        assert heartbeat == (204 if reading == 200 else 404)
    assert 404 in {heartbeat for _, heartbeat in statuses.values()}, statuses
    assert 204 in {heartbeat for _, heartbeat in statuses.values()}, statuses


async def test_a_doctor_out_of_scope_is_never_listed_as_a_viewer(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    for key in ("doctor.mai", "doctor.an"):
        doctor = await client_factory(key)
        await beat(doctor, world)  # 204 or 404: only the one in scope is stored
    owner = await client_factory("owner")
    listed = {v["user_id"] for v in await viewers(owner, world)}
    assert listed <= {str(world.users["doctor.mai"]), str(world.users["doctor.an"])}
    assert len(listed) == 1


async def test_an_unknown_presence_state_is_refused(
    presence_live: LiveServices, client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory("cs.maianh")
    assert (await beat(cs, world, "sleeping")).status_code == 422
    assert (await cs.post(f"{path(world)}/presence", json={})).status_code == 422


# ------------------------------------------------------------------------------------- degradation


async def test_when_the_presence_store_is_down_heartbeats_still_answer_204_and_viewers_are_empty(
    presence_live: LiveServices,
    store: InMemoryPresenceStore,
    client_factory: ClientFactory,
    world: SeedResult,
) -> None:
    mai_anh = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    await beat(mai_anh, world)
    store.fail = True
    assert (await beat(thu, world)).status_code == 204
    assert (await thu.delete(f"{path(world)}/presence")).status_code == 204
    assert await viewers(thu, world) == []  # the conversation itself still loads
    page = await thu.get("/api/v1/conversations", params={"limit": 200})
    assert page.status_code == 200
    assert all(row["viewers"] == [] for row in page.json()["items"])


async def test_without_any_live_services_the_inbox_and_presence_still_work(
    app: FastAPI, client_factory: ClientFactory, world: SeedResult
) -> None:
    """A bare app (no composition root): ``viewers`` is empty and the heartbeat is accepted."""
    cs = await client_factory("cs.maianh")
    assert (await beat(cs, world)).status_code == 204
    assert await viewers(cs, world) == []
