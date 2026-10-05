"""``SqlCareStore`` over Postgres as the worker role (package M, step M2a). New tests.

Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). The worker reads and writes ``agent.*`` and sees the
patient code only through the view ``clinic_agent.patient_ref``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.loop import CareEventBus, CareTurnRunner, TurnStatus
from pema.care.models import ControlState
from pema.care.pairing import ensure_care_agent
from pema.care.ports import HarnessDecision
from pema.care.priority import CarePriorityQueue
from pema.care.store import SqlCareStore
from pema.care.testing import (
    FakeChannel,
    FakeClock,
    FakeContextLoader,
    FakeGuard,
    FakeHarness,
    FakeReview,
    FakeScheduler,
    FixedWindow,
    vn,
)
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db


async def _pair(db: ClinicDatabase, world: SeedResult, code: str = "P025") -> UUID:
    async with db.session() as session:
        return (await ensure_care_agent(session, world.patients[code])).id


async def test_the_store_reads_a_care_agent_and_defaults_the_state_to_auto(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _pair(db, world)
    store = SqlCareStore(worker_db)
    agent = await store.get_care_agent(care_agent_id)
    assert agent is not None
    assert (agent.patient_id, agent.profile, agent.paused) == (
        world.patients["P025"],
        "patient_channel",
        False,
    )
    assert await store.get_control_state(agent.patient_id) is ControlState.AUTO
    assert await store.get_care_agent(uuid4()) is None


async def test_the_store_reads_the_control_state(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await _pair(db, world)
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.conversation_control (clinic_id, patient_id, state, staff_owner) "
                "VALUES (:c, :p, 'STAFF', :u)"
            ),
            {"c": world.clinic_id, "p": world.patients["P025"], "u": world.users["cs.maianh"]},
        )
    assert await SqlCareStore(worker_db).get_control_state(world.patients["P025"]) is ControlState.STAFF


async def test_the_store_finds_the_care_agent_by_patient_code_through_the_view(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _pair(db, world)
    store = SqlCareStore(worker_db)
    assert await store.care_agent_id_for("P025") == care_agent_id
    assert await store.care_agent_id_for("P999") is None
    assert await store.care_agent_id_for("P026") is None  # exists but not paired yet


async def test_record_action_and_touch_last_tick(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    first = await _pair(db, world, "P025")
    second = await _pair(db, world, "P026")
    store = SqlCareStore(worker_db)
    at = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)
    await store.record_action(
        first, action_type="send:paused_proactive_cap", disposition="paused", depth="D1", at=at
    )
    await store.touch_last_tick([first, second], at)
    with admin.connect() as conn:
        rows = conn.execute(text("SELECT action_type, disposition, depth, at FROM agent.actions_log")).all()
        ticks = conn.execute(text("SELECT last_tick_at, version FROM agent.care_agents")).all()
    assert [(r.action_type, r.disposition, r.depth, r.at) for r in rows] == [
        ("send:paused_proactive_cap", "paused", "D1", at)
    ]
    assert [(t.last_tick_at, t.version) for t in ticks] == [(at, 2), (at, 2)]
    with pytest.raises(IntegrityError):
        await store.record_action(first, action_type="x", disposition="sent", depth=None, at=at)


async def test_keyset_pages_skip_paused_agents(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    ids = sorted([await _pair(db, world, "P025"), await _pair(db, world, "P026")])
    with admin.begin() as conn:
        conn.execute(text("UPDATE agent.care_agents SET paused = true WHERE id = :i"), {"i": ids[1]})
    store = SqlCareStore(worker_db)
    page = await store.list_active_care_agents(after=None, limit=10)
    assert [a.id for a in page] == [ids[0]]
    assert await store.list_active_care_agents(after=ids[0], limit=10) == []


async def test_a_full_turn_over_the_real_store_writes_the_log_and_the_tick_time(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care_agent_id = await _pair(db, world)
    store = SqlCareStore(worker_db)
    harness = FakeHarness(HarnessDecision(text="Nhắc (mẫu)", depth="D1"))
    clock = FakeClock(vn(2026, 10, 3, 22, 0))
    runner = CareTurnRunner(
        store=store,
        context_loader=FakeContextLoader(),
        harness=harness,
        channel=FakeChannel(),
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=FixedWindow(),
        guard=FakeGuard(),
        clock=clock,
        cap_per_day=2,
    )
    queue = CarePriorityQueue()
    published = await CareEventBus(store, queue).publish(
        CareEvent(
            kind=EventKind.DORMANT, initiator=Initiator.SYSTEM, patient_ref="P025", occurred_at=clock.now
        )
    )
    assert published
    item = queue.pop_nowait()
    assert item is not None
    assert item.care_agent_id == care_agent_id
    outcome = await runner.run_turn(item.care_agent_id, item.event)
    assert outcome.status is TurnStatus.DRAFTED  # default autonomy is L0
    with admin.connect() as conn:
        log = conn.execute(text("SELECT action_type, disposition, depth FROM agent.actions_log")).all()
        tick = conn.execute(text("SELECT last_tick_at FROM agent.care_agents")).scalar_one()
    assert [(r.action_type, r.disposition, r.depth) for r in log] == [("draft:autonomy", "paused", "D1")]
    assert tick == clock.now
    assert tick == vn(2026, 10, 3, 22, 0)
