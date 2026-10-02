"""Control state machine, holding message and the turn loop with the skill ``handoff`` (package M, step M2b).

New tests (no zalo-agent original). Fakes, fake clock, no database (the SQL side is ``test_care_control_store``).
The ``FakeHarness`` is the "answering model" and ``FakeDepthLlm`` the "classifying model": every test that is
about "no model is called" counts both.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from pema.care.control import (
    HOLDING_FAILED,
    HOLDING_SENT,
    CareControl,
    build_summary,
    transition_action,
)
from pema.care.depth import DepthClassifier
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import HandoffSkill
from pema.care.handoff_types import (
    ControlConfigError,
    Depth,
    DepthLlmOutput,
    HandoffAction,
    HandoffConfig,
    HandoffDecision,
    InvalidTransitionError,
    Urgency,
)
from pema.care.loop import (
    HANDOFF_FAILED,
    HANDOFF_REQUESTED,
    SKIPPED_STATE_PREFIX,
    SUGGESTED_STATE_PREFIX,
    CareEventBus,
    CareTurnRunner,
    CareTurnWorker,
    TurnStatus,
)
from pema.care.models import ControlState
from pema.care.ports import (
    CareAgentSnapshot,
    ChannelTarget,
    HandoffRequestSnapshot,
    PatientContext,
)
from pema.care.priority import CarePriorityQueue
from pema.care.testing import (
    FakeChannel,
    FakeClock,
    FakeContextLoader,
    FakeDepthLlm,
    FakeGuard,
    FakeHarness,
    FakeReview,
    FakeScheduler,
    FakeSuggestions,
    FixedWindow,
    InMemoryCareStore,
    InMemoryControlStore,
    StaticHandoffConfig,
    StaticTexts,
    vn,
)
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType, Role

REF = "P900"
NOW = vn(2026, 10, 3, 10, 0)
RED_FLAG_TEXT = "em bị chảy máu nhiều ở chỗ tiêm"
PLAIN_TEXT = "kem này dùng buổi tối được không ạ"


def staff_ctx(role: Role = Role.CS_STAFF, user: UUID | None = None) -> ActionContext:
    return ActionContext(
        clinic_id=UUID(int=1), actor_type=ActorType.USER, actor_user_id=user or uuid4(), actor_role=role
    )


def other_ctx(actor_type: ActorType, role: Role | None = None) -> ActionContext:
    return ActionContext(clinic_id=UUID(int=1), actor_type=actor_type, actor_user_id=uuid4(), actor_role=role)


def llm_says(depth: Depth, confidence: float = 0.9) -> FakeDepthLlm:
    return FakeDepthLlm(DepthLlmOutput(depth=depth, confidence=confidence))


def decision(depth: Depth = Depth.D4, urgency: Urgency = Urgency.URGENT) -> HandoffDecision:
    return HandoffDecision(
        action=HandoffAction.HANDOFF,
        reason="depth_at_or_above_threshold",
        depth=depth,
        confidence=0.8,
        required_skill="medical",
        urgency=urgency,
        signals=("depth_at_or_above_threshold",),
    )


def event(kind: EventKind = EventKind.PATIENT_MESSAGE, at_minute: int = 0) -> CareEvent:
    initiator = Initiator.PATIENT if kind is EventKind.PATIENT_MESSAGE else Initiator.SYSTEM
    return CareEvent(
        kind=kind,
        initiator=initiator,
        patient_ref=REF,
        occurred_at=NOW + timedelta(minutes=at_minute),
    )


@dataclass
class Rig:
    care: InMemoryCareStore
    controls: InMemoryControlStore
    harness: FakeHarness
    channel: FakeChannel
    suggestions: FakeSuggestions
    llm: FakeDepthLlm
    clock: FakeClock
    config: StaticHandoffConfig
    control: CareControl
    runner: CareTurnRunner
    agent: CareAgentSnapshot
    texts: StaticTexts
    queue: CarePriorityQueue
    bus: CareEventBus

    @property
    def state(self) -> ControlState:
        return self.care.states.get(self.agent.patient_id, ControlState.AUTO)

    def actions(self) -> list[str]:
        return [row.action_type for row in self.care.actions]

    async def run(self, *events: CareEvent) -> list[TurnStatus]:
        statuses: list[TurnStatus] = []
        for item in events:
            statuses.append((await self.runner.run_turn(self.agent.id, item)).status)
        return statuses


def make_rig(
    *,
    text: str = PLAIN_TEXT,
    llm: FakeDepthLlm | None = None,
    config: HandoffConfig | None = None,
    channel: FakeChannel | None = None,
    loader: FakeContextLoader | None = None,
    with_suggestions: bool = True,
) -> Rig:
    care = InMemoryCareStore()
    agent = care.add_patient(REF)
    controls = InMemoryControlStore(care)
    harness = FakeHarness()
    channel = channel or FakeChannel()
    suggestions = FakeSuggestions()
    llm = llm or llm_says(Depth.D2)
    clock = FakeClock(NOW)
    config_source = StaticHandoffConfig(config)
    texts = StaticTexts(text)
    control = CareControl(store=controls, config_source=config_source, channel=channel, clock=clock)
    skill = HandoffSkill(
        classifier=DepthClassifier(llm),
        config_source=config_source,
        texts=texts,
        clock=clock,
        window=FixedWindow(),
    )
    runner = CareTurnRunner(
        store=care,
        context_loader=loader or FakeContextLoader(),
        harness=harness,
        channel=channel,
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=FixedWindow(),
        guard=FakeGuard(),
        clock=clock,
        handoff=skill,
        requester=control,
        suggestions=suggestions if with_suggestions else None,
        cap_per_day=2,
    )
    queue = CarePriorityQueue()
    return Rig(
        care,
        controls,
        harness,
        channel,
        suggestions,
        llm,
        clock,
        config_source,
        control,
        runner,
        agent,
        texts,
        queue,
        CareEventBus(care, queue),
    )


async def open_round(rig: Rig, depth: Depth = Depth.D4, urgency: Urgency = Urgency.URGENT) -> None:
    context = PatientContext(
        REF, rig.agent.patient_id, channel=ChannelTarget("acct-fake", "thread-fake"), facts={"vip": True}
    )
    await rig.control.request_handoff(rig.agent, event(), context, decision(depth, urgency))


async def to_staff(rig: Rig, staff: ActionContext | None = None) -> ActionContext:
    ctx = staff or staff_ctx()
    await open_round(rig)
    await rig.control.accept(ctx, rig.agent.patient_id)
    return ctx


# ------------------------------------------------------------------ request: AUTO -> HANDOFF_ROUTING
async def test_a_request_moves_the_conversation_to_routing_and_stores_a_masked_summary() -> None:
    rig = make_rig()
    context = PatientContext(
        REF,
        rig.agent.patient_id,
        channel=ChannelTarget("acct-fake", "thread-fake"),
        facts={"vip": True, "contact": "0901234567", "note": "gọi lại số 0912345678 giúp"},
    )
    opened = await rig.control.request_handoff(rig.agent, event(), context, decision())
    assert opened.created
    assert rig.state is ControlState.HANDOFF_ROUTING
    request = opened.request
    assert (request.depth, request.urgency, request.required_skill) == ("D4", "urgent", "medical")
    assert request.candidates == ()  # M2c fills them
    assert request.outcome is None
    assert "0901234567" not in request.summary
    assert "0912345678" not in request.summary
    assert REF in request.summary
    assert "D4" in request.summary
    assert transition_action(ControlState.AUTO, ControlState.HANDOFF_ROUTING, "agent") in rig.actions()


def test_the_summary_never_holds_the_message_text() -> None:
    ctx = PatientContext(REF, uuid4(), facts={"vip": True})
    summary = build_summary(event(), ctx, decision())
    assert "vip: True" in summary
    assert "chảy máu" not in summary


async def test_critical_is_stored_as_urgent_and_keeps_depth_d5() -> None:
    rig = make_rig()
    await open_round(rig, Depth.D5, Urgency.CRITICAL)
    (request,) = rig.controls.requests
    assert (request.depth, request.urgency) == ("D5", "urgent")


# ------------------------------------------------------------------------ the holding message
async def test_exactly_one_template_holding_message_is_sent() -> None:
    rig = make_rig()
    await open_round(rig, urgency=Urgency.NORMAL)
    assert len(rig.channel.sent) == 1
    target, text, proactive = rig.channel.sent[0]
    assert target == ChannelTarget("acct-fake", "thread-fake")
    assert text == HandoffConfig().holding_message
    assert proactive is False  # the patient wrote: not counted against the daily cap
    assert HOLDING_SENT in rig.actions()


async def test_an_urgent_request_gets_the_urgent_template() -> None:
    rig = make_rig()
    await open_round(rig, Depth.D5, Urgency.CRITICAL)
    assert rig.channel.sent[0][1] == HandoffConfig().holding_message_urgent


async def test_the_holding_templates_come_from_the_config() -> None:
    rig = make_rig(config=HandoffConfig(holding_message="Mẫu giữ chỗ (thử)"))
    await open_round(rig, urgency=Urgency.NORMAL)
    assert rig.channel.sent[0][1] == "Mẫu giữ chỗ (thử)"


async def test_a_second_request_during_routing_changes_nothing_and_sends_nothing() -> None:
    rig = make_rig()
    await open_round(rig)
    first = rig.controls.requests[0]
    await open_round(rig)
    await open_round(rig, Depth.D5, Urgency.CRITICAL)
    assert rig.controls.requests == [first]
    assert len(rig.channel.sent) == 1


async def test_several_patient_messages_during_routing_get_one_holding_message_and_no_answer() -> None:
    rig = make_rig(text=RED_FLAG_TEXT)
    for minute in range(4):
        await rig.bus.publish(event(at_minute=minute))
    processed = await CareTurnWorker(rig.queue, rig.runner).run_until_idle()
    assert processed == 4
    assert len(rig.channel.sent) == 1
    assert rig.channel.sent[0][1] == HandoffConfig().holding_message_urgent
    assert rig.harness.requests[0].persona == "care_agent_suggest"  # only suggestions, never an answer
    assert all(r.persona == "care_agent_suggest" for r in rig.harness.requests)
    assert len(rig.controls.requests) == 1
    assert rig.state is ControlState.HANDOFF_ROUTING


async def test_no_holding_message_for_an_event_the_patient_did_not_write() -> None:
    rig = make_rig()
    context = PatientContext(REF, rig.agent.patient_id, channel=ChannelTarget("acct-fake", "thread-fake"))
    opened = await rig.control.request_handoff(rig.agent, event(EventKind.MILESTONE_DUE), context, decision())
    assert opened.created
    assert rig.channel.sent == []


async def test_no_holding_message_without_a_verified_channel() -> None:
    rig = make_rig()
    context = PatientContext(REF, rig.agent.patient_id, channel=None)
    await rig.control.request_handoff(rig.agent, event(), context, decision())
    assert rig.channel.sent == []
    assert rig.state is ControlState.HANDOFF_ROUTING


async def test_a_failed_holding_send_is_logged_and_never_retried() -> None:
    rig = make_rig(channel=FakeChannel(ok=False))
    await open_round(rig)
    await open_round(rig)
    assert len(rig.channel.sent) == 1
    assert HOLDING_FAILED in rig.actions()
    assert rig.state is ControlState.HANDOFF_ROUTING  # the staff is still asked


# --------------------------------------------------------------- the loop with the skill wired in
async def test_a_red_flag_message_goes_to_a_doctor_without_calling_any_model() -> None:
    rig = make_rig(text=RED_FLAG_TEXT, llm=llm_says(Depth.D1))
    (status,) = await rig.run(event())
    assert status is TurnStatus.HANDOFF
    assert rig.llm.calls == []  # the classifying model
    assert rig.harness.calls == 0  # the answering model
    assert rig.state is ControlState.HANDOFF_ROUTING
    (request,) = rig.controls.requests
    assert (request.depth, request.urgency) == ("D5", "urgent")
    assert HANDOFF_REQUESTED in rig.actions()
    assert [text for _, text, _ in rig.channel.sent] == [HandoffConfig().holding_message_urgent]


async def test_an_unverified_patient_asking_d2_is_handed_off_by_the_loop() -> None:
    rig = make_rig(loader=FakeContextLoader(channel=None), llm=llm_says(Depth.D2))
    (status,) = await rig.run(event())
    assert status is TurnStatus.HANDOFF
    assert rig.harness.calls == 0
    assert rig.state is ControlState.HANDOFF_ROUTING


async def test_a_question_the_agent_may_answer_does_not_touch_the_state() -> None:
    rig = make_rig(llm=llm_says(Depth.D2))
    (status,) = await rig.run(event())
    assert status is not TurnStatus.HANDOFF
    assert rig.state is ControlState.AUTO
    assert rig.controls.requests == []
    assert rig.harness.calls == 1


async def test_a_failing_requester_leaves_the_state_in_auto_so_the_next_event_decides_again() -> None:
    rig = make_rig(text=RED_FLAG_TEXT)

    class Broken:
        async def request_handoff(
            self,
            agent: CareAgentSnapshot,
            event: CareEvent,
            context: PatientContext,
            decision: HandoffDecision,
            now: object,
        ) -> None:
            raise RuntimeError("database gone")

    rig.runner._requester = Broken()  # type: ignore[assignment]
    (status,) = await rig.run(event())
    assert status is TurnStatus.FAILED
    assert HANDOFF_FAILED in rig.actions()
    assert rig.state is ControlState.AUTO


# ---------------------------------------------------- HANDOFF_ROUTING / STAFF: only suggestions
async def test_in_staff_a_patient_message_gets_a_suggestion_for_staff_and_is_never_sent() -> None:
    rig = make_rig()
    await to_staff(rig)
    sent_before = len(rig.channel.sent)
    (status,) = await rig.run(event(at_minute=5))
    assert status is TurnStatus.SUGGESTED
    ((agent_id, ref, text, state),) = rig.suggestions.items
    assert (agent_id, ref, state) == (rig.agent.id, REF, ControlState.STAFF)
    assert text
    assert len(rig.channel.sent) == sent_before
    assert rig.llm.calls == []  # the skill is not asked again: a person already has the patient
    assert SUGGESTED_STATE_PREFIX + "staff" in rig.actions()


async def test_in_routing_a_patient_message_also_gets_a_suggestion() -> None:
    rig = make_rig()
    await open_round(rig)
    (status,) = await rig.run(event(at_minute=1))
    assert status is TurnStatus.SUGGESTED
    assert rig.suggestions.items[0][3] is ControlState.HANDOFF_ROUTING


async def test_in_staff_other_events_only_write_a_paused_row() -> None:
    rig = make_rig()
    await to_staff(rig)
    harness_before = rig.harness.calls
    statuses = await rig.run(event(EventKind.MILESTONE_DUE), event(EventKind.DAILY_TICK))
    assert statuses == [TurnStatus.SKIPPED_STATE, TurnStatus.SKIPPED_STATE]
    assert rig.harness.calls == harness_before
    assert rig.suggestions.items == []
    assert rig.actions().count(SKIPPED_STATE_PREFIX + "staff") == 2


async def test_without_a_suggestion_sink_the_loop_behaves_as_in_m2a() -> None:
    rig = make_rig(with_suggestions=False)
    await to_staff(rig)
    (status,) = await rig.run(event(at_minute=5))
    assert status is TurnStatus.SKIPPED_STATE
    assert rig.harness.calls == 0


async def test_a_failed_suggestion_is_a_failed_turn_and_sends_nothing() -> None:
    rig = make_rig()
    rig.suggestions.ok = False
    await to_staff(rig)
    sent_before = len(rig.channel.sent)
    (status,) = await rig.run(event(at_minute=5))
    assert status is TurnStatus.FAILED
    assert len(rig.channel.sent) == sent_before


# ------------------------------------------------------------------ accept: HANDOFF_ROUTING -> STAFF
async def test_staff_accepts_and_becomes_the_owner() -> None:
    rig = make_rig()
    await open_round(rig)
    staff = staff_ctx(Role.DOCTOR)
    request = await rig.control.accept(staff, rig.agent.patient_id)
    assert rig.state is ControlState.STAFF
    assert request.accepted_by == staff.actor_user_id
    assert request.outcome == "accepted"
    snapshot = await rig.controls.get_control(rig.agent.patient_id)
    assert snapshot.staff_owner == staff.actor_user_id
    assert f"control:handoff_routing_to_staff:staff:{staff.actor_user_id}" in rig.actions()


@pytest.mark.parametrize(
    "ctx",
    [
        staff_ctx(Role.PATIENT),
        other_ctx(ActorType.SYSTEM),
        other_ctx(ActorType.AGENT),
        other_ctx(ActorType.SCHEDULER),
        ActionContext(clinic_id=UUID(int=1), actor_type=ActorType.USER, actor_role=Role.CS_STAFF),
    ],
)
async def test_only_a_signed_in_staff_member_may_accept_decline_or_release(ctx: ActionContext) -> None:
    rig = make_rig()
    await open_round(rig)
    patient_id = rig.agent.patient_id
    with pytest.raises(PermissionError):
        await rig.control.accept(ctx, patient_id)
    with pytest.raises(PermissionError):
        await rig.control.decline(ctx, patient_id, "bận")
    with pytest.raises(PermissionError):
        await rig.control.release_to_auto(ctx, patient_id, "ghi chú")
    assert rig.state is ControlState.HANDOFF_ROUTING


async def test_a_second_accept_is_refused() -> None:
    rig = make_rig()
    await to_staff(rig)
    with pytest.raises(InvalidTransitionError):
        await rig.control.accept(staff_ctx(), rig.agent.patient_id)


async def test_accept_without_a_request_is_refused() -> None:
    rig = make_rig()
    with pytest.raises(InvalidTransitionError):
        await rig.control.accept(staff_ctx(), rig.agent.patient_id)


# -------------------------------------------------------------------------------------- decline
async def test_a_decline_keeps_the_round_open_and_tells_m2c() -> None:
    rig = make_rig()
    await open_round(rig)
    seen: list[tuple[HandoffRequestSnapshot, UUID, str, UUID | None]] = []

    class Routing:
        async def on_declined(
            self, request: HandoffRequestSnapshot, staff_id: UUID, reason: str, suggest_user_id: UUID | None
        ) -> None:
            seen.append((request, staff_id, reason, suggest_user_id))

    control = CareControl(
        store=rig.controls, config_source=rig.config, channel=rig.channel, clock=rig.clock, routing=Routing()
    )
    staff, suggested = staff_ctx(), uuid4()
    await control.decline(staff, rig.agent.patient_id, "đang bận ca khác", suggested)
    assert rig.state is ControlState.HANDOFF_ROUTING
    ((request, staff_id, reason, suggest),) = seen
    assert (staff_id, reason, suggest) == (staff.actor_user_id, "đang bận ca khác", suggested)
    assert request.outcome is None
    assert f"control:handoff_routing_declined:staff:{staff.actor_user_id}" in rig.actions()


async def test_a_decline_outside_routing_is_refused() -> None:
    rig = make_rig()
    with pytest.raises(InvalidTransitionError):
        await rig.control.decline(staff_ctx(), rig.agent.patient_id, "x")


# ---------------------------------------------------------------------------- release: STAFF -> AUTO
async def test_staff_release_returns_the_conversation_to_auto_with_a_note_in_the_memory() -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    snapshot = await rig.control.release_to_auto(staff, rig.agent.patient_id, "  Khách thích nhắn buổi tối  ")
    assert snapshot.state is ControlState.AUTO
    assert rig.state is ControlState.AUTO
    assert snapshot.release_note == "Khách thích nhắn buổi tối"
    assert rig.controls.memory == [(rig.agent.id, "Khách thích nhắn buổi tối", "staff")]
    assert (
        transition_action(ControlState.STAFF, ControlState.AUTO, f"staff:{staff.actor_user_id}")
        in rig.actions()
    )


async def test_the_release_note_is_pii_masked_and_limited_to_500_characters() -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    note = "Gọi 0901234567 sau 18h. " + "x" * 600
    await rig.control.release_to_auto(staff, rig.agent.patient_id, note)
    ((_, fact, _),) = rig.controls.memory
    assert "0901234567" not in fact
    assert len(fact) <= 500


async def test_an_empty_note_writes_no_memory() -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    await rig.control.release_to_auto(staff, rig.agent.patient_id, "   ")
    assert rig.controls.memory == []


@pytest.mark.parametrize("actor", [Role.PATIENT, None])
async def test_a_patient_or_the_system_cannot_release_to_auto(actor: Role | None) -> None:
    rig = make_rig()
    await to_staff(rig)
    ctx = staff_ctx(Role.PATIENT) if actor is Role.PATIENT else other_ctx(ActorType.SYSTEM)
    with pytest.raises(PermissionError):
        await rig.control.release_to_auto(ctx, rig.agent.patient_id, "x")
    assert rig.state is ControlState.STAFF


async def test_the_agent_itself_cannot_release_to_auto() -> None:
    rig = make_rig()
    await to_staff(rig)
    with pytest.raises(PermissionError):
        await rig.control.release_to_auto(other_ctx(ActorType.AGENT), rig.agent.patient_id, "x")
    assert rig.state is ControlState.STAFF


@pytest.mark.parametrize("prepare", ["auto", "routing"])
async def test_release_is_only_possible_from_staff(prepare: str) -> None:
    rig = make_rig()
    if prepare == "routing":
        await open_round(rig)
    with pytest.raises(InvalidTransitionError):
        await rig.control.release_to_auto(staff_ctx(), rig.agent.patient_id, "x")


async def test_after_the_release_the_agent_answers_again() -> None:
    rig = make_rig(llm=llm_says(Depth.D2))
    staff = await to_staff(rig)
    await rig.control.release_to_auto(staff, rig.agent.patient_id, "ok")
    harness_before = rig.harness.calls
    await rig.run(event(at_minute=30))
    assert rig.harness.calls == harness_before + 1


# ---------------------------------------------------------------- release with a lower level
async def test_a_release_may_lower_the_level_for_a_time() -> None:
    rig = make_rig()
    rig.care.agents[rig.agent.id] = CareAgentSnapshot(
        rig.agent.id,
        rig.agent.clinic_id,
        rig.agent.patient_id,
        "patient_channel",
        autonomy_levels={"default": "L2"},
    )
    staff = await to_staff(rig)
    until = NOW + timedelta(days=7)
    await rig.control.release_to_auto(staff, rig.agent.patient_id, "ok", override_level=0, until=until)
    ((agent_id, override),) = rig.controls.override_log
    assert (agent_id, override.level, override.until) == (rig.agent.id, 0, until)
    stored = rig.care.agents[rig.agent.id].autonomy_override
    assert stored == {"level": "L0", "until": until.isoformat()}
    assert "autonomy:override_set:level0" in rig.actions()


async def test_a_release_cannot_raise_the_level() -> None:
    rig = make_rig()  # level L0 everywhere
    staff = await to_staff(rig)
    with pytest.raises(ValueError, match="lower"):
        await rig.control.release_to_auto(staff, rig.agent.patient_id, "ok", override_level=1)
    assert rig.state is ControlState.STAFF  # nothing happened


@pytest.mark.parametrize(("level", "until_days"), [(3, 1), (-1, 1), (0, -1), (0, 0)])
async def test_an_invalid_override_is_refused_before_anything_changes(level: int, until_days: int) -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    with pytest.raises(ValueError, match=r"override|level"):
        await rig.control.release_to_auto(
            staff, rig.agent.patient_id, "ok", override_level=level, until=NOW + timedelta(days=until_days)
        )
    assert rig.state is ControlState.STAFF
    assert rig.controls.memory == []


async def test_until_without_a_level_is_refused() -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    with pytest.raises(ValueError, match="until"):
        await rig.control.release_to_auto(staff, rig.agent.patient_id, "ok", until=NOW + timedelta(days=1))


# ----------------------------------------------------- no way back to AUTO except staff, never by time
async def test_time_never_returns_a_conversation_to_auto() -> None:
    rig = make_rig()
    await to_staff(rig)
    for days in (1, 30, 365):
        rig.clock.advance(timedelta(days=days))
        await rig.bus.publish(event(at_minute=days))
        await CareTurnWorker(rig.queue, rig.runner).run_until_idle()
        assert rig.state is ControlState.STAFF
    snapshot = await rig.controls.get_control(rig.agent.patient_id)
    assert snapshot.state is ControlState.STAFF
    assert snapshot.auto_release_after is None


async def test_routing_does_not_expire_either() -> None:
    rig = make_rig()
    await open_round(rig)
    rig.clock.advance(timedelta(days=30))
    await rig.run(event(at_minute=1))
    assert rig.state is ControlState.HANDOFF_ROUTING


async def test_auto_release_after_defaults_to_null_and_needs_the_config_flag() -> None:
    rig = make_rig()
    staff = await to_staff(rig)
    assert (await rig.controls.get_control(rig.agent.patient_id)).auto_release_after is None
    with pytest.raises(ControlConfigError):
        await rig.control.set_auto_release_after(staff, rig.agent.patient_id, timedelta(hours=6))
    assert (await rig.controls.get_control(rig.agent.patient_id)).auto_release_after is None


async def test_with_the_flag_on_the_value_is_stored_but_time_still_does_not_release() -> None:
    rig = make_rig(config=HandoffConfig(allow_auto_release=True))
    staff = await to_staff(rig)
    await rig.control.set_auto_release_after(staff, rig.agent.patient_id, timedelta(hours=6))
    assert (await rig.controls.get_control(rig.agent.patient_id)).auto_release_after == timedelta(hours=6)
    rig.clock.advance(timedelta(days=10))
    await rig.run(event(at_minute=1))
    assert rig.state is ControlState.STAFF  # no sweeper reads the value (a separate decision)
    await rig.control.set_auto_release_after(staff, rig.agent.patient_id, None)
    assert (await rig.controls.get_control(rig.agent.patient_id)).auto_release_after is None


async def test_a_non_positive_auto_release_is_refused() -> None:
    rig = make_rig(config=HandoffConfig(allow_auto_release=True))
    staff = await to_staff(rig)
    with pytest.raises(ValueError, match="positive"):
        await rig.control.set_auto_release_after(staff, rig.agent.patient_id, timedelta(0))


async def test_only_staff_may_set_auto_release() -> None:
    rig = make_rig(config=HandoffConfig(allow_auto_release=True))
    await to_staff(rig)
    with pytest.raises(PermissionError):
        await rig.control.set_auto_release_after(
            other_ctx(ActorType.SYSTEM), rig.agent.patient_id, timedelta(hours=1)
        )


def test_no_module_reads_auto_release_after_to_flip_a_state() -> None:
    """The column is written by ``set_auto_release_after`` only; no code path reads it to return to AUTO."""
    import pathlib

    care_dir = pathlib.Path(__file__).resolve().parents[2] / "pema" / "care"
    readers: Sequence[str] = [
        path.name
        for path in care_dir.glob("*.py")
        if "auto_release_after" in path.read_text(encoding="utf-8")
        and path.name
        not in {"control.py", "control_store.py", "models.py", "ports.py", "testing.py", "handoff_types.py"}
    ]
    assert list(readers) == []
