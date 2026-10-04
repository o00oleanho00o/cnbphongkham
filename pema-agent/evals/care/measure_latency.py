"""Orchestration latency, the daily tick over 500 fake patients, and the LLM-call counts that feed the cost
estimate (steps 5 and 6 of the recipe).

New module (not a port). EVERY model in this module is a fake that answers at once, so what is timed is only
the orchestration of package M: the queue, the state machine, the skill ``handoff``, the red-flag rules, the
depth rules, routing, the specialists' loop and budget, all in-process with in-memory stores. It is NOT the
time a person waits: the real model adds its own latency per call, which only the GPU run can measure
(``real_run``). The numbers here are the floor that must stay negligible next to that.

What is also counted, per event, is how many model calls the orchestration makes (the classifier, the reply
model, the specialists' model steps): multiplied by the tokens per call of a real run and by the clinic's real
traffic that is the cost estimate. No token number is produced here.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

from evals.care.stats import Latency
from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool
from pema.care.budget import TurnBudget
from pema.care.depth import DEPTH_PROMPT, DepthClassifier
from pema.care.handoff_skill import HANDOFF_INSTRUCTION, HandoffSkill
from pema.care.handoff_types import Depth, DepthLlmOutput, HandoffConfig
from pema.care.loop import CareTurnRunner, TurnStatus
from pema.care.ports import FreeSlot, HarnessDecision, HarnessRequest
from pema.care.priority import CarePriorityQueue
from pema.care.specialists.scope import CareTurnScope
from pema.care.specialists.spec import KNOWLEDGE_ID, REVIEWER_ID, SCHEDULER_ID
from pema.care.testing import (
    DelegationRig,
    FakeChannel,
    FakeClock,
    FakeContextLoader,
    FakeDepthLlm,
    FakeGuard,
    FakeHarness,
    FakeReview,
    FakeScheduler,
    FakeSuggestions,
    FakeTickRules,
    FixedWindow,
    InMemoryCareStore,
    StaticHandoffConfig,
    StaticTexts,
    make_rig,
    vn,
)
from pema.care.testing_routing import MONDAY_10, REF, RoutingRig, make_routing_rig
from pema.care.tick import daily_tick
from pema_contracts.knowledge import KbHit

SAMPLES = 200
"""Timed runs per class of turn."""
WARMUP = 10
"""Untimed runs before the timed ones."""
TICK_PATIENTS = 500
PLAIN_TEXT = "kem này dùng buổi tối được không ạ"
ADMIN_TEXT = "đặt lịch giúp em tuần sau nhé"
RED_FLAG_TEXT = "em bị chảy máu nhiều ở chỗ tiêm"
HIT = KbHit(
    source_id="kb-aftercare-1",
    source_name="Hướng dẫn sau điều trị (mẫu)",
    title="Chăm sóc da",
    content="Tránh nắng 48 giờ.",
    score=0.9,
)
SLOT = FreeSlot(starts_at=vn(2026, 10, 7, 9, 0), duration_min=30)


@dataclass(frozen=True)
class TurnClass:
    name: str
    latency: Latency
    depth_model_calls: float
    """Mean calls of the depth classifier's model per turn."""
    reply_model_calls: float
    """Mean calls of the reply model (the shared pipeline) per turn."""
    specialist_model_steps: float
    """Mean model steps of the specialists per turn (scripted: one step is one model call)."""
    outcome: str


@dataclass(frozen=True)
class TickRow:
    draft_share: float
    patients: int
    batches: int
    findings: int
    drafts: int
    tick_ms: float
    drain_ms: float
    harness_calls: int
    depth_model_calls: int


@dataclass(frozen=True)
class LatencyReport:
    samples: int
    classes: list[TurnClass]
    ticks: list[TickRow]
    classifier_prompt_chars_mean: float
    classifier_prompt_chars_max: int
    reply_overhead_note: str = ""


# ----------------------------------------------------------------------------------- timing helper
async def _time(runs: int, make: Callable[[], Awaitable[object]]) -> list[int]:
    samples: list[int] = []
    for _ in range(runs):
        started = time.perf_counter_ns()
        await make()
        samples.append(time.perf_counter_ns() - started)
    return samples


@dataclass
class _Delegation:
    """One ``DelegationRig`` with the two scripted models that play Knowledge and Scheduler."""

    rig: DelegationRig
    knowledge: ScriptedModel
    scheduler: ScriptedModel

    @classmethod
    def build(cls) -> _Delegation:
        knowledge = ScriptedModel(
            [
                lambda: goi_tool("kb_search", {"question": "sau laser"}, call_id=f"k-{uuid4().hex[:6]}"),
                lambda: goi_tool(
                    "submit_result",
                    {"summary": "Tránh nắng", "confidence": 0.8},
                    call_id=f"s-{uuid4().hex[:6]}",
                ),
            ]
        )
        scheduler = ScriptedModel(
            [
                lambda: goi_tool(
                    "appointment.search_slots",
                    {"from_date": "2026-10-07", "to_date": "2026-10-14"},
                    call_id=f"a-{uuid4().hex[:6]}",
                ),
                lambda: goi_tool(
                    "submit_result",
                    {"summary": "Có 1 khung giờ", "confidence": 0.9},
                    call_id=f"b-{uuid4().hex[:6]}",
                ),
            ]
        )
        rig = make_rig(
            models={KNOWLEDGE_ID: knowledge, SCHEDULER_ID: scheduler}, slots=[SLOT], hits={"sau laser": [HIT]}
        )
        return cls(rig, knowledge, scheduler)

    @property
    def steps(self) -> int:
        return self.knowledge.count + self.scheduler.count


async def _measure_messages(
    name: str, text: str, *, delegations: tuple[str, ...] = (), runs: int = SAMPLES
) -> TurnClass:
    """``runs`` patient messages in AUTO. ``delegations`` lists the specialists the reply model calls."""
    rig = make_routing_rig(now=MONDAY_10)
    inner = [_Delegation.build() for _ in range(runs + WARMUP if delegations else 0)]
    cursor = iter(inner)
    statuses: set[str] = set()

    if delegations:

        async def process(request: HarnessRequest) -> HarnessDecision:
            rig.harness.requests.append(request)
            current = next(cursor)
            scope = CareTurnScope(
                care_agent=current.rig.scope.care_agent,
                patient_ref=REF,
                budget=TurnBudget(clock=current.rig.clock),
                turn_key=f"turn-{uuid4().hex[:8]}",
            )
            for specialist in delegations:
                await current.rig.service.delegate(scope, specialist, "tìm giúp", None)
            return rig.harness.decision

        rig.harness.process = process  # type: ignore[method-assign]

    async def one() -> None:
        statuses.add((await rig.message(text)).status.value)

    for _ in range(WARMUP):  # imports, caches and the first allocations are not the orchestration
        await one()
    depth_before, reply_before = len(rig.llm.calls), rig.harness.calls
    steps_before = sum(d.steps for d in inner)
    statuses.clear()
    samples = await _time(runs, one)
    return TurnClass(
        name=name,
        latency=Latency.from_ns(samples),
        depth_model_calls=(len(rig.llm.calls) - depth_before) / runs,
        reply_model_calls=(rig.harness.calls - reply_before) / runs,
        specialist_model_steps=(sum(d.steps for d in inner) - steps_before) / runs,
        outcome=", ".join(sorted(statuses)),
    )


async def _measure_handoffs(name: str, text: str, depth: Depth, *, runs: int = SAMPLES) -> TurnClass:
    """A handoff opens a round, so every sample needs its own rig (built before the timer starts)."""
    rigs: list[RoutingRig] = []
    for _ in range(runs):
        rig = make_routing_rig(now=MONDAY_10, depth=depth)
        for index in range(3):
            rig.directory.add_staff("doctor" if index == 0 else "cs_staff", load=index)
        rigs.append(rig)
    statuses: set[str] = set()
    index = 0

    async def one() -> None:
        nonlocal index
        rig = rigs[index]
        index += 1
        outcome = await rig.message(text)
        statuses.add(outcome.status.value)

    samples = await _time(runs, one)
    return TurnClass(
        name=name,
        latency=Latency.from_ns(samples),
        depth_model_calls=sum(len(r.llm.calls) for r in rigs) / runs,
        reply_model_calls=sum(r.harness.calls for r in rigs) / runs,
        specialist_model_steps=0.0,
        outcome=", ".join(sorted(statuses)),
    )


# ------------------------------------------------------------------------------------------- the tick
async def _measure_tick(draft_share: float, *, patients: int = TICK_PATIENTS) -> TickRow:
    clock = FakeClock(vn(2026, 10, 5, 6, 0))
    care = InMemoryCareStore()
    refs: dict[object, str] = {}
    needs: dict[str, bool] = {}
    wanted = round(patients * draft_share)
    for number in range(patients):
        ref = f"P{1000 + number}"
        agent = care.add_patient(ref)
        refs[agent.id] = ref
        needs[ref] = number < wanted
    rules = FakeTickRules(needs_draft=needs, refs=refs)  # type: ignore[arg-type]
    queue = CarePriorityQueue()
    clinic_id = next(iter(care.agents.values())).clinic_id
    started = time.perf_counter_ns()
    report = await daily_tick(clinic_id, clock(), store=care, rules=rules, queue=queue)
    tick_ns = time.perf_counter_ns() - started

    llm = FakeDepthLlm(DepthLlmOutput(depth=Depth.D2, confidence=0.9))
    harness = FakeHarness()
    skill = HandoffSkill(
        classifier=DepthClassifier(llm),
        config_source=StaticHandoffConfig(HandoffConfig()),
        texts=StaticTexts(),
        clock=clock,
        window=FixedWindow(),
    )
    runner = CareTurnRunner(
        store=care,
        context_loader=FakeContextLoader(),
        harness=harness,
        channel=FakeChannel(),
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=FixedWindow(),
        guard=FakeGuard(),
        clock=clock,
        handoff=skill,
        suggestions=FakeSuggestions(),
    )
    started = time.perf_counter_ns()
    while (item := queue.pop_nowait()) is not None:
        outcome = await runner.run_turn(item.care_agent_id, item.event)
        if outcome.status is not TurnStatus.DRAFTED:
            raise RuntimeError(f"a tick draft ended as {outcome.status.value}")
    drain_ns = time.perf_counter_ns() - started
    return TickRow(
        draft_share=draft_share,
        patients=patients,
        batches=report.batches,
        findings=report.findings,
        drafts=report.drafts_enqueued,
        tick_ms=tick_ns / 1_000_000,
        drain_ms=drain_ns / 1_000_000,
        harness_calls=harness.calls,
        depth_model_calls=len(llm.calls),
    )


def classifier_prompt_sizes(texts: list[str]) -> tuple[float, int]:
    """Characters of the prompt the classifier model receives for each text (a size, not a token count)."""
    schema = DepthLlmOutput.model_json_schema()
    sizes = [
        len(DEPTH_PROMPT.format(instruction=HANDOFF_INSTRUCTION, schema=schema, text=text)) for text in texts
    ]
    return (sum(sizes) / len(sizes) if sizes else 0.0, max(sizes, default=0))


async def measure_latency(sample_texts: list[str], *, runs: int = SAMPLES) -> LatencyReport:
    classes = [
        await _measure_messages("D1 by rules (booking), reply model only", ADMIN_TEXT, runs=runs),
        await _measure_messages("D2: depth model + reply model", PLAIN_TEXT, runs=runs),
        await _measure_messages(
            "D2 + Reviewer delegation (checklist, no model)",
            PLAIN_TEXT,
            delegations=(REVIEWER_ID,),
            runs=runs,
        ),
        await _measure_messages(
            "D2 + Knowledge + Scheduler delegation (2 specialists, 2 scripted steps each)",
            PLAIN_TEXT,
            delegations=(KNOWLEDGE_ID, SCHEDULER_ID),
            runs=runs,
        ),
        await _measure_handoffs(
            "D4: depth model, then handoff round + routing", PLAIN_TEXT, Depth.D4, runs=runs
        ),
        await _measure_handoffs(
            "D5 red flag: no model, handoff round + routing", RED_FLAG_TEXT, Depth.D2, runs=runs
        ),
    ]
    ticks = [await _measure_tick(share) for share in (0.0, 0.1, 1.0)]
    mean_chars, max_chars = classifier_prompt_sizes(sample_texts)
    return LatencyReport(runs, classes, ticks, mean_chars, max_chars)
