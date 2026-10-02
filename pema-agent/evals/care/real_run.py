"""The measurements that need a REAL model (Ollama + Qwen3-8B on the GPU box, or any provider).

New module (not a port). NOT run on the Windows development box: it has no Ollama and no GPU, the local model
is switched off in this repository ("TẠM TẮT LLM LOCAL"), and no number in ``report.md`` comes from here until
somebody runs it where a model exists. The plumbing is tested with a scripted model (``test_care_eval``); what
a real model says is not.

What it measures, per run:

* the depth classifier on every labelled case through ``TextGeneratorDepthLlm`` over ``ProviderTextGenerator``
  (the real single-shot completion): accuracy per class against the labels, handoff precision/recall and the
  false negatives, how many replies were not valid JSON (the "classifier unavailable" fallback), and for every
  model call: latency p50/p95 and tokens (as the provider reports them);
* the Knowledge and Scheduler specialists with the real model (fake knowledge base and slots): latency and
  tokens per delegation, how many came back ``needs_human``;
* from those, the model part of the cost per patient per month for an explicit traffic assumption.

What it does NOT measure: the reply model of the shared pipeline. The adapter that gives a care turn to the
engine belongs to the wiring package and is not in the repository, so "patient message to reply draft" with a
real reply model has no entry point yet (open item in the report).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from evals.care.cases import CareCase
from evals.care.measure_depth import DepthReport, Mode, run_cases, summarize
from evals.care.stats import Latency
from pema.agent.model_types import ChatModel, ModelCompletion, ModelRequest, ModelUsage
from pema.agent.text_generator import ProviderTextGenerator
from pema.care.budget import TurnBudget
from pema.care.depth import TextGeneratorDepthLlm
from pema.care.ports import FreeSlot
from pema.care.specialists.scope import CareTurnScope
from pema.care.specialists.spec import KNOWLEDGE_ID, SCHEDULER_ID
from pema.care.testing import make_rig, vn
from pema_contracts.knowledge import KbHit

type ModelFactory = Callable[[str], ChatModel]
"""``purpose`` (``classifier``, ``knowledge``, ``scheduler``) to the model that plays it."""

HIT = KbHit(
    source_id="kb-aftercare-1",
    source_name="Hướng dẫn sau điều trị (mẫu)",
    title="Chăm sóc da",
    content="Tránh nắng 48 giờ sau peel, bôi kem dưỡng ẩm 2 lần mỗi ngày.",
    score=0.9,
)
SLOT = FreeSlot(starts_at=vn(2026, 10, 7, 9, 0), duration_min=30)


@dataclass
class CallRecord:
    latency_ns: int
    usage: ModelUsage


class MeteredModel:
    """A ``ChatModel`` that records the latency and the usage of every call it forwards."""

    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner
        self.records: list[CallRecord] = []

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    async def complete(self, request: ModelRequest) -> ModelCompletion:
        started = time.perf_counter_ns()
        completion = await self._inner.complete(request)
        self.records.append(CallRecord(time.perf_counter_ns() - started, completion.usage))
        return completion


@dataclass(frozen=True)
class CallStats:
    calls: int
    latency: Latency
    input_tokens_mean: float | None
    output_tokens_mean: float | None
    total_tokens_mean: float | None
    unreported: int
    """Calls whose provider did not report token usage (they are left out of the token means)."""


def call_stats(records: list[CallRecord]) -> CallStats:
    reported = [r for r in records if r.usage.total_tokens is not None]

    def mean(values: list[int]) -> float | None:
        return sum(values) / len(values) if values else None

    return CallStats(
        calls=len(records),
        latency=Latency.from_ns([r.latency_ns for r in records]),
        input_tokens_mean=mean([r.usage.input_tokens or 0 for r in reported]),
        output_tokens_mean=mean([r.usage.output_tokens or 0 for r in reported]),
        total_tokens_mean=mean([r.usage.total_tokens or 0 for r in reported]),
        unreported=len(records) - len(reported),
    )


@dataclass(frozen=True)
class SpecialistRow:
    specialist: str
    delegations: int
    needs_human: int
    latency: Latency
    model: CallStats


@dataclass
class RealReport:
    model_label: str
    depth: DepthReport
    classifier: CallStats
    fallbacks: int
    specialists: list[SpecialistRow] = field(default_factory=list[SpecialistRow])


async def _delegations(
    purpose: str, specialist: str, task: str, factory: ModelFactory, runs: int
) -> SpecialistRow:
    metered = MeteredModel(factory(purpose))
    latencies: list[int] = []
    needs_human = 0
    for _ in range(runs):
        rig = make_rig(models={specialist: metered}, slots=[SLOT], hits={"sau peel": [HIT]})
        scope = CareTurnScope(
            care_agent=rig.scope.care_agent,
            patient_ref="P900",
            budget=TurnBudget(clock=rig.clock),
            turn_key=f"turn-{uuid4().hex[:8]}",
        )
        started = time.perf_counter_ns()
        result = await rig.service.delegate(scope, specialist, task, None)
        latencies.append(time.perf_counter_ns() - started)
        needs_human += 1 if result.needs_human else 0
    return SpecialistRow(
        specialist, runs, needs_human, Latency.from_ns(latencies), call_stats(metered.records)
    )


async def run_real(
    cases: list[CareCase], factory: ModelFactory, *, model_label: str, delegation_runs: int = 10
) -> RealReport:
    """Run the depth cases and the specialists on the models ``factory`` gives."""
    classifier_model = MeteredModel(factory("classifier"))
    generator = ProviderTextGenerator(resolve_model=lambda override, thread: classifier_model)
    outcomes = await run_cases(cases, Mode.REAL, TextGeneratorDepthLlm(generator))
    depth = summarize(Mode.REAL, outcomes)
    report = RealReport(
        model_label=model_label,
        depth=depth,
        classifier=call_stats(classifier_model.records),
        fallbacks=depth.by_source.get("fallback", 0),
    )
    report.specialists.append(
        await _delegations(
            "knowledge", KNOWLEDGE_ID, "Tra cứu: sau peel cần kiêng gì", factory, delegation_runs
        )
    )
    report.specialists.append(
        await _delegations(
            "scheduler", SCHEDULER_ID, "Tìm khung giờ trống tuần sau cho tái khám", factory, delegation_runs
        )
    )
    return report
