"""Live events and presence of the assignment (package O, step O2). New tests (no zalo-agent original).

Need ``PEMA_TEST_DATABASE_URL``. The live services are the in-memory ones (no Redis), wired the way the
composition root does it. Covered: ``assignment.changed`` after a claim, a takeover, a release, a send that
claims and the "Phụ trách" box (and nothing for a no-op or a refused call), who may receive the event type, and
the holder reported apart from the viewers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import record_inbound
from pema.api.live_access import EVENT_PERMISSION
from pema.clinic.actions import FakeOutboundDelivery, assignment, conversations
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema.live.bus import InMemoryLiveEventBus
from pema.live.presence import InMemoryPresenceStore
from pema.live.publisher import install_live_publisher
from pema.live.services import LiveServices, build_memory_live_services
from pema_contracts.conversations import ConversationUpdate, MessageCreate
from pema_contracts.errors import DomainError
from pema_contracts.live import LiveEventType
from pema_contracts.ops import TakeoverRequest
from pema_contracts.roles import Permission

pytestmark = pytest.mark.db


@pytest.fixture
def bus() -> InMemoryLiveEventBus:
    return InMemoryLiveEventBus()


@pytest_asyncio.fixture
async def live(app: FastAPI, bus: InMemoryLiveEventBus) -> AsyncIterator[LiveServices]:
    services = build_memory_live_services(bus=bus, store=InMemoryPresenceStore(), max_per_user=2)
    app.state.live = services
    install_live_publisher(services.publisher)
    services.hub.start()
    yield services
    install_live_publisher(None)
    await services.aclose()


async def thread(db: ClinicDatabase, world: SeedResult) -> UUID:
    ref = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    return ref.conversation_id


def seen(bus: InMemoryLiveEventBus, event_type: LiveEventType) -> list[UUID | None]:
    return [event.id for event in bus.published if event.type is event_type]


def test_the_assignment_event_goes_to_whoever_may_read_conversations() -> None:
    assert EVENT_PERMISSION[LiveEventType.ASSIGNMENT_CHANGED] is Permission.CONVERSATION_READ


async def test_a_claim_and_a_takeover_announce_the_conversation_and_a_no_op_announces_nothing(
    live: LiveServices,
    bus: InMemoryLiveEventBus,
    db: ClinicDatabase,
    world: SeedResult,
    staff_ctx: Any,
) -> None:
    cid = await thread(db, world)
    mai, thu = staff_ctx("cs.maianh"), staff_ctx("cs.thu")
    await assignment.claim(db, mai, cid)
    await live.publisher.flush()
    assert seen(bus, LiveEventType.ASSIGNMENT_CHANGED) == [cid]
    assert cid in seen(bus, LiveEventType.INBOX_CHANGED)

    bus.published.clear()
    await assignment.claim(db, mai, cid)  # already the holder
    with pytest.raises(DomainError):
        await assignment.claim(db, thu, cid)  # locked
    await live.publisher.flush()
    assert bus.published == []

    await assignment.takeover(db, thu, cid, TakeoverRequest(reason="Em nhận giúp chị"))
    await live.publisher.flush()
    assert seen(bus, LiveEventType.ASSIGNMENT_CHANGED) == [cid]

    bus.published.clear()
    await assignment.release(db, thu, cid)
    await live.publisher.flush()
    assert seen(bus, LiveEventType.ASSIGNMENT_CHANGED) == [cid]


async def test_a_reply_that_claims_and_the_phu_trach_box_announce_it_too(
    live: LiveServices,
    bus: InMemoryLiveEventBus,
    db: ClinicDatabase,
    world: SeedResult,
    staff_ctx: Any,
) -> None:
    first, second = await thread(db, world), await thread(db, world)
    thu, manager = staff_ctx("cs.thu"), staff_ctx("manager")
    await conversations.send_message(
        db, thu, first, MessageCreate(text="Chào bạn (tin mẫu)"), delivery=FakeOutboundDelivery()
    )
    await live.publisher.flush()
    assert seen(bus, LiveEventType.ASSIGNMENT_CHANGED) == [first]

    bus.published.clear()
    version = (await conversations.get_conversation(db, manager, second)).version
    await conversations.update_conversation(
        db, manager, second, ConversationUpdate(version=version, assigned_user_id=world.users["cs.thu"])
    )
    await live.publisher.flush()
    assert seen(bus, LiveEventType.ASSIGNMENT_CHANGED) == [second]


async def test_the_holder_is_reported_apart_from_the_viewers(
    live: LiveServices,
    client_factory: Any,
    db: ClinicDatabase,
    admin: Engine,
    world: SeedResult,
) -> None:
    cid = await thread(db, world)
    base = f"/api/v1/conversations/{cid}"
    mai = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    manager = await client_factory("manager")

    assert (await mai.post(f"{base}/claim")).status_code == 200
    assert (await mai.post(f"{base}/presence", json={"state": "replying"})).status_code == 204
    assert (await manager.post(f"{base}/presence", json={"state": "viewing"})).status_code == 204

    seen_by_thu = (await thu.get(base)).json()
    assert seen_by_thu["holder_presence"] == "replying"
    assert [viewer["state"] for viewer in seen_by_thu["viewers"]] == ["viewing"]
    assert seen_by_thu["assigned_user_name"]

    seen_by_holder = (await mai.get(base)).json()
    assert seen_by_holder["holder_presence"] == "replying", "the holder sees their own state too"
    assert [viewer["state"] for viewer in seen_by_holder["viewers"]] == ["viewing"]

    listed = (await thu.get("/api/v1/conversations", params={"limit": 200})).json()["items"]
    row = next(item for item in listed if item["id"] == str(cid))
    assert row["holder_presence"] == "replying"
    assert all(viewer["user_id"] != row["assigned_user_id"] for viewer in row["viewers"])

    with admin.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic.conversation_assignment")).scalar_one() == 1
