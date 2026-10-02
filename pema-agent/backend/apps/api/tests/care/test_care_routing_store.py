"""Routing, the on-call contact and paused reminders over Postgres (package M, step M2c).

New tests. Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). The agent side runs as the worker role
(``agent_worker``: reads the views ``clinic_agent.staff_profile`` ... and writes ``agent.*``), the API side as
``be_app`` (reads the tables). Single tenant: no row level security; the guards under test are the table
CHECKs, the compare-and-set on ``current_idx``, the conditional UPDATE of ``paused_reminders`` and the grants.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from pema.care.control import CareControl
from pema.care.control_store import SqlControlStore
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import SqlHandoffConfigSource
from pema.care.handoff_types import Depth, HandoffAction, HandoffDecision, Urgency
from pema.care.models import ControlState
from pema.care.oncall import OnCallDirectory
from pema.care.patient_notices import PatientNotices
from pema.care.ports import CareAgentSnapshot, ChannelTarget, HandoffSpec, PatientContext
from pema.care.reminder_store import SqlReminderStore
from pema.care.reminders import ReminderService
from pema.care.routing import RoutingService
from pema.care.routing_store import (
    SqlOnCallSource,
    SqlRoutingConfigSource,
    SqlRoutingDirectory,
    SqlRoutingStore,
)
from pema.care.routing_types import (
    CandidateKind,
    CandidateStatus,
    NewPausedReminder,
    ReminderStatus,
    RoutingConfig,
    candidates_from_json,
)
from pema.care.seed import FIXTURE_ON_CALL_NUMBER, seed_care_dev
from pema.care.store import SqlCareStore
from pema.care.testing import FakeChannel, FakeClock, FixedWindow
from pema.care.testing_routing import FakeSlaScheduler, FakeStaffNotify, RecordingPublisher, staff_context
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

API_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # Monday 10:00 clinic time
DAY = timedelta(days=1)


def _rows(admin: Engine, sql: str, **params: object) -> list[tuple[object, ...]]:
    with admin.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params).all()]


async def _seed(db: ClinicDatabase, world: SeedResult) -> dict[str, UUID]:
    seeded = await seed_care_dev(db, users=world.users, patients=world.patients)
    return dict(seeded.care_agents)


async def _agent(worker_db: ClinicDatabase, care_agent_id: UUID) -> CareAgentSnapshot:
    agent = await SqlCareStore(worker_db).get_care_agent(care_agent_id)
    assert agent is not None
    return agent


def _spec(depth: str = "D2", urgency: str = "normal") -> HandoffSpec:
    return HandoffSpec(
        reason="depth_at_or_above_threshold",
        summary="Khách: P025\nĐộ sâu: " + depth,
        depth=depth,
        confidence=0.7,
        required_skill="general",
        urgency=urgency,
    )


class Wiring:
    """The M2c services over Postgres with fake notification, SLA scheduler and channel."""

    def __init__(self, worker_db: ClinicDatabase, db: ClinicDatabase, now: datetime = NOW) -> None:
        self.clock = FakeClock(now)
        self.store = SqlRoutingStore(worker_db)
        self.config = SqlRoutingConfigSource(worker_db)
        self.oncall = OnCallDirectory(SqlOnCallSource(worker_db), self.store)
        self.notifier = FakeStaffNotify()
        self.sla = FakeSlaScheduler()
        self.window = FixedWindow()
        self.service = RoutingService(
            store=self.store,
            directory=SqlRoutingDirectory(worker_db),
            oncall=self.oncall,
            config_source=self.config,
            notifier=self.notifier,
            sla=self.sla,
            window=self.window,
            clock=self.clock,
        )
        self.controls = SqlControlStore(worker_db)
        self.channel = FakeChannel()
        self.publisher = RecordingPublisher()
        self.reminder_store = SqlReminderStore(worker_db)
        self.reminders = ReminderService(
            store=self.reminder_store,
            config_source=self.config,
            directory=SqlRoutingDirectory(worker_db),
            controls=self.controls,
            recorder=self.store,
            publisher=self.publisher,
            clock=self.clock,
        )
        self.control = CareControl(
            store=self.controls,
            config_source=SqlHandoffConfigSource(worker_db),
            channel=self.channel,
            clock=self.clock,
            routing=self.service,
            routing_start=self.service,
            notices=PatientNotices(config_source=self.config, window=self.window, oncall=self.oncall),
            reminders=self.reminders,
        )

    async def open_round(self, agent: CareAgentSnapshot, depth: Depth = Depth.D2) -> UUID:
        decision = HandoffDecision(
            action=HandoffAction.HANDOFF,
            reason="depth_at_or_above_threshold",
            depth=depth,
            confidence=0.8,
            required_skill="medical" if depth.rank >= Depth.D4.rank else "general",
            urgency=Urgency.NORMAL if depth.rank < Depth.D4.rank else Urgency.URGENT,
        )
        context = PatientContext("P025", agent.patient_id, channel=ChannelTarget("acct-fake", "thread-fake"))
        event = CareEvent(
            kind=EventKind.PATIENT_MESSAGE, initiator=Initiator.PATIENT, patient_ref="P025", occurred_at=NOW
        )
        opened = await self.control.request_handoff(agent, event, context, decision, self.clock.now)
        return opened.request.id


# ------------------------------------------------------------------------------------- config
async def test_the_routing_row_is_seeded_with_pending_defaults_and_read_on_every_use(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await _seed(db, world)
    source = SqlRoutingConfigSource(worker_db)
    config = await source.get(world.clinic_id)
    assert config == RoutingConfig()
    assert config.pending_doctor_approval
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent.skills SET classifier_config = classifier_config || '{\"sla_normal_minutes\": 45}' "
                "WHERE name = 'routing'"
            )
        )
    assert (await source.get(world.clinic_id)).sla_normal_minutes == 45  # a change applies at once
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent.skills SET classifier_config = '{\"max_candidates\": 99}' WHERE name = 'routing'"
            )
        )
    assert await source.get(world.clinic_id) == RoutingConfig()  # invalid: defaults, never an exception


async def test_without_a_row_the_defaults_apply(worker_db: ClinicDatabase, world: SeedResult) -> None:
    assert await SqlRoutingConfigSource(worker_db).get(world.clinic_id) == RoutingConfig()


# ------------------------------------------------------------------------------------ directory
async def test_the_worker_reads_staff_and_owners_through_the_views_and_the_api_through_the_tables(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    await _seed(db, world)
    for directory in (SqlRoutingDirectory(worker_db), SqlRoutingDirectory(db, role="app")):
        staff = {s.user_id: s for s in await directory.list_staff(world.clinic_id)}
        assert set(staff) == {world.users["doctor.mai"], world.users["cs.maianh"], world.users["cs.thu"]}
        doctor = staff[world.users["doctor.mai"]]
        assert doctor.role == "doctor"
        assert set(doctor.skills) == {"laser", "nam"}
        assert doctor.capacity == 5
        assert doctor.load == 0
        assert "mon" in doctor.shift
        owners = await directory.ownership(world.patients["P025"])
        assert owners.cs_owner == world.users["cs.maianh"]
        assert owners.doctor == world.users["doctor.mai"]
        assert (await directory.ownership(uuid4())).cs_owner is None


async def test_the_load_of_a_person_is_the_number_of_staff_conversations_she_owns(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care = await _seed(db, world)
    wiring = Wiring(worker_db, db)
    agent = await _agent(worker_db, care["P025"])
    await wiring.controls.open_handoff(agent, _spec(), log_action="x", at=NOW)
    await wiring.controls.accept(
        agent.patient_id, world.users["cs.maianh"], log_action="control:accepted", at=NOW
    )
    staff = {s.user_id: s for s in await SqlRoutingDirectory(worker_db).list_staff(world.clinic_id)}
    assert staff[world.users["cs.maianh"]].load == 1
    assert staff[world.users["cs.thu"]].load == 0


async def test_the_on_call_contact_comes_from_the_database_on_every_call(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await _seed(db, world)
    directory = OnCallDirectory(SqlOnCallSource(worker_db))
    current = await directory.current_on_call(world.clinic_id, NOW)
    assert current is not None
    assert (current.zalo_number, current.is_fixture) == (FIXTURE_ON_CALL_NUMBER, True)
    with admin.begin() as conn:  # the dashboard edit
        conn.execute(text("UPDATE clinic.on_call_contacts SET zalo_number = '0000000002'"))
    changed = await directory.current_on_call(world.clinic_id, NOW)
    assert changed is not None
    assert changed.zalo_number == "0000000002"
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.on_call_contacts SET active = false"))
    assert await directory.current_on_call(world.clinic_id, NOW) is None
    assert len(await SqlOnCallSource(db, role="app").active_contacts(world.clinic_id)) == 0


# --------------------------------------------------------------------------------------- store
async def test_save_routing_is_a_compare_and_set_that_closes_with_the_outcome(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    controls = SqlControlStore(worker_db)
    opened = await controls.open_handoff(agent, _spec(), log_action="x", at=NOW)
    store = SqlRoutingStore(worker_db)
    chain = [{"kind": "staff", "n": 1}, {"kind": "on_call", "n": 2}]

    saved = await store.save_routing(
        opened.request.id,
        expected_idx=0,
        candidates=chain,
        current_idx=1,
        notified_at=NOW,
        outcome=None,
        log_action="routing:test:1",
        at=NOW,
    )
    assert saved is not None
    assert (saved.current_idx, saved.current_notified_at, saved.outcome) == (1, NOW, None)
    assert saved.candidates == tuple(chain)
    stale = await store.save_routing(
        opened.request.id,
        expected_idx=0,
        candidates=chain,
        current_idx=2,
        notified_at=NOW,
        outcome=None,
        log_action="routing:never",
        at=NOW,
    )
    assert stale is None
    closed = await store.save_routing(
        opened.request.id,
        expected_idx=1,
        candidates=chain,
        current_idx=1,
        notified_at=NOW,
        outcome="exhausted_to_oncall",
        log_action="routing:end",
        at=NOW,
    )
    assert closed is not None
    assert closed.outcome == "exhausted_to_oncall"
    assert (
        await store.save_routing(
            opened.request.id,
            expected_idx=1,
            candidates=chain,
            current_idx=1,
            notified_at=NOW,
            outcome=None,
            log_action="routing:after",
            at=NOW,
        )
        is None
    )  # closed
    log = [r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log ORDER BY id")]
    assert log == ["x", "routing:test:1", "routing:end"]
    assert _rows(admin, "SELECT resolved_at FROM agent.handoff_requests")[0][0] == NOW


async def test_two_callers_that_race_for_the_same_step_advance_the_request_once(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    opened = await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    store = SqlRoutingStore(worker_db)

    async def step() -> object:
        return await store.save_routing(
            opened.request.id,
            expected_idx=0,
            candidates=[{"kind": "staff"}, {"kind": "on_call"}],
            current_idx=1,
            notified_at=NOW,
            outcome=None,
            log_action="routing:step",
            at=NOW,
        )

    results = await asyncio.gather(*[step() for _ in range(5)])
    assert sum(r is not None for r in results) == 1


async def test_unresolved_requests_are_listed_oldest_first_without_the_closed_ones(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care = await _seed(db, world)
    first = await _agent(worker_db, care["P025"])
    second = await _agent(worker_db, care["P026"])
    controls = SqlControlStore(worker_db)
    one = await controls.open_handoff(first, _spec(), log_action="x", at=NOW)
    two = await controls.open_handoff(second, _spec(), log_action="x", at=NOW + timedelta(minutes=1))
    store = SqlRoutingStore(worker_db)
    assert [r.id for r in await store.list_unresolved_requests(limit=10)] == [one.request.id, two.request.id]
    await store.save_routing(
        one.request.id,
        expected_idx=0,
        candidates=[{"kind": "on_call"}],
        current_idx=0,
        notified_at=NOW,
        outcome="exhausted_to_oncall",
        log_action="routing:end",
        at=NOW,
    )
    assert [r.id for r in await store.list_unresolved_requests(limit=10)] == [two.request.id]
    assert [r.clinic_id for r in await store.list_unresolved_requests(limit=10)] == [world.clinic_id]


# --------------------------------------------------------------------- routing end to end on Postgres
async def test_the_whole_chain_over_postgres_ends_with_the_on_call_contact_and_staff_can_still_accept(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    wiring = Wiring(worker_db, db)
    request_id = await wiring.open_round(agent)
    request = await wiring.store.get_request(request_id)
    assert request is not None
    chain = candidates_from_json(request.candidates)
    # the CS owner, the treating doctor (owners first), then the one who is on shift, then on-call
    assert [c.user_id for c in chain] == [
        world.users["cs.maianh"],
        world.users["doctor.mai"],
        world.users["cs.thu"],
        None,
    ]
    assert chain[-1].kind is CandidateKind.ON_CALL
    assert chain[0].sla_due_at == NOW + timedelta(minutes=30)
    assert wiring.sla.last.idx == 0

    owner_ctx = staff_context(world.users["cs.maianh"])
    await wiring.control.decline(
        owner_ctx, agent.patient_id, "không đúng chuyên môn, gọi 0912345678", world.users["cs.thu"]
    )
    request = await wiring.store.get_request(request_id)
    assert request is not None
    chain = candidates_from_json(request.candidates)
    assert [c.user_id for c in chain][:2] == [world.users["cs.maianh"], world.users["cs.thu"]]
    assert chain[0].status is CandidateStatus.DECLINED
    assert chain[0].decline_reason is not None
    assert "0912345678" not in chain[0].decline_reason
    stored = _rows(admin, "SELECT candidates::text FROM agent.handoff_requests")[0][0]
    assert "0912345678" not in str(stored)  # masked before it reached the database

    wiring.clock.advance(timedelta(minutes=31))
    assert await wiring.service.sweep_overdue() == 1  # cs.thu did not answer
    wiring.clock.advance(timedelta(minutes=31))
    await wiring.service.on_sla_expired(request_id, 2)  # doctor.mai too (the check of S)
    request = await wiring.store.get_request(request_id)
    assert request is not None
    assert request.outcome == "exhausted_to_oncall"
    assert [c.status for c in candidates_from_json(request.candidates)] == [
        CandidateStatus.DECLINED,
        CandidateStatus.EXPIRED,
        CandidateStatus.EXPIRED,
        CandidateStatus.NOTIFIED,
    ]
    ((contact, _),) = wiring.notifier.on_call
    assert contact.zalo_number == FIXTURE_ON_CALL_NUMBER
    log = [r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log ORDER BY id")]
    assert "oncall_used:chain" in log
    assert "oncall_used:notify" in log
    assert await SqlControlStore(db).get_open_request(agent.patient_id) is not None  # nobody took it yet

    # a staff member can still take it in the app
    await wiring.control.accept(staff_context(world.users["doctor.mai"], role=_doctor()), agent.patient_id)
    assert await SqlCareStore(worker_db).get_control_state(agent.patient_id) is ControlState.STAFF
    row = _rows(admin, "SELECT outcome, accepted_by FROM agent.handoff_requests")[0]
    assert row == ("accepted", world.users["doctor.mai"])
    exported = await wiring.service.export_declines(NOW - DAY)
    assert [(r.user_id, r.depth) for r in exported] == [(world.users["cs.maianh"], "D2")]


def _doctor():  # type: ignore[no-untyped-def]
    from pema_contracts.roles import Role

    return Role.DOCTOR


async def test_out_of_hours_d5_over_postgres_gives_one_template_with_the_number_of_the_database(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    wiring = Wiring(worker_db, db, now=datetime(2026, 10, 5, 15, 0, tzinfo=UTC))  # 22:00 clinic time
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.on_call_contacts SET zalo_number = '0000000042'"))
    request_id = await wiring.open_round(agent, Depth.D5)
    request = await wiring.store.get_request(request_id)
    assert request is not None
    assert [c.kind for c in candidates_from_json(request.candidates)] == [CandidateKind.ON_CALL]
    assert request.outcome == "exhausted_to_oncall"
    assert len(wiring.channel.sent) == 1
    assert "0000000042" in wiring.channel.sent[0][1]
    assert "oncall_used:patient_notice" in [
        r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log")
    ]


# ---------------------------------------------------------------------------------- paused reminders
def _new(
    care_agent_id: UUID, patient_id: UUID, clinic_id: UUID, key: str, owner: UUID | None
) -> NewPausedReminder:
    return NewPausedReminder(
        clinic_id=clinic_id,
        care_agent_id=care_agent_id,
        patient_id=patient_id,
        patient_ref="P025",
        kind=EventKind.MILESTONE_DUE,
        rule="d3",
        due_at=NOW,
        dedupe_key=key,
        prepared_text="Mẫu (ví dụ)",
        owner_user_id=owner,
        payload={"anchor": "S1"},
        paused_at=NOW,
    )


async def test_the_reminder_store_dedupes_lists_and_resolves_once(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    owner = world.users["cs.maianh"]
    store = SqlReminderStore(worker_db)
    item = _new(agent.id, agent.patient_id, agent.clinic_id, "k1", owner)
    assert await store.add(item)
    assert not await store.add(item)  # the same reminder twice is one row
    (paused,) = await store.list_paused(agent.id)
    assert (paused.rule, paused.kind, paused.status) == ("d3", EventKind.MILESTONE_DUE, ReminderStatus.PAUSED)
    assert paused.payload == {"anchor": "S1"}
    assert paused.prepared_text == "Mẫu (ví dụ)"
    assert [r.id for r in await store.list_for_owner(owner, limit=5)] == [paused.id]
    assert await store.list_for_owner(world.users["cs.thu"], limit=5) == []

    results = await asyncio.gather(
        *[store.resolve(paused.id, ReminderStatus.RESUMED, "resumed", NOW) for _ in range(4)]
    )
    assert sum(results) == 1  # exactly one caller wins
    assert not await store.resolve(paused.id, ReminderStatus.DROPPED, "late", NOW)
    assert await store.list_paused(agent.id) == []
    row = _rows(admin, "SELECT status, resolution, resolved_at, version FROM agent.paused_reminders")[0]
    assert row[:3] == ("resumed", "resumed", NOW)
    assert row[3] == 2


async def test_both_runtime_roles_can_write_paused_reminders(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    assert await SqlReminderStore(worker_db).add(_new(agent.id, agent.patient_id, agent.clinic_id, "w", None))
    assert await SqlReminderStore(db).add(_new(agent.id, agent.patient_id, agent.clinic_id, "a", None))
    assert len(await SqlReminderStore(db).list_paused(agent.id)) == 2


async def test_reminders_are_paused_in_staff_and_judged_on_release_over_postgres(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care = await _seed(db, world)
    agent = await _agent(worker_db, care["P025"])
    wiring = Wiring(worker_db, db)
    await wiring.open_round(agent)
    me = world.users["cs.maianh"]
    await wiring.control.accept(staff_context(me), agent.patient_id)

    for rule, hours in (("d1", 0), ("d3", 48)):
        event = CareEvent(
            kind=EventKind.MILESTONE_DUE,
            initiator=Initiator.SYSTEM,
            patient_ref="P025",
            payload={"rule": rule},
            occurred_at=NOW + timedelta(hours=hours),
        )
        assert await wiring.reminders.pause_event(agent, event, NOW)
        assert await wiring.reminders.pause_event(agent, event, NOW)  # a repeat: still one row
    assert _rows(admin, "SELECT count(*) FROM agent.paused_reminders")[0][0] == 2
    assert {r.owner_user_id for r in await wiring.reminder_store.list_paused(agent.id)} == {me}

    wiring.clock.advance(timedelta(hours=60))  # D+1 is 60 h late and D+3 has passed; D+3 is 12 h late
    await wiring.control.release_to_auto(staff_context(me), agent.patient_id, "xong")
    status = dict(_rows(admin, "SELECT rule, status FROM agent.paused_reminders"))  # type: ignore[arg-type]
    assert status == {"d1": "dropped", "d3": "resumed"}
    (event,) = wiring.publisher.events
    assert event.payload["rule"] == "d3"
    assert event.payload["late_original_at"] == (NOW + timedelta(hours=48)).isoformat()
    log = [r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log ORDER BY id")]
    assert "reminder:paused:d1" in log
    assert "reminder:dropped:past_meaning:d1" in log
    assert "reminder:resumed:d3" in log


# ------------------------------------------------------------------------------------- migration
def test_the_paused_reminders_migration_downgrades_one_step_and_upgrades_again(
    admin: Engine, pg_url: str
) -> None:
    cfg = Config(str(API_INI))
    command.downgrade(cfg, "-1")
    left = _rows(admin, "SELECT to_regclass('agent.paused_reminders') IS NOT NULL")[0][0]
    care_agents = _rows(admin, "SELECT to_regclass('agent.care_agents') IS NOT NULL")[0][0]
    command.upgrade(cfg, "heads")
    assert left is False
    assert care_agents is True  # M1 stays
    assert _rows(admin, "SELECT to_regclass('agent.paused_reminders') IS NOT NULL")[0][0] is True


def test_paused_reminders_checks_pin_the_status_and_the_resolution_time(
    world: SeedResult, admin: Engine
) -> None:
    from sqlalchemy.exc import IntegrityError

    with admin.begin() as conn:
        conn.execute(
            text("INSERT INTO agent.care_agents (clinic_id, patient_id) VALUES (:c, :p)"),
            {"c": world.clinic_id, "p": world.patients["P025"]},
        )
        agent_id = conn.execute(text("SELECT id FROM agent.care_agents")).scalar_one()
    insert = (
        "INSERT INTO agent.paused_reminders (clinic_id, care_agent_id, patient_id, patient_ref, event_kind, "
        "due_at, dedupe_key, status, resolved_at) VALUES (:c, :a, :p, 'P025', :k, now(), :d, :s, :r)"
    )
    base = {"c": world.clinic_id, "a": agent_id, "p": world.patients["P025"]}
    bad: list[dict[str, object]] = [
        {"k": "tick", "d": "1", "s": "paused", "r": None},  # not a reminder kind
        {"k": "no_show", "d": "2", "s": "done", "r": None},  # unknown status
        {
            "k": "no_show",
            "d": "3",
            "s": "paused",
            "r": datetime(2026, 1, 1, tzinfo=UTC),
        },  # paused but resolved
        {"k": "no_show", "d": "4", "s": "dropped", "r": None},  # resolved without a time
    ]
    for values in bad:
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(text(insert), {**base, **values})
    with admin.begin() as conn:
        conn.execute(text(insert), {**base, "k": "no_show", "d": "ok", "s": "paused", "r": None})
