"""``SqlControlStore``, ``SqlHandoffConfigSource`` and the skill row over Postgres (package M, step M2b).

New tests. Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). The agent side (open a round) runs as the
worker role, the staff side (accept, release) as ``be_app``, like production. Single tenant: no row level
security; the guards under test are the table CHECKs, the partial unique index and the row lock.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pema.care.control import CareControl, transition_action
from pema.care.control_store import SqlControlStore, pack_reason, unpack_reason
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import (
    HANDOFF_INSTRUCTION,
    HANDOFF_SKILL_NAME,
    SqlHandoffConfigSource,
    ensure_handoff_skill,
)
from pema.care.handoff_types import (
    Depth,
    HandoffAction,
    HandoffConfig,
    HandoffDecision,
    InvalidTransitionError,
    Urgency,
)
from pema.care.models import ControlState
from pema.care.pairing import ensure_care_agent
from pema.care.ports import ChannelTarget, HandoffSpec, PatientContext, ReleaseSpec
from pema.care.store import SqlCareStore
from pema.care.testing import FakeChannel
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _staff(world: SeedResult, key: str = "cs.maianh", role: Role = Role.CS_STAFF) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.USER,
        actor_user_id=world.users[key],
        actor_role=role,
    )


def _spec(depth: str = "D4", urgency: str = "urgent") -> HandoffSpec:
    return HandoffSpec(
        reason="depth_at_or_above_threshold",
        summary="Khách: P025\nĐộ sâu: D4",
        depth=depth,
        confidence=0.7,
        required_skill="medical",
        urgency=urgency,
    )


def _decision(depth: Depth = Depth.D4, urgency: Urgency = Urgency.URGENT) -> HandoffDecision:
    return HandoffDecision(
        action=HandoffAction.HANDOFF,
        reason="depth_at_or_above_threshold",
        depth=depth,
        confidence=0.7,
        required_skill="medical",
        urgency=urgency,
        signals=("depth_at_or_above_threshold",),
    )


async def _agent(db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, code: str = "P025"):  # type: ignore[no-untyped-def]
    async with db.session() as session:
        care_agent_id = (await ensure_care_agent(session, world.patients[code])).id
    agent = await SqlCareStore(worker_db).get_care_agent(care_agent_id)
    assert agent is not None
    return agent


def _rows(admin: Engine, sql: str, **params: object) -> list[tuple[object, ...]]:
    with admin.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params).all()]


# ----------------------------------------------------------------------------- pack / unpack
def test_the_summary_rides_in_the_reason_column_and_comes_back() -> None:
    stored = pack_reason("low_confidence", "Khách: P025\nĐộ sâu: D3")
    assert unpack_reason(stored) == ("low_confidence", "Khách: P025\nĐộ sâu: D3")
    assert unpack_reason("red_flag") == ("red_flag", "")
    assert pack_reason("red_flag", "") == "red_flag"


# --------------------------------------------------------------------------------- open a round
async def test_opening_a_round_sets_the_state_and_writes_the_request_and_its_audit_line(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    store = SqlControlStore(worker_db)
    opened = await store.open_handoff(
        agent, _spec(), log_action="control:auto_to_handoff_routing:agent", at=NOW
    )
    assert opened.created
    assert opened.request.reason == "depth_at_or_above_threshold"
    assert opened.request.summary == "Khách: P025\nĐộ sâu: D4"
    assert (await store.get_control(agent.patient_id)).state is ControlState.HANDOFF_ROUTING
    assert await SqlCareStore(worker_db).get_control_state(agent.patient_id) is ControlState.HANDOFF_ROUTING
    rows = _rows(
        admin,
        "SELECT depth, urgency, candidates::text, outcome FROM agent.handoff_requests WHERE patient_id = :p",
        p=agent.patient_id,
    )
    assert rows == [("D4", "urgent", "[]", None)]
    log = _rows(
        admin,
        "SELECT action_type, disposition, depth FROM agent.actions_log WHERE care_agent_id = :a",
        a=agent.id,
    )
    assert log == [("control:auto_to_handoff_routing:agent", "paused", "D4")]


async def test_a_second_open_changes_nothing(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    store = SqlControlStore(worker_db)
    first = await store.open_handoff(agent, _spec(), log_action="a", at=NOW)
    second = await store.open_handoff(agent, _spec("D5"), log_action="b", at=NOW)
    assert (first.created, second.created) == (True, False)
    assert second.request.id == first.request.id
    assert _rows(admin, "SELECT count(*) FROM agent.handoff_requests")[0][0] == 1
    assert _rows(admin, "SELECT count(*) FROM agent.actions_log")[0][0] == 1


async def test_concurrent_opens_create_exactly_one_round(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    store = SqlControlStore(worker_db)
    results = await asyncio.gather(
        *[store.open_handoff(agent, _spec(), log_action="x", at=NOW) for _ in range(5)]
    )
    assert sum(r.created for r in results) == 1
    assert len({r.request.id for r in results}) == 1
    assert _rows(admin, "SELECT count(*) FROM agent.handoff_requests")[0][0] == 1


async def test_the_database_allows_one_open_request_per_patient_whatever_the_code_does(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    insert = (
        "INSERT INTO agent.handoff_requests (clinic_id, patient_id, reason, depth, confidence) "
        "VALUES (:c, :p, 'dup', 'D2', 0.5)"
    )
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text(insert), {"c": agent.clinic_id, "p": agent.patient_id})


# ------------------------------------------------------------------------------------- accept
async def test_accept_moves_to_staff_and_closes_the_request(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    staff_id = world.users["cs.maianh"]
    store = SqlControlStore(db)
    request = await store.accept(agent.patient_id, staff_id, log_action="control:accepted", at=NOW)
    assert (request.accepted_by, request.outcome) == (staff_id, "accepted")
    control = await store.get_control(agent.patient_id)
    assert (control.state, control.staff_owner) == (ControlState.STAFF, staff_id)
    assert await store.get_open_request(agent.patient_id) is None
    assert (
        _rows(admin, "SELECT count(*) FROM agent.actions_log WHERE action_type = 'control:accepted'")[0][0]
        == 1
    )
    with pytest.raises(InvalidTransitionError):
        await store.accept(agent.patient_id, staff_id, log_action="again", at=NOW)


async def test_two_staff_accepting_at_once_one_wins(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    store = SqlControlStore(db)
    outcomes = await asyncio.gather(
        store.accept(agent.patient_id, world.users["cs.maianh"], log_action="a", at=NOW),
        store.accept(agent.patient_id, world.users["cs.thu"], log_action="b", at=NOW),
        return_exceptions=True,
    )
    assert sum(isinstance(o, InvalidTransitionError) for o in outcomes) == 1
    assert sum(not isinstance(o, BaseException) for o in outcomes) == 1


async def test_accept_without_a_round_is_refused(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    agent = await _agent(db, worker_db, world)
    with pytest.raises(InvalidTransitionError):
        await SqlControlStore(db).accept(agent.patient_id, world.users["cs.maianh"], log_action="a", at=NOW)


async def test_a_decline_is_audited_and_the_round_stays_open(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    store = SqlControlStore(db)
    request = await store.record_decline(
        agent.patient_id, world.users["cs.thu"], log_action="declined", at=NOW
    )
    assert request.outcome is None
    assert (await store.get_control(agent.patient_id)).state is ControlState.HANDOFF_ROUTING
    assert _rows(admin, "SELECT count(*) FROM agent.actions_log WHERE action_type = 'declined'")[0][0] == 1


# ------------------------------------------------------------------------------------- release
async def test_release_returns_to_auto_writes_the_memory_and_the_override_together(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    with admin.begin() as conn:
        conn.execute(
            text('UPDATE agent.care_agents SET autonomy_levels = \'{"default": "L2"}\'::jsonb WHERE id = :a'),
            {"a": agent.id},
        )
    ctx = _staff(world)
    control = CareControl(
        store=SqlControlStore(db),
        config_source=SqlHandoffConfigSource(db),
        channel=None,
        clock=_clock,
    )
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    await control.accept(ctx, agent.patient_id)

    until = NOW + timedelta(days=7)
    snapshot = await control.release_to_auto(
        ctx, agent.patient_id, "Khách thích nhắn buổi tối", override_level=0, until=until
    )

    assert snapshot.state is ControlState.AUTO
    row = _rows(
        admin,
        "SELECT state, staff_owner, release_note, auto_release_after FROM agent.conversation_control "
        "WHERE patient_id = :p",
        p=agent.patient_id,
    )
    assert row == [("AUTO", None, "Khách thích nhắn buổi tối", None)]
    memory = _rows(
        admin, "SELECT fact, source, valid_until FROM agent.care_memory WHERE care_agent_id = :a", a=agent.id
    )
    assert memory == [("Khách thích nhắn buổi tối", "staff", None)]
    override = _rows(
        admin,
        "SELECT autonomy_override->>'level', autonomy_override->>'until' FROM agent.care_agents WHERE id = :a",
        a=agent.id,
    )
    assert override == [("L0", until.isoformat())]
    actions = [r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log ORDER BY id")]
    assert transition_action(ControlState.STAFF, ControlState.AUTO, f"staff:{ctx.actor_user_id}") in actions
    assert "autonomy:override_set:level0" in actions


async def test_a_release_may_not_raise_the_level_and_changes_nothing_when_refused(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)  # L0 everywhere
    ctx = _staff(world)
    control = CareControl(
        store=SqlControlStore(db), config_source=SqlHandoffConfigSource(db), channel=None, clock=_clock
    )
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    await control.accept(ctx, agent.patient_id)
    with pytest.raises(ValueError, match="lower"):
        await control.release_to_auto(ctx, agent.patient_id, "ok", override_level=2)
    assert (await SqlControlStore(db).get_control(agent.patient_id)).state is ControlState.STAFF
    assert _rows(admin, "SELECT count(*) FROM agent.care_memory")[0][0] == 0


async def test_release_outside_staff_is_refused(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    agent = await _agent(db, worker_db, world)
    store = SqlControlStore(db)
    with pytest.raises(InvalidTransitionError):  # AUTO
        await store.release(agent.patient_id, world.users["cs.maianh"], ReleaseSpec(), log_action="r", at=NOW)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    with pytest.raises(InvalidTransitionError):  # HANDOFF_ROUTING
        await store.release(agent.patient_id, world.users["cs.maianh"], ReleaseSpec(), log_action="r", at=NOW)


async def test_the_database_refuses_staff_without_an_owner_and_a_non_positive_auto_release(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(
            text("UPDATE agent.conversation_control SET state = 'STAFF' WHERE patient_id = :p"),
            {"p": agent.patient_id},
        )
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent.conversation_control SET auto_release_after = interval '0' WHERE patient_id = :p"
            ),
            {"p": agent.patient_id},
        )


async def test_auto_release_after_stays_null_unless_set_through_the_guarded_api(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    await SqlControlStore(worker_db).open_handoff(agent, _spec(), log_action="x", at=NOW)
    assert _rows(admin, "SELECT auto_release_after FROM agent.conversation_control")[0][0] is None
    store = SqlControlStore(db)
    await store.set_auto_release_after(agent.patient_id, timedelta(hours=6), log_action="set", at=NOW)
    assert (await store.get_control(agent.patient_id)).auto_release_after == timedelta(hours=6)


# ---------------------------------------------------------- the whole chain through CareControl
async def test_request_handoff_through_the_sql_store_sends_one_holding_message(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent = await _agent(db, worker_db, world)
    channel = FakeChannel()
    control = CareControl(
        store=SqlControlStore(worker_db),
        config_source=SqlHandoffConfigSource(worker_db),
        channel=channel,
        clock=_clock,
    )
    context = PatientContext(
        "P025",
        agent.patient_id,
        channel=ChannelTarget("acct-fake", "thread-fake"),
        facts={"contact": "0901234567"},
    )
    event = CareEvent(
        kind=EventKind.PATIENT_MESSAGE, initiator=Initiator.PATIENT, patient_ref="P025", occurred_at=NOW
    )
    first = await control.request_handoff(agent, event, context, _decision(Depth.D5, Urgency.CRITICAL))
    second = await control.request_handoff(agent, event, context, _decision(Depth.D5, Urgency.CRITICAL))
    assert (first.created, second.created) == (True, False)
    assert len(channel.sent) == 1
    stored = _rows(admin, "SELECT reason FROM agent.handoff_requests")[0][0]
    assert isinstance(stored, str)
    assert "0901234567" not in stored
    actions = [r[0] for r in _rows(admin, "SELECT action_type FROM agent.actions_log ORDER BY id")]
    assert actions == ["control:auto_to_handoff_routing:agent", "control:holding_message"]


# --------------------------------------------------------------------------------- skill row
async def test_the_skill_row_is_seeded_with_defaults_that_await_the_doctor(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    async with db.session() as session:
        await ensure_handoff_skill(session, world.clinic_id)
        await ensure_handoff_skill(session, world.clinic_id)  # idempotent
    rows = _rows(
        admin,
        "SELECT name, enabled_for_profiles, classifier_config->>'pending_doctor_approval', "
        "classifier_config->>'confidence_threshold' FROM agent.skills",
    )
    assert rows == [(HANDOFF_SKILL_NAME, ["patient_channel"], "true", "0.6")]


async def test_the_config_source_reads_the_row_on_every_call(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    source = SqlHandoffConfigSource(db)
    missing = await source.get(world.clinic_id)
    assert missing.config == HandoffConfig()  # no row: defaults
    assert missing.instruction == HANDOFF_INSTRUCTION
    async with db.session() as session:
        await ensure_handoff_skill(session, world.clinic_id)
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent.skills SET classifier_config = classifier_config || "
                '\'{"vip_handoff_from_depth": "D1", "confidence_threshold": 0.8, '
                "\"pending_doctor_approval\": false}'::jsonb WHERE name = 'handoff'"
            )
        )
    edited = (await source.get(world.clinic_id)).config
    assert edited.vip_handoff_from_depth is Depth.D1
    assert edited.confidence_threshold == 0.8
    assert edited.pending_doctor_approval is False  # the doctor's sign-off is data, not code


async def test_an_invalid_config_falls_back_to_the_defaults(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    async with db.session() as session:
        await ensure_handoff_skill(session, world.clinic_id)
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent.skills SET classifier_config = '{\"confidence_threshold\": 7}'::jsonb "
                "WHERE name = 'handoff'"
            )
        )
    assert (await SqlHandoffConfigSource(db).get(world.clinic_id)).config == HandoffConfig()


async def test_the_worker_role_can_read_the_skill_row(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    async with db.session() as session:
        await ensure_handoff_skill(session, world.clinic_id)
    settings = await SqlHandoffConfigSource(worker_db).get(world.clinic_id)
    assert settings.config.pending_doctor_approval is True
