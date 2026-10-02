"""Autonomy levels, override, pause, kill switches and the auto-send gate (package M, step M3).

New tests (no zalo-agent original). The pure tests use a transient ``CareAgent`` and need no database; the
``db`` tests need ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). Single tenant: nothing about row level security.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from pema.care.autonomy import (
    ACTION_TYPES,
    KILL_SWITCH_KEY,
    SETTINGS_KEY,
    ActionType,
    AutonomySettings,
    AutoSendDecision,
    Initiator,
    KillSwitchState,
    Level,
    clear_override,
    demote,
    demote_all_to_l0,
    effective_level,
    evaluate_auto_send,
    levels_snapshot,
    load_kill_switch,
    load_settings,
    may_auto_send,
    pause,
    resolve_level,
    resume,
    save_settings,
    set_kill_switch,
    set_override,
)
from pema.care.models import ActionLog, CareAgent
from pema.care.pairing import ensure_care_agent
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.runtime_settings_kv import (
    InMemoryRuntimeSettingsKv,
    get_runtime_settings_kv,
    install_runtime_settings_kv,
    reset_runtime_settings_kv,
)
from pema.core.db import ClinicDatabase
from pema_contracts.common import VN_TZ
from pema_contracts.policy import STAFF_ASSISTANT_PROFILE

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=VN_TZ)
TEMPLATE = "tpl-reminder-visit"
OTHER_TEMPLATE = "tpl-not-approved"


@pytest.fixture(autouse=True)
def kv() -> Iterator[InMemoryRuntimeSettingsKv]:
    store = InMemoryRuntimeSettingsKv()
    install_runtime_settings_kv(store)
    yield store
    reset_runtime_settings_kv()


def _agent(
    levels: dict[str, Any] | None = None,
    override: dict[str, Any] | None = None,
    *,
    paused: bool = False,
) -> CareAgent:
    return CareAgent(
        id=uuid4(),
        clinic_id=uuid4(),
        patient_id=uuid4(),
        autonomy_levels=levels or {},
        autonomy_override=override,
        paused=paused,
    )


def _template(**overrides: Any) -> AutoSendDecision:
    base: dict[str, Any] = {
        "action_type": ActionType.REMINDER_TEMPLATE.value,
        "template_id": TEMPLATE,
        "identity_verified": True,
    }
    return AutoSendDecision(**{**base, **overrides})


def _faq(**overrides: Any) -> AutoSendDecision:
    base: dict[str, Any] = {
        "action_type": ActionType.FAQ_KB_ANSWER.value,
        "depth": "D2",
        "kb_citations": 1,
        "confidence": 0.95,
        "identity_verified": True,
    }
    return AutoSendDecision(**{**base, **overrides})


def _with_template() -> AutonomySettings:
    return AutonomySettings(templates_l1=(TEMPLATE,))


# ====================================================================================== new patient
def test_a_new_patient_is_l0_for_every_action_type() -> None:
    agent = _agent()
    for action_type in ACTION_TYPES:
        assert effective_level(agent, action_type, NOW) is Level.L0
    assert set(levels_snapshot(agent, NOW).values()) == {Level.L0}


def test_an_unknown_action_type_is_l0() -> None:
    assert effective_level(_agent({"made_up": "L2"}), "made_up", NOW) is Level.L0


def test_the_defaults_are_flagged_pending_doctor_approval() -> None:
    settings = load_settings()
    assert settings.pending_doctor_approval is True
    assert settings.n_to_l2 == {"faq_kb_answer": 10}
    assert settings.templates_l1 == ()


# ============================================================================================ L1
def test_enabling_a_template_lets_l1_send_that_template_but_not_another() -> None:
    settings = _with_template()
    agent = _agent()
    level = effective_level(agent, ActionType.REMINDER_TEMPLATE.value, NOW, settings=settings)
    assert level is Level.L1
    assert may_auto_send(_template(), level, settings=settings)
    assert not may_auto_send(_template(template_id=OTHER_TEMPLATE), level, settings=settings)
    assert not may_auto_send(_template(template_id=None), level, settings=settings)


def test_nothing_enabled_means_a_template_is_not_sent_even_at_l1() -> None:
    assert not may_auto_send(_template(), Level.L1, settings=AutonomySettings())


def test_l1_does_not_send_a_faq_answer() -> None:
    verdict = evaluate_auto_send(_faq(), Level.L1, settings=_with_template())
    assert (verdict.allowed, verdict.reason) == (False, "needs_l2")


def test_appointment_confirm_needs_the_slot_the_patient_picked() -> None:
    settings = AutonomySettings(appointment_confirm_l1=True)
    level = effective_level(_agent(), ActionType.APPOINTMENT_CONFIRM.value, NOW, settings=settings)
    assert level is Level.L1
    confirm = AutoSendDecision(
        action_type=ActionType.APPOINTMENT_CONFIRM.value, slot_picked_by_patient=True, identity_verified=True
    )
    assert may_auto_send(confirm, level, settings=settings)
    not_picked = AutoSendDecision(action_type=ActionType.APPOINTMENT_CONFIRM.value, identity_verified=True)
    assert not may_auto_send(not_picked, level, settings=settings)


def test_appointment_confirm_is_l0_until_the_clinic_switches_it_on() -> None:
    assert effective_level(_agent(), ActionType.APPOINTMENT_CONFIRM.value, NOW) is Level.L0


def test_an_explicit_entry_beats_the_clinic_floor() -> None:
    agent = _agent({ActionType.REMINDER_TEMPLATE.value: "L0"})
    level = effective_level(agent, ActionType.REMINDER_TEMPLATE.value, NOW, settings=_with_template())
    assert level is Level.L0


# ============================================================================================ L2
def test_l2_sends_a_cited_confident_faq_answer_at_depth_d2() -> None:
    assert may_auto_send(_faq(), Level.L2)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"kb_citations": 0}, "no_kb_citation"),
        ({"confidence": 0.5}, "confidence_below_threshold"),
        ({"confidence": None}, "confidence_below_threshold"),
        ({"red_flags": ("bleeding",)}, "red_flag"),
        ({"depth": "D3"}, "depth_too_deep"),
        ({"depth": None}, "depth_too_deep"),
    ],
)
def test_l2_refuses_a_faq_answer_that_misses_a_condition(overrides: dict[str, Any], reason: str) -> None:
    verdict = evaluate_auto_send(_faq(**overrides), Level.L2)
    assert (verdict.allowed, verdict.reason) == (False, reason)


def test_depth_d3_is_open_only_for_the_types_the_doctor_enabled() -> None:
    settings = AutonomySettings(d3_enabled_types=(ActionType.FAQ_KB_ANSWER.value,))
    assert may_auto_send(_faq(depth="D3"), Level.L2, settings=settings)
    assert not may_auto_send(_faq(depth="D3"), Level.L2, settings=AutonomySettings())


def test_the_confidence_threshold_is_configurable() -> None:
    strict = AutonomySettings(confidence_threshold=0.99)
    assert not may_auto_send(_faq(confidence=0.95), Level.L2, settings=strict)
    assert may_auto_send(_faq(confidence=0.95), Level.L2, settings=AutonomySettings(confidence_threshold=0.9))


def test_l2_keeps_the_abilities_of_l1() -> None:
    assert may_auto_send(_template(), Level.L2, settings=_with_template())


def test_symptom_reply_has_no_auto_ability_even_at_l2() -> None:
    decision = AutoSendDecision(
        action_type=ActionType.SYMPTOM_REPLY.value, identity_verified=True, depth="D1"
    )
    verdict = evaluate_auto_send(decision, Level.L2)
    assert (verdict.allowed, verdict.reason) == (False, "no_auto_ability")


# ======================================================================================== hard rules
def test_medical_judgement_is_never_auto_sent_even_if_the_config_tries() -> None:
    hostile = AutonomySettings.model_validate(
        {
            "n_to_l2": {"medical_judgement": 1, "faq_kb_answer": 1},
            "d3_enabled_types": ["medical_judgement"],
            "templates_l1": [TEMPLATE],
        }
    )
    assert "medical_judgement" not in hostile.n_to_l2
    assert "medical_judgement" not in hostile.d3_enabled_types
    decision = AutoSendDecision(
        action_type="medical_judgement", template_id=TEMPLATE, depth="D1", kb_citations=3, confidence=1.0,
        identity_verified=True,
    )  # fmt: skip
    for level in Level:
        assert not may_auto_send(decision, level, settings=hostile)
    # even a settings object that bypasses validation cannot lift the rule
    forced = AutonomySettings.model_construct(
        n_to_l2={"medical_judgement": 1}, templates_l1=(TEMPLATE,), d3_enabled_types=("medical_judgement",)
    )
    assert not may_auto_send(decision, Level.L2, settings=forced)
    agent = _agent({"medical_judgement": "L2"})
    assert effective_level(agent, "medical_judgement", NOW, settings=forced) is Level.L0


def test_birthday_greeting_is_never_auto_sent() -> None:
    agent = _agent({ActionType.BIRTHDAY_GREETING.value: "L2"})
    assert effective_level(agent, ActionType.BIRTHDAY_GREETING.value, NOW) is Level.L0
    decision = AutoSendDecision(
        action_type=ActionType.BIRTHDAY_GREETING.value, template_id=TEMPLATE, identity_verified=True
    )
    assert evaluate_auto_send(decision, Level.L2, settings=_with_template()).reason == "never_auto_sent"


@pytest.mark.parametrize("depth", ["D4", "D5", "D9", "x"])
def test_depth_d4_d5_or_garbage_always_goes_to_a_person(depth: str) -> None:
    verdict = evaluate_auto_send(_template(depth=depth), Level.L2, settings=_with_template())
    assert (verdict.allowed, verdict.reason) == (False, "depth_requires_human")
    assert not may_auto_send(_faq(depth=depth), Level.L2)


def test_a_red_flag_blocks_a_template_too() -> None:
    verdict = evaluate_auto_send(_template(red_flags=("fever",)), Level.L2, settings=_with_template())
    assert verdict.reason == "red_flag"


def test_marketing_opt_out_blocks_marketing() -> None:
    settings = _with_template()
    assert may_auto_send(_template(is_marketing=True), Level.L1, settings=settings)
    verdict = evaluate_auto_send(
        _template(is_marketing=True, marketing_opt_out=True), Level.L1, settings=settings
    )
    assert (verdict.allowed, verdict.reason) == (False, "marketing_opt_out")


def test_the_patient_channel_profile_is_a_ceiling() -> None:
    settings = _with_template()
    unverified = evaluate_auto_send(_template(identity_verified=False), Level.L1, settings=settings)
    assert unverified.reason == "identity_not_verified"
    scheduled_faq = evaluate_auto_send(_faq(scheduled=True), Level.L2, settings=settings)
    assert scheduled_faq.reason == "scheduled_not_from_template"
    assert may_auto_send(_template(scheduled=True), Level.L1, settings=settings)
    # the staff profile has neither rule, so the profile argument really is what decides
    assert may_auto_send(
        _template(identity_verified=False), Level.L1, settings=settings, profile=STAFF_ASSISTANT_PROFILE
    )
    # an unknown profile name falls back to the strict one
    assert not may_auto_send(_template(identity_verified=False), Level.L1, settings=settings, profile="nope")


def test_l0_never_sends_anything() -> None:
    assert not may_auto_send(_template(), Level.L0, settings=_with_template())
    assert not may_auto_send(_faq(), Level.L0)


# ========================================================================================== override
def _override(level: str, until: datetime) -> dict[str, Any]:
    return {"level": level, "until": until.isoformat()}


def test_an_override_l0_for_7_days_ends_and_the_previous_level_returns() -> None:
    settings = _with_template()
    agent = _agent(
        {ActionType.FAQ_KB_ANSWER.value: "L2"},
        _override("L0", NOW + timedelta(days=7)),
    )
    faq, template = ActionType.FAQ_KB_ANSWER.value, ActionType.REMINDER_TEMPLATE.value
    assert effective_level(agent, faq, NOW, settings=settings) is Level.L0
    assert effective_level(agent, template, NOW + timedelta(days=6), settings=settings) is Level.L0
    after = NOW + timedelta(days=7, seconds=1)
    assert effective_level(agent, faq, after, settings=settings) is Level.L2
    assert effective_level(agent, template, after, settings=settings) is Level.L1


def test_an_override_can_lower_but_never_raise() -> None:
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L1"}, _override("L2", NOW + timedelta(days=1)))
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L1
    lower = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"}, _override("L1", NOW + timedelta(days=1)))
    assert effective_level(lower, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L1


@pytest.mark.parametrize(
    "broken",
    [
        {"level": "L0"},
        {"level": "L9", "until": "2030-01-01T00:00:00+07:00"},
        {"level": "L0", "until": "not a date"},
        {"level": "L0", "until": "2030-01-01T00:00:00"},
    ],
)
def test_an_unreadable_override_is_ignored(broken: dict[str, Any]) -> None:
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"}, broken)
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L2


# =================================================================================== kill switches
def test_a_paused_care_agent_is_l0() -> None:
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"}, paused=True)
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L0


async def test_the_system_kill_switch_stops_every_auto_send() -> None:
    await save_settings(_with_template())
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"})
    assert effective_level(agent, ActionType.REMINDER_TEMPLATE.value, NOW) is Level.L1
    state = await set_kill_switch("system", True, initiator=Initiator.MANAGER)
    assert state.system
    assert state.any_on
    for action_type in ACTION_TYPES:
        level = effective_level(agent, action_type, NOW)
        assert level is Level.L0
        decision = AutoSendDecision(
            action_type=action_type, template_id=TEMPLATE, depth="D1", kb_citations=2, confidence=1.0,
            identity_verified=True, slot_picked_by_patient=True,
        )  # fmt: skip
        assert not may_auto_send(decision, level)
    await set_kill_switch("system", False, initiator=Initiator.MANAGER)
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L2


async def test_a_specialist_kill_switch_is_l0_for_everyone_and_blocks_only_that_agent() -> None:
    await set_kill_switch("reviewer", True, initiator=Initiator.MANAGER)
    state = load_kill_switch()
    assert state.agents == frozenset({"reviewer"})
    assert not state.system
    assert state.blocks("reviewer")
    assert not state.blocks("scheduler")
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"})
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L0
    await set_kill_switch("reviewer", False, initiator=Initiator.MANAGER)
    assert not load_kill_switch().any_on
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L2


async def test_the_system_and_specialist_switches_are_independent() -> None:
    await set_kill_switch("scheduler", True, initiator=Initiator.MANAGER)
    await set_kill_switch("system", True, initiator=Initiator.MANAGER)
    await set_kill_switch("system", False, initiator=Initiator.MANAGER)
    assert load_kill_switch() == KillSwitchState(system=False, agents=frozenset({"scheduler"}))


@pytest.mark.parametrize("raw", ["{", "[]", '{"system": "yes"}', '{"agents": "all"}', "null"])
def test_an_unreadable_kill_switch_fails_closed(raw: str) -> None:
    kv = InMemoryRuntimeSettingsKv({KILL_SWITCH_KEY: raw})
    state = load_kill_switch(kv)
    assert state.system is True
    agent = _agent({ActionType.FAQ_KB_ANSWER.value: "L2"})
    assert effective_level(agent, ActionType.FAQ_KB_ANSWER.value, NOW, kill_switch=state) is Level.L0


async def test_settings_round_trip_and_an_unreadable_value_falls_back_to_the_defaults() -> None:
    await save_settings(AutonomySettings(templates_l1=(TEMPLATE,), pending_doctor_approval=False))
    loaded = load_settings()
    assert loaded.templates_l1 == (TEMPLATE,)
    assert loaded.pending_doctor_approval is False
    await get_runtime_settings_kv().aset(SETTINGS_KEY, "{not json")
    fallback = load_settings()
    assert fallback.pending_doctor_approval is True
    assert fallback.templates_l1 == ()


# =============================================================================================== db
async def _agent_id(db: ClinicDatabase, world: SeedResult, code: str = "P025") -> UUID:
    async with db.session() as session:
        return (await ensure_care_agent(session, world.patients[code])).id


async def _log_rows(db: ClinicDatabase, care_agent_id: UUID) -> list[dict[str, Any]]:
    async with db.session() as session:
        rows = await session.scalars(
            select(ActionLog).where(
                ActionLog.care_agent_id == care_agent_id, ActionLog.action_type == "autonomy_change"
            )
        )
        return [r.reviewer_edit_diff or {} for r in rows]


@pytest.mark.db
async def test_a_new_patient_from_the_database_is_l0_for_all_types(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    async with db.session() as session:
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        assert {t: effective_level(agent, t, NOW) for t in ACTION_TYPES} == dict.fromkeys(
            ACTION_TYPES, Level.L0
        )


@pytest.mark.db
async def test_set_override_expires_and_resolve_level_clears_it_with_a_log_row(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    staff = world.users["reception.lan"]
    async with db.session() as session:
        await demote_all_to_l0(session, care_agent_id, initiator=Initiator.DOCTOR, reason="test_reset")
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        agent.autonomy_levels = {ActionType.FAQ_KB_ANSWER.value: "L2"}
        await session.flush()
        await set_override(
            session,
            care_agent_id,
            Level.L0,
            NOW + timedelta(days=7),
            "tạm dừng một tuần",
            initiator=Initiator.STAFF,
            actor_user_id=staff,
            now=NOW,
        )
        agent = await session.get(CareAgent, care_agent_id, populate_existing=True)
        assert agent is not None
        faq = ActionType.FAQ_KB_ANSWER.value
        assert await resolve_level(session, agent, faq, NOW + timedelta(days=1)) is Level.L0
        assert agent.autonomy_override is not None
        assert agent.autonomy_override["note"] == "tạm dừng một tuần"
        later = NOW + timedelta(days=7, minutes=1)
        assert await resolve_level(session, agent, faq, later) is Level.L2
        assert agent.autonomy_override is None
    rows = await _log_rows(db, care_agent_id)
    scopes = [(r["scope"], r["reason"], r["initiator"]) for r in rows]
    assert ("override", "override_set", "staff") in scopes
    assert ("override", "override_expired", "system") in scopes
    assert all("tạm dừng" not in str(r) for r in rows)  # the staff note is not copied into the log


@pytest.mark.db
async def test_set_override_refuses_a_past_or_naive_until(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    async with db.session() as session:
        with pytest.raises(ValueError, match="future"):
            await set_override(session, care_agent_id, Level.L0, NOW - timedelta(hours=1), now=NOW)
        with pytest.raises(ValueError, match="timezone"):
            await set_override(session, care_agent_id, Level.L0, datetime(2030, 1, 1), now=NOW)


@pytest.mark.db
async def test_clear_override_logs_once(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    async with db.session() as session:
        await set_override(
            session, care_agent_id, Level.L0, NOW + timedelta(days=1), initiator=Initiator.STAFF, now=NOW
        )
        assert await clear_override(session, care_agent_id, initiator=Initiator.STAFF) is True
        assert await clear_override(session, care_agent_id, initiator=Initiator.STAFF) is False
    assert [r["reason"] for r in await _log_rows(db, care_agent_id)] == ["override_set", "override_cleared"]


@pytest.mark.db
async def test_pause_and_resume_are_per_patient_and_logged(db: ClinicDatabase, world: SeedResult) -> None:
    mine = await _agent_id(db, world, "P025")
    other = await _agent_id(db, world, "P026")
    async with db.session() as session:
        assert await pause(session, world.patients["P025"], actor_user_id=world.users["reception.lan"])
        assert not await pause(session, world.patients["P025"])  # already paused: nothing written
    async with db.session() as session:
        paused = await session.get(CareAgent, mine)
        untouched = await session.get(CareAgent, other)
        assert paused is not None
        assert untouched is not None
        assert paused.paused is True
        assert untouched.paused is False
        assert effective_level(paused, ActionType.FAQ_KB_ANSWER.value, NOW) is Level.L0
        assert await resume(session, world.patients["P025"])
    assert [r["reason"] for r in await _log_rows(db, mine)] == ["pause", "resume"]
    assert await _log_rows(db, other) == []


@pytest.mark.db
async def test_pause_of_an_unknown_patient_is_an_error(db: ClinicDatabase, world: SeedResult) -> None:
    async with db.session() as session:
        with pytest.raises(LookupError):
            await pause(session, uuid4())


@pytest.mark.db
async def test_demote_lowers_only_and_logs_the_initiator(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    faq = ActionType.FAQ_KB_ANSWER.value
    async with db.session() as session:
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        agent.autonomy_levels = {faq: "L2"}
        agent.trust_scores = {"scores": {faq: 10}, "processed_reviews": []}
        await session.flush()
        with pytest.raises(ValueError, match="lowered"):
            await demote(
                session,
                care_agent_id,
                ActionType.REMINDER_TEMPLATE.value,
                Level.L2,
                initiator=Initiator.DOCTOR,
                reason="x",
            )
        with pytest.raises(ValueError, match="unknown"):
            await demote(session, care_agent_id, "made_up", Level.L0, initiator=Initiator.DOCTOR, reason="x")
        assert (
            await demote(
                session, care_agent_id, faq, Level.L1, initiator=Initiator.DOCTOR, reason="doctor_decision"
            )
            is Level.L1
        )
    async with db.session() as session:
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        assert effective_level(agent, faq, NOW) is Level.L1
        assert agent.trust_scores["scores"] == {}  # the type has to be earned again
    (row,) = await _log_rows(db, care_agent_id)
    assert (row["initiator"], row["scope"], row["from"], row["to"]) == ("doctor", faq, "L2", "L1")


@pytest.mark.db
async def test_demote_all_to_l0_beats_the_clinic_floor(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = _with_template()
    async with db.session() as session:
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        assert effective_level(agent, ActionType.REMINDER_TEMPLATE.value, NOW, settings=settings) is Level.L1
        dropped = await demote_all_to_l0(
            session, care_agent_id, initiator=Initiator.MANAGER, reason="manager", settings=settings
        )
        assert dropped == [ActionType.REMINDER_TEMPLATE.value, ActionType.CARE_GUIDE_TEMPLATE.value]
    async with db.session() as session:
        agent = await session.get(CareAgent, care_agent_id)
        assert agent is not None
        assert set(levels_snapshot(agent, NOW, settings=settings).values()) == {Level.L0}


async def test_the_settings_survive_a_save_through_the_runtime_kv(
    kv: InMemoryRuntimeSettingsKv,
) -> None:
    await save_settings(AutonomySettings(n_to_l2={"faq_kb_answer": 3}))
    assert load_settings().n_to_l2 == {"faq_kb_answer": 3}
    assert SETTINGS_KEY in kv.snapshot()
