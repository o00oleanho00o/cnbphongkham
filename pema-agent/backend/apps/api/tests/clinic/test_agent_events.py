"""The outbox of what the agent must hear, and its worker (docs/PLAN-crm-plugin.md 3.4, 3.7).

An event is written in the transaction of the change it tells about, only for a person linked to a chat, with
ids, times and statuses only; the worker sends them in order, signed with the clinic's key, tries again after
a failure with a growing wait, stops after eight, and is woken by a commit instead of looking on a timer.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from sqlalchemy.engine import Engine

from pema.api import agent_token
from pema.api.clinic_testing import ClientFactory
from pema.api.gateway_testing import Save, at, book, free_day, rows
from pema.clinic.actions import agent_events
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.models.agent_event import AgentEvent
from pema.composition import agent_events_worker as worker_module
from pema.composition.agent_events_worker import AgentEventWorker
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType

pytestmark = pytest.mark.db

URL = "http://agent.test/v1/hooks/crm/events"


@pytest.fixture
def events_on(gateway_on: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_AGENT_EVENTS_URL", URL)
    get_settings.cache_clear()
    yield
    agent_events.set_waker(None)
    get_settings.cache_clear()


def events(admin: Engine, kind: str | None = None) -> list[dict[str, Any]]:
    found = rows(
        admin,
        "SELECT kind, payload, delivered_at, attempts FROM clinic.agent_event "
        "WHERE (CAST(:k AS text) IS NULL OR kind = :k) ORDER BY id",
        k=kind,
    )
    return [{"kind": r[0], "payload": r[1], "delivered_at": r[2], "attempts": r[3]} for r in found]


# ------------------------------------------------------------------ what is written, and when


async def test_a_booking_of_a_linked_person_leaves_one_event_with_the_whole_state(
    events_on: None, agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved(consent=True)
    visit = (await book(agent, path, at(free_day(), 9))).json()
    changed = events(admin, "appointment.changed")
    assert len(changed) == 1
    payload = changed[0]["payload"]
    assert payload["appointment_id"] == visit["id"]
    assert (payload["channel"], payload["external_id"]) == ("zalo-test", path.rsplit("/", 1)[1])
    assert (payload["status"], payload["version"], payload["duration_min"]) == ("booked", 1, 30)
    assert payload["messages_consent"] is True
    assert payload["actor_type"] == "agent"
    assert payload["starts_at"].endswith("+07:00")
    flat = str(payload)
    assert "Khách thử" not in flat
    assert "0912000111" not in flat


async def test_each_change_of_a_visit_leaves_an_event_with_a_higher_version(
    events_on: None, agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    day = free_day()
    visit = (await book(agent, path, at(day, 9))).json()
    base = f"{path}/appointments/{visit['id']}"
    await agent.post(f"{base}/confirm")
    await agent.post(f"{base}/reschedule", json={"starts_at": at(day, 10)}, headers={"Idempotency-Key": "m1"})
    await agent.post(f"{base}/cancel", json={"reason": "bận"})
    seen = [(e["payload"]["status"], e["payload"]["version"]) for e in events(admin, "appointment.changed")]
    assert seen == [("booked", 1), ("confirmed", 2), ("confirmed", 3), ("cancelled", 4)]
    moved = events(admin, "appointment.changed")[2]["payload"]
    assert moved["starts_at"][11:16] == "10:00"


async def test_a_change_by_staff_is_marked_as_a_user(
    events_on: None,
    agent: httpx.AsyncClient,
    saved: Save,
    admin: Engine,
    client_factory: ClientFactory,
) -> None:
    path = await saved()
    visit = (await book(agent, path, at(free_day(), 9))).json()
    reception = await client_factory("reception.lan")
    done = await reception.post(f"/api/v1/appointments/{visit['id']}/confirm", json={"version": 1})
    assert done.status_code == 200, done.text
    last = events(admin, "appointment.changed")[-1]["payload"]
    assert (last["status"], last["actor_type"]) == ("confirmed", "user")


async def test_a_person_who_is_not_linked_leaves_no_event(
    events_on: None, client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    response = await reception.post(
        "/api/v1/appointments",
        json={"patient_id": str(world.patients["P027"]), "starts_at": at(free_day(), 9), "duration_min": 30},
    )
    assert response.status_code == 201, response.text
    assert events(admin) == []


async def test_nothing_is_written_without_the_events_url(
    gateway_on: None, agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved(consent=True)
    assert (await book(agent, path, at(free_day(), 9))).status_code == 201
    assert events(admin) == []


async def test_the_consent_of_a_linked_person_leaves_a_person_event_from_either_side(
    events_on: None,
    agent: httpx.AsyncClient,
    saved: Save,
    admin: Engine,
    client_factory: ClientFactory,
) -> None:
    path = await saved(consent=True)  # the agent: granted
    patient = rows(
        admin,
        "SELECT patient_id FROM clinic.patient_channel WHERE external_id = :e",
        e=path.rsplit("/", 1)[1],
    )[0][0]
    reception = await client_factory("reception.lan")
    base = f"/api/v1/patients/{patient}/consents"
    await reception.post(base, json={"kind": "messaging", "granted": False, "source": "desk"})
    await reception.post(base, json={"kind": "marketing", "granted": False, "source": "desk"})
    people = events(admin, "person.changed")
    assert [(e["payload"]["messages_consent"], e["payload"]["actor_type"]) for e in people] == [
        (True, "agent"),
        (False, "user"),
    ]
    assert set(people[0]["payload"]) == {
        "channel",
        "external_id",
        "messages_consent",
        "actor_type",
        "occurred_at",
    }


async def test_a_change_that_rolls_back_leaves_no_event(
    events_on: None, saved: Save, admin: Engine, db: ClinicDatabase, world: SeedResult
) -> None:
    path = await saved()
    patient = rows(
        admin,
        "SELECT patient_id FROM clinic.patient_channel WHERE external_id = :e",
        e=path.rsplit("/", 1)[1],
    )[0][0]
    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)
    with pytest.raises(RuntimeError):
        async with db.session() as session:
            await agent_events.record_person_changed(session, ctx, patient, messages_consent=True)
            raise RuntimeError("the change failed after the event was added")
    assert events(admin) == []


# ------------------------------------------------------------------ the worker


class Clock:
    """The real time, moved forward by ``offset`` (rows get the database's own ``now()``)."""

    def __init__(self) -> None:
        self.offset = timedelta()

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.offset


async def add_events(db: ClinicDatabase, clinic_id: UUID, count: int = 1, **fields: Any) -> list[UUID]:
    ids: list[UUID] = []
    async with db.session() as session:
        for number in range(count):
            row = AgentEvent(
                clinic_id=clinic_id,
                event_id=uuid4(),  # set here: the column default only runs at the flush
                kind="appointment.changed",
                payload={"appointment_id": str(uuid4()), "status": "booked", "version": number + 1},
                **fields,
            )
            session.add(row)
            ids.append(row.event_id)
    return ids


def signer_key(tmp_path: Path) -> agent_token.SigningKey:
    return agent_token.load_or_create_key(tmp_path)


class Agent:
    """What the agent answers: a status code, or a refused connection."""

    def __init__(self, status: int | None = 200) -> None:
        self.status = status
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.status is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(self.status)

    @property
    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))


def make_worker(
    db: ClinicDatabase, tmp_path: Path, agent: Agent, clock: Clock | None = None
) -> AgentEventWorker:
    return AgentEventWorker(
        db,
        URL,
        key=lambda: signer_key(tmp_path),
        transport=httpx.MockTransport(agent),
        clock=clock or Clock(),
    )


def state(admin: Engine) -> list[Any]:
    return rows(
        admin,
        "SELECT event_id, attempts, delivered_at, failed_at, next_attempt_at, last_error "
        "FROM clinic.agent_event ORDER BY id",
    )


async def test_the_worker_sends_in_the_order_of_id_and_marks_delivered(
    db: ClinicDatabase, world: SeedResult, admin: Engine, tmp_path: Path
) -> None:
    ids = await add_events(db, world.clinic_id, 3)
    agent = Agent()
    worker = make_worker(db, tmp_path, agent)
    async with agent.http as http:
        done = await worker.deliver_due(http)
    assert (done.sent, done.failed, done.next_due) == (3, 0, None)
    key = signer_key(tmp_path).private.public_key()
    sent = [
        jwt.decode(
            r.headers["authorization"].removeprefix("Bearer "),
            key,
            algorithms=["EdDSA"],
            audience="pema-agent-events",
        )["jti"]
        for r in agent.calls
    ]
    assert sent == [str(i) for i in ids]
    assert all(row[2] is not None and row[1] == 1 for row in state(admin))


async def test_an_event_is_a_short_token_only_the_clinics_key_can_make(
    db: ClinicDatabase, world: SeedResult, tmp_path: Path
) -> None:
    (event_id,) = await add_events(db, world.clinic_id)
    agent = Agent()
    async with agent.http as http:
        await make_worker(db, tmp_path, agent).deliver_due(http)
    token = agent.calls[0].headers["authorization"].removeprefix("Bearer ")
    sk = signer_key(tmp_path)
    claims = jwt.decode(token, sk.private.public_key(), algorithms=["EdDSA"], audience="pema-agent-events")
    assert claims["iss"] == "pema-clinic"
    assert claims["jti"] == str(event_id)
    assert claims["exp"] - claims["iat"] == 120
    assert claims["event"]["kind"] == "appointment.changed"
    assert claims["event"]["status"] == "booked"
    assert jwt.get_unverified_header(token)["kid"] == sk.kid
    with pytest.raises(jwt.InvalidAudienceError):  # the agent's SSO audience is not this one
        jwt.decode(token, sk.private.public_key(), algorithms=["EdDSA"], audience="pema-agent")
    assert str(agent.calls[0].url) == URL


async def test_a_failed_try_waits_and_a_later_round_delivers(
    db: ClinicDatabase, world: SeedResult, admin: Engine, tmp_path: Path
) -> None:
    await add_events(db, world.clinic_id)
    clock = Clock()
    failing, working = Agent(500), Agent(200)
    async with failing.http as http:
        first = await make_worker(db, tmp_path, failing, clock).deliver_due(http)
        again = await make_worker(db, tmp_path, failing, clock).deliver_due(http)
    assert (first.failed, again.failed, len(failing.calls)) == (1, 0, 1)  # not due yet: not tried again
    (row,) = state(admin)
    assert (row[1], row[5]) == (1, "HTTP 500")
    wait = (row[4] - datetime.now(UTC)).total_seconds()
    assert worker_module.RETRY_BASE_S - 5 < wait <= worker_module.RETRY_BASE_S
    clock.offset = timedelta(seconds=worker_module.RETRY_BASE_S + 2)
    async with working.http as http:
        last = await make_worker(db, tmp_path, working, clock).deliver_due(http)
    assert (last.sent, state(admin)[0][2] is not None) == (1, True)


async def test_after_eight_failed_tries_the_row_is_left_alone(
    db: ClinicDatabase, world: SeedResult, admin: Engine, tmp_path: Path
) -> None:
    await add_events(db, world.clinic_id)
    clock, agent = Clock(), Agent(503)
    worker = make_worker(db, tmp_path, agent, clock)
    async with agent.http as http:
        for _ in range(worker_module.MAX_ATTEMPTS + 2):
            await worker.deliver_due(http)
            clock.offset += timedelta(seconds=worker_module.RETRY_CAP_S + 1)
    (row,) = state(admin)
    assert (row[1], row[3] is not None, len(agent.calls)) == (worker_module.MAX_ATTEMPTS, True, 8)


async def test_a_refused_connection_ends_the_round_at_once(
    db: ClinicDatabase, world: SeedResult, admin: Engine, tmp_path: Path
) -> None:
    await add_events(db, world.clinic_id, 3)
    agent = Agent(None)
    async with agent.http as http:
        done = await make_worker(db, tmp_path, agent).deliver_due(http)
    assert (done.sent, done.failed, len(agent.calls)) == (0, 1, 1)
    assert [row[1] for row in state(admin)] == [1, 0, 0]


async def test_old_delivered_and_failed_rows_are_deleted_and_recent_ones_kept(
    db: ClinicDatabase, world: SeedResult, admin: Engine, tmp_path: Path
) -> None:
    now = datetime.now(UTC)
    await add_events(db, world.clinic_id, delivered_at=now - timedelta(days=8))
    await add_events(db, world.clinic_id, delivered_at=now - timedelta(days=1))
    await add_events(db, world.clinic_id, failed_at=now - timedelta(days=31))
    await add_events(db, world.clinic_id, failed_at=now - timedelta(days=2))
    await add_events(db, world.clinic_id)
    await make_worker(db, tmp_path, Agent()).cleanup()
    assert len(state(admin)) == 3


async def test_a_commit_wakes_the_worker_and_the_event_is_delivered_without_a_timer(
    events_on: None,
    agent: httpx.AsyncClient,
    saved: Save,
    admin: Engine,
    db: ClinicDatabase,
    tmp_path: Path,
) -> None:
    receiver = Agent()
    worker = make_worker(db, tmp_path, receiver)
    agent_events.set_waker(worker.wake)
    task = asyncio.create_task(worker.run())
    try:
        await asyncio.sleep(0.3)  # the worker has found nothing and sleeps with no timeout
        path = await saved(consent=True)
        await book(agent, path, at(free_day(), 9))
        for _ in range(50):
            if len(receiver.calls) >= 2:
                break
            await asyncio.sleep(0.2)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    assert len(receiver.calls) == 2  # the consent and the booking
    assert all(e["delivered_at"] is not None for e in events(admin))


async def test_the_worker_outlives_a_broken_round(
    db: ClinicDatabase, world: SeedResult, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = make_worker(db, tmp_path, Agent())
    monkeypatch.setattr(worker_module, "CRASH_PAUSE_S", 0.05)

    async def broken(_http: httpx.AsyncClient) -> Any:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(worker, "deliver_due", broken)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.4)
    assert not task.done()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
