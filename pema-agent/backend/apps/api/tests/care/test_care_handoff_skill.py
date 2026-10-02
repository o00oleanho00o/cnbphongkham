"""The skill ``handoff`` (package M, step M2b). New tests (no zalo-agent original).

All fakes, fake clock, fake "model": no database. Every threshold used here is a ``HandoffConfig`` field
(``agent.skills.classifier_config``); a test that changes a field and sees the decision change is the proof
that the number is not in the code. Times are wall times of Asia/Ho_Chi_Minh through ``vn``; the send window
(used as clinic hours) is the default 08:00-20:00.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from pema.care.depth import DepthClassifier
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import (
    ASKS_FOR_HUMAN,
    CLASSIFIER_FALLBACK,
    COMPLEX_HISTORY,
    EXCEEDS_AUTONOMY,
    LOW_CONFIDENCE,
    NOT_A_PATIENT_MESSAGE,
    OUT_OF_HOURS,
    PAST_COMPLAINT,
    POST_PROCEDURE,
    RED_FLAG,
    REPEATED_QUESTION,
    UNVERIFIED,
    VIP,
    WITHIN_AUTONOMY,
    HandoffSkill,
    PatientSignals,
    effective_level,
)
from pema.care.handoff_types import (
    Depth,
    DepthLlmOutput,
    HandoffAction,
    HandoffConfig,
    HandoffDecision,
    Urgency,
    config_from_row,
    db_urgency,
)
from pema.care.ports import CareAgentSnapshot, ChannelTarget, HandoffDecider, PatientContext
from pema.care.testing import (
    FakeClock,
    FakeDepthLlm,
    FixedWindow,
    InMemoryCareStore,
    StaticHandoffConfig,
    StaticTexts,
    vn,
)

NOW = vn(2026, 10, 3, 10, 0)


def message() -> CareEvent:
    return CareEvent(
        kind=EventKind.PATIENT_MESSAGE, initiator=Initiator.PATIENT, patient_ref="P900", occurred_at=NOW
    )


def llm_says(depth: Depth, confidence: float = 0.9, **extra: Any) -> FakeDepthLlm:
    return FakeDepthLlm(
        DepthLlmOutput.model_validate({"depth": depth.value, "confidence": confidence, **extra})
    )


class Setup:
    def __init__(
        self,
        *,
        text: str = "kem này dùng buổi tối được không ạ",
        llm: FakeDepthLlm | None = None,
        config: HandoffConfig | None = None,
        now: datetime = NOW,
        facts: dict[str, Any] | None = None,
        verified: bool = True,
        autonomy_levels: dict[str, object] | None = None,
        autonomy_override: dict[str, object] | None = None,
    ) -> None:
        self.llm = llm or llm_says(Depth.D2)
        self.config_source = StaticHandoffConfig(config)
        self.texts = StaticTexts(text)
        store = InMemoryCareStore()
        agent = store.add_patient("P900")
        self.agent: CareAgentSnapshot = replace(
            agent,
            autonomy_levels=autonomy_levels or {},
            autonomy_override=autonomy_override,
        )
        self.context = PatientContext(
            patient_ref="P900",
            patient_id=agent.patient_id,
            facts=facts or {},
            channel=ChannelTarget("acct-fake", "thread-fake") if verified else None,
        )
        self.skill = HandoffSkill(
            classifier=DepthClassifier(self.llm),
            config_source=self.config_source,
            texts=self.texts,
            clock=FakeClock(now),
            window=FixedWindow(),
        )

    async def decide(self, event: CareEvent | None = None) -> HandoffDecision:
        return await self.skill.evaluate(self.agent, event or message(), self.context)


# ----------------------------------------------------------------------------- the contract
def test_the_skill_is_a_handoff_decider() -> None:
    decider: HandoffDecider = Setup().skill  # structural: pyright checks the signature
    assert decider is not None


async def test_decide_returns_the_verdict_with_the_structured_decision() -> None:
    setup = Setup()
    verdict = await setup.skill.decide(setup.agent, message(), setup.context)
    assert verdict.decision is not None
    assert verdict.action is verdict.decision.action
    assert verdict.reason == verdict.decision.reason


def test_every_default_threshold_awaits_the_doctor() -> None:
    assert HandoffConfig().pending_doctor_approval is True
    assert config_from_row({}).pending_doctor_approval is True
    assert config_from_row(None) == HandoffConfig()
    assert config_from_row({"unknown_field": 1, "confidence_threshold": 0.7}).confidence_threshold == 0.7


def test_critical_is_stored_as_urgent() -> None:
    assert db_urgency(Urgency.CRITICAL) == "urgent"
    assert db_urgency(Urgency.URGENT) == "urgent"
    assert db_urgency(Urgency.NORMAL) == "normal"


# ------------------------------------------------------------------------------- red flag, D5
async def test_a_red_flag_message_is_a_critical_d5_handoff_and_the_model_is_not_called() -> None:
    setup = Setup(text="em bị chảy máu nhiều sau khi tiêm, không cầm được", llm=llm_says(Depth.D1))
    decision = await setup.decide()
    assert decision.action is HandoffAction.HANDOFF
    assert (decision.depth, decision.urgency, decision.confidence) == (Depth.D5, Urgency.CRITICAL, 1.0)
    assert decision.reason == RED_FLAG
    assert "red_flag:bleeding" in decision.signals
    assert decision.required_skill == "medical"
    assert setup.llm.calls == []


async def test_a_red_flag_wins_over_every_reassuring_signal() -> None:
    setup = Setup(text="em sốt 39 độ", facts={"vip": False}, autonomy_levels={"default": "L2"})
    decision = await setup.decide()
    assert (decision.action, decision.depth) == (HandoffAction.HANDOFF, Depth.D5)


# ------------------------------------------------------------------------------------- identity
async def test_an_unverified_patient_asking_d2_is_handed_off() -> None:
    setup = Setup(llm=llm_says(Depth.D2), verified=False)
    decision = await setup.decide()
    assert decision.action is HandoffAction.HANDOFF
    assert decision.reason == UNVERIFIED
    assert decision.depth is Depth.D2


async def test_an_unverified_patient_asking_d1_is_answered() -> None:
    setup = Setup(text="cho em đặt lịch tái khám", verified=False)
    decision = await setup.decide()
    assert decision.action is HandoffAction.ANSWER
    assert decision.depth is Depth.D1
    assert decision.reason == WITHIN_AUTONOMY


async def test_a_verified_patient_asking_d2_is_answered() -> None:
    decision = await Setup(llm=llm_says(Depth.D2)).decide()
    assert decision.action is HandoffAction.ANSWER


async def test_the_identity_fact_overrides_the_channel_guess() -> None:
    setup = Setup(llm=llm_says(Depth.D2), facts={"identity_verified": False})  # a channel, but not verified
    assert (await setup.decide()).reason == UNVERIFIED


# --------------------------------------------------------------------------- depth thresholds
async def test_d4_is_always_a_person_by_default() -> None:
    decision = await Setup(llm=llm_says(Depth.D4)).decide()
    assert decision.action is HandoffAction.HANDOFF
    assert decision.urgency is Urgency.URGENT
    assert decision.required_skill == "medical"


async def test_d3_is_not_a_handoff_by_default() -> None:
    decision = await Setup(llm=llm_says(Depth.D3)).decide()
    assert decision.action is HandoffAction.ANSWER  # a draft for review is the loop's business


async def test_a_vip_configured_for_a_human_from_d2_is_handed_off_at_d2() -> None:
    config = HandoffConfig(vip_handoff_from_depth=Depth.D2)
    decision = await Setup(llm=llm_says(Depth.D2), config=config, facts={"vip": True}).decide()
    assert decision.action is HandoffAction.HANDOFF
    assert decision.reason == VIP


async def test_the_same_patient_without_vip_at_d2_is_answered() -> None:
    config = HandoffConfig(vip_handoff_from_depth=Depth.D2)
    assert (await Setup(llm=llm_says(Depth.D2), config=config).decide()).action is HandoffAction.ANSWER


async def test_a_vip_is_still_answered_at_d1() -> None:
    config = HandoffConfig(vip_handoff_from_depth=Depth.D2)
    setup = Setup(text="địa chỉ phòng khám ở đâu", config=config, facts={"vip": True})
    assert (await setup.decide()).action is HandoffAction.ANSWER


@pytest.mark.parametrize(
    ("fact", "signal"),
    [("complex_history", COMPLEX_HISTORY), ("past_complaint", PAST_COMPLAINT)],
)
async def test_patient_state_lowers_the_depth_that_goes_to_a_person(fact: str, signal: str) -> None:
    setup = Setup(llm=llm_says(Depth.D3), facts={fact: True})
    decision = await setup.decide()
    assert (decision.action, decision.reason) == (HandoffAction.HANDOFF, signal)


async def test_the_lowest_applicable_threshold_wins() -> None:
    config = HandoffConfig(vip_handoff_from_depth=Depth.D2, complex_history_handoff_from_depth=Depth.D3)
    setup = Setup(llm=llm_says(Depth.D2), config=config, facts={"vip": True, "complex_history": True})
    decision = await setup.decide()
    assert decision.action is HandoffAction.HANDOFF
    assert decision.signals == (VIP,)  # complex history alone would not hand off a D2


async def test_a_threshold_is_read_from_the_config_not_the_code() -> None:
    setup = Setup(llm=llm_says(Depth.D3), config=HandoffConfig(default_handoff_from_depth=Depth.D3))
    assert (await setup.decide()).action is HandoffAction.HANDOFF
    answered = Setup(llm=llm_says(Depth.D3), config=HandoffConfig(default_handoff_from_depth=Depth.D5))
    assert (await answered.decide()).action is HandoffAction.ANSWER


async def test_the_config_is_read_on_every_decision() -> None:
    setup = Setup()
    await setup.decide()
    await setup.decide()
    assert setup.config_source.reads == 2


# ------------------------------------------------------------------------- confidence, fallback
async def test_a_confidence_under_the_threshold_is_a_handoff_whatever_the_depth() -> None:
    decision = await Setup(llm=llm_says(Depth.D2, 0.4)).decide()
    assert (decision.action, decision.reason) == (HandoffAction.HANDOFF, LOW_CONFIDENCE)


async def test_the_confidence_threshold_comes_from_the_config() -> None:
    config = HandoffConfig(confidence_threshold=0.3)
    assert (await Setup(llm=llm_says(Depth.D2, 0.4), config=config).decide()).action is HandoffAction.ANSWER


async def test_an_unavailable_classifier_is_a_handoff() -> None:
    decision = await Setup(llm=FakeDepthLlm(fail=True)).decide()
    assert decision.action is HandoffAction.HANDOFF
    assert CLASSIFIER_FALLBACK in decision.signals
    assert LOW_CONFIDENCE in decision.signals


# ------------------------------------------------------------------------- mood and course
async def test_the_patient_asking_for_a_person_is_a_signal_not_a_command() -> None:
    d1 = await Setup(text="cho em gặp nhân viên, em muốn đặt lịch").decide()
    assert d1.action is HandoffAction.ANSWER  # D1 stays answered: the signal lowers the bar to D2, no further
    d2 = await Setup(
        text="cho em gặp nhân viên, kem này dùng buổi tối được không", llm=llm_says(Depth.D2)
    ).decide()
    assert (d2.action, d2.reason) == (HandoffAction.HANDOFF, ASKS_FOR_HUMAN)


async def test_a_repeated_question_from_the_facts_counts() -> None:
    setup = Setup(llm=llm_says(Depth.D2), facts={"repeat_count": 2})
    assert (await setup.decide()).reason == REPEATED_QUESTION
    assert (
        await Setup(llm=llm_says(Depth.D2), facts={"repeat_count": 1}).decide()
    ).action is HandoffAction.ANSWER


async def test_a_repeated_question_flag_of_the_model_counts() -> None:
    setup = Setup(llm=llm_says(Depth.D2, repeated_question=True))
    assert (await setup.decide()).reason == REPEATED_QUESTION


async def test_an_upset_patient_is_handed_off_from_d2() -> None:
    decision = await Setup(
        text="em rất bực vì không ai trả lời, kem này dùng sao", llm=llm_says(Depth.D2)
    ).decide()
    assert decision.action is HandoffAction.HANDOFF


# ---------------------------------------------------------------------------------- context
async def test_within_48h_of_a_procedure_a_d3_goes_to_a_person_and_is_urgent() -> None:
    done = (NOW - timedelta(hours=47)).isoformat()
    decision = await Setup(llm=llm_says(Depth.D3), facts={"last_procedure_at": done}).decide()
    assert (decision.action, decision.reason, decision.urgency) == (
        HandoffAction.HANDOFF,
        POST_PROCEDURE,
        Urgency.URGENT,
    )


async def test_after_the_window_the_same_d3_is_not_handed_off() -> None:
    done = (NOW - timedelta(hours=49)).isoformat()
    decision = await Setup(llm=llm_says(Depth.D3), facts={"last_procedure_at": done}).decide()
    assert decision.action is HandoffAction.ANSWER


async def test_the_post_procedure_window_comes_from_the_config() -> None:
    done = (NOW - timedelta(hours=49)).isoformat()
    config = HandoffConfig(post_procedure_window_hours=72)
    decision = await Setup(llm=llm_says(Depth.D3), config=config, facts={"last_procedure_at": done}).decide()
    assert decision.action is HandoffAction.HANDOFF


async def test_out_of_hours_a_d3_goes_to_a_person_and_a_d2_does_not() -> None:
    night = vn(2026, 10, 3, 22, 30)
    d3 = await Setup(llm=llm_says(Depth.D3), now=night).decide()
    assert (d3.action, d3.reason) == (HandoffAction.HANDOFF, OUT_OF_HOURS)
    d2 = await Setup(llm=llm_says(Depth.D2), now=night).decide()
    assert d2.action is HandoffAction.ANSWER


async def test_work_waiting_for_a_doctor_lowers_the_bar() -> None:
    decision = await Setup(llm=llm_says(Depth.D3), facts={"pending_doctor_work": True}).decide()
    assert decision.action is HandoffAction.HANDOFF


# ----------------------------------------------------------------------------------- autonomy
async def test_an_intent_that_never_runs_without_a_person_is_a_handoff() -> None:
    decision = await Setup(llm=llm_says(Depth.D2, intent="medication_change")).decide()
    assert (decision.action, decision.reason) == (HandoffAction.HANDOFF, EXCEEDS_AUTONOMY)


async def test_an_intent_above_the_agents_level_is_a_handoff_and_at_its_level_it_is_not() -> None:
    config = HandoffConfig(intent_min_level={"booking_change": 1})
    below = await Setup(llm=llm_says(Depth.D2, intent="booking_change"), config=config).decide()
    assert (below.action, below.reason) == (HandoffAction.HANDOFF, EXCEEDS_AUTONOMY)
    at_level = Setup(
        llm=llm_says(Depth.D2, intent="booking_change"), config=config, autonomy_levels={"default": "L1"}
    )
    assert (await at_level.decide()).action is HandoffAction.ANSWER


async def test_a_time_boxed_override_lowers_the_effective_level_until_it_expires() -> None:
    levels = {"default": "L2"}
    override = {"level": "L0", "until": (NOW + timedelta(days=7)).isoformat()}
    agent = replace(
        InMemoryCareStore().add_patient("P900"), autonomy_levels=levels, autonomy_override=override
    )
    assert effective_level(agent, "reply", NOW) == 0
    assert effective_level(agent, "reply", NOW + timedelta(days=8)) == 2
    assert effective_level(replace(agent, autonomy_override=None), "reply", NOW) == 2
    assert (
        effective_level(replace(agent, autonomy_levels={"reply": "L1"}, autonomy_override=None), "reply", NOW)
        == 1
    )


# ------------------------------------------------------------------------------ other events
@pytest.mark.parametrize("kind", [k for k in EventKind if k is not EventKind.PATIENT_MESSAGE])
async def test_a_system_event_is_never_a_question_for_a_person(kind: EventKind) -> None:
    setup = Setup(verified=False, facts={"vip": True})
    event = CareEvent(kind=kind, initiator=Initiator.SYSTEM, patient_ref="P900", occurred_at=NOW)
    decision = await setup.decide(event)
    assert (decision.action, decision.reason) == (HandoffAction.ANSWER, NOT_A_PATIENT_MESSAGE)
    assert setup.llm.calls == []
    assert setup.config_source.reads == 0


# ------------------------------------------------------------------------- patient signals
def test_missing_patient_facts_mean_no_and_identity_follows_the_channel() -> None:
    with_channel = PatientSignals.from_context(
        PatientContext("P900", uuid4(), channel=ChannelTarget("acct-fake", "thread-fake"))
    )
    without = PatientSignals.from_context(PatientContext("P900", uuid4()))
    assert with_channel.verified
    assert not without.verified
    assert not with_channel.vip
    assert not with_channel.complex_history
    assert not with_channel.past_complaint
    assert with_channel.last_procedure_at is None
    assert with_channel.repeat_count == 0


def test_a_malformed_fact_is_ignored() -> None:
    context = PatientContext(
        "P900", uuid4(), facts={"vip": "yes", "last_procedure_at": "not a date", "repeat_count": "3"}
    )
    signals = PatientSignals.from_context(context)
    assert (signals.vip, signals.last_procedure_at, signals.repeat_count) == (False, None, 0)
