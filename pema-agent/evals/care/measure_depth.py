"""Depth classification and handoff decision against the labelled cases (steps 1 and 2 of the recipe).

New module (not a port). Every case goes through the real ``HandoffSkill`` and the real ``DepthClassifier``
(red-flag rules, D1 rules, the safety floor), with a fake clock and the default ``HandoffConfig``. What
differs
between runs is only the model behind ``DepthLlm``:

* ``oracle``: answers the LABEL of the case for D2-D4 (with the case's confidence and intent). It measures the
  matrix and the rules, NOT the model: a model that is always right. For a case labelled D5 the oracle answers
  D1 with confidence 1.0 (a model that tries to talk the system out of a red flag), so a red flag the rules
  miss shows up as a false negative instead of being rescued by the oracle.
* ``rules_only``: no model (``DepthClassifier(None)``): what the system does when the model is down.
* ``real``: a real model through ``TextGeneratorDepthLlm`` (needs the GPU box; see ``run_eval``).

The counters that matter for safety are counted here, per case: how many model calls a case needed (a D5 case
must need zero).
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from evals.care.cases import CareCase
from evals.care.stats import Confusion, Latency, ratio
from pema.care.depth import DepthClassifier, DepthResult, DepthSource
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import HandoffSkill
from pema.care.handoff_types import (
    Depth,
    DepthLlmOutput,
    HandoffAction,
    HandoffConfig,
    HandoffDecision,
    Urgency,
)
from pema.care.ports import CareAgentSnapshot, ChannelTarget, DepthLlm, PatientContext
from pema.care.testing import (
    FakeClock,
    FixedWindow,
    InMemoryCareStore,
    StaticHandoffConfig,
    StaticTexts,
    vn,
)
from pema.policy.text_normalize import fold_text, to_nfc

REF = "P900"
DEPTHS: tuple[Depth, ...] = (Depth.D1, Depth.D2, Depth.D3, Depth.D4, Depth.D5)


class Mode(StrEnum):
    ORACLE = "oracle"
    RULES_ONLY = "rules_only"
    REAL = "real"


class OracleDepthLlm:
    """The model that is always right on D2-D4 and tries to hide a red flag (see the module docstring)."""

    def __init__(self) -> None:
        self.calls = 0
        self._case: CareCase | None = None

    def prime(self, case: CareCase) -> None:
        self._case = case

    async def classify(self, masked_text: str, *, instruction: str) -> DepthLlmOutput | None:
        self.calls += 1
        case = self._case
        if case is None:
            return None
        if case.depth is Depth.D5:
            return DepthLlmOutput(depth=Depth.D1, confidence=1.0)
        return DepthLlmOutput(depth=case.depth, confidence=case.conf, intent=case.intent)


class CountingDepthLlm:
    """Wraps a ``DepthLlm`` and counts calls (the real model; the oracle counts for itself)."""

    def __init__(self, inner: DepthLlm) -> None:
        self._inner = inner
        self.calls = 0

    async def classify(self, masked_text: str, *, instruction: str) -> DepthLlmOutput | None:
        self.calls += 1
        return await self._inner.classify(masked_text, instruction=instruction)


class RecordingClassifier(DepthClassifier):
    """``DepthClassifier`` that keeps the last ``DepthResult`` (the skill does not expose it)."""

    def __init__(self, llm: DepthLlm | None) -> None:
        super().__init__(llm)
        self.last: DepthResult | None = None

    async def classify(self, event: CareEvent, texts: Sequence[str], *, instruction: str = "") -> DepthResult:
        result = await super().classify(event, texts, instruction=instruction)
        self.last = result
        return result


@dataclass(frozen=True)
class CaseOutcome:
    case: CareCase
    decision: HandoffDecision
    source: DepthSource
    llm_calls: int
    elapsed_ns: int

    @property
    def predicted(self) -> Depth:
        return self.decision.depth

    @property
    def action_ok(self) -> bool:
        return self.decision.action is self.case.action

    @property
    def depth_ok(self) -> bool:
        return self.decision.depth is self.case.depth


def _context(case: CareCase, agent: CareAgentSnapshot) -> PatientContext:
    when = vn(2026, 10, 5, case.hour)
    facts: dict[str, object] = {
        "vip": case.vip,
        "complex_history": case.complex_history,
        "past_complaint": case.past_complaint,
        "pending_doctor_work": case.pending_doctor_work,
        "repeat_count": case.repeat_count,
    }
    if case.procedure_hours_ago is not None:
        facts["last_procedure_at"] = (when - timedelta(hours=case.procedure_hours_ago)).isoformat()
    return PatientContext(
        patient_ref=REF,
        patient_id=agent.patient_id,
        facts=facts,
        channel=ChannelTarget("acct-fake", "thread-fake") if case.verified else None,
    )


async def run_case(
    case: CareCase,
    llm: DepthLlm | None,
    calls_of: OracleDepthLlm | CountingDepthLlm | None,
    *,
    config: HandoffConfig | None = None,
    texts: Sequence[str] | None = None,
) -> CaseOutcome:
    """One case through the skill. ``calls_of`` is the object that counts the model calls of ``llm``."""
    when = vn(2026, 10, 5, case.hour)
    store = InMemoryCareStore()
    agent = store.add_patient(REF)
    classifier = RecordingClassifier(llm)
    skill = HandoffSkill(
        classifier=classifier,
        config_source=StaticHandoffConfig(config),
        texts=StaticTexts(*(case.texts if texts is None else texts)),
        clock=FakeClock(when),
        window=FixedWindow(),
    )
    event = CareEvent(
        kind=EventKind.PATIENT_MESSAGE, initiator=Initiator.PATIENT, patient_ref=REF, occurred_at=when
    )
    before = calls_of.calls if calls_of is not None else 0
    started = time.perf_counter_ns()
    decision = await skill.evaluate(agent, event, _context(case, agent))
    elapsed = time.perf_counter_ns() - started
    after = calls_of.calls if calls_of is not None else 0
    assert classifier.last is not None  # noqa: S101  - the skill always classifies a patient message
    return CaseOutcome(case, decision, classifier.last.source, after - before, elapsed)


async def run_cases(
    cases: Sequence[CareCase], mode: Mode, real_llm: DepthLlm | None = None
) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []
    if mode is Mode.ORACLE:
        oracle = OracleDepthLlm()
        for case in cases:
            oracle.prime(case)
            outcomes.append(await run_case(case, oracle, oracle))
    elif mode is Mode.RULES_ONLY:
        outcomes.extend([await run_case(case, None, None) for case in cases])
    else:
        if real_llm is None:
            raise ValueError("the real mode needs a DepthLlm")
        counting = CountingDepthLlm(real_llm)
        for case in cases:
            outcomes.append(await run_case(case, counting, counting))
    return outcomes


# ------------------------------------------------------------------------------------------ the numbers
@dataclass(frozen=True)
class ClassStats:
    depth: Depth
    labelled: int
    predicted: int
    correct: int

    @property
    def recall(self) -> float | None:
        return ratio(self.correct, self.labelled)

    @property
    def precision(self) -> float | None:
        return ratio(self.correct, self.predicted)


@dataclass(frozen=True)
class Miss:
    case_id: str
    label: Depth
    predicted: Depth
    reason: str
    source: str


@dataclass
class DepthReport:
    mode: Mode
    cases: int
    accuracy: float | None
    classes: list[ClassStats]
    confusion: dict[tuple[Depth, Depth], int]
    d5_labelled: int
    d5_found: int
    d5_llm_calls: int
    d5_false_positives: list[Miss]
    d1_labelled: int
    d1_by_rules: int
    d1_false_by_rules: list[Miss]
    llm_calls_total: int
    cases_without_model: int
    by_source: dict[str, int]
    accuracy_with_diacritics: float | None
    accuracy_without_diacritics: float | None
    n_with_diacritics: int
    n_without_diacritics: int
    handoff: Confusion
    false_negatives: list[Miss]
    false_positives: list[Miss]
    skill_correct: int
    skill_total: int
    skill_misses: list[tuple[str, str, str]]
    critical_ok: bool
    urgent_ok: bool
    latency: Latency
    depth_misses: list[Miss] = field(default_factory=list[Miss])

    @property
    def d5_recall(self) -> float | None:
        return ratio(self.d5_found, self.d5_labelled)


def _miss(outcome: CaseOutcome) -> Miss:
    return Miss(
        outcome.case.id,
        outcome.case.depth,
        outcome.predicted,
        outcome.decision.reason,
        outcome.source.value,
    )


def summarize(mode: Mode, outcomes: Sequence[CaseOutcome]) -> DepthReport:
    confusion: Counter[tuple[Depth, Depth]] = Counter()
    for outcome in outcomes:
        confusion[(outcome.case.depth, outcome.predicted)] += 1
    classes = [
        ClassStats(
            depth,
            labelled=sum(1 for o in outcomes if o.case.depth is depth),
            predicted=sum(1 for o in outcomes if o.predicted is depth),
            correct=confusion[(depth, depth)],
        )
        for depth in DEPTHS
    ]
    d5 = [o for o in outcomes if o.case.depth is Depth.D5]
    d1 = [o for o in outcomes if o.case.depth is Depth.D1]
    handoff = Confusion()
    for outcome in outcomes:
        handoff = handoff.add(
            expected=outcome.case.action is HandoffAction.HANDOFF,
            actual=outcome.decision.action is HandoffAction.HANDOFF,
        )
    with_marks = [o for o in outcomes if o.case.has_diacritics]
    without = [o for o in outcomes if not o.case.has_diacritics]
    skill_pairs = [(o.case.id, o.case.skill, o.decision.required_skill) for o in outcomes]
    return DepthReport(
        mode=mode,
        cases=len(outcomes),
        accuracy=ratio(sum(1 for o in outcomes if o.depth_ok), len(outcomes)),
        classes=classes,
        confusion=dict(confusion),
        d5_labelled=len(d5),
        d5_found=sum(1 for o in d5 if o.predicted is Depth.D5),
        d5_llm_calls=sum(o.llm_calls for o in d5),
        d5_false_positives=[
            _miss(o) for o in outcomes if o.predicted is Depth.D5 and o.case.depth is not Depth.D5
        ],
        d1_labelled=len(d1),
        d1_by_rules=sum(1 for o in d1 if o.source is DepthSource.RULES),
        d1_false_by_rules=[
            _miss(o) for o in outcomes if o.source is DepthSource.RULES and o.case.depth is not Depth.D1
        ],
        llm_calls_total=sum(o.llm_calls for o in outcomes),
        cases_without_model=sum(1 for o in outcomes if o.llm_calls == 0),
        by_source=dict(Counter(o.source.value for o in outcomes)),
        accuracy_with_diacritics=ratio(sum(1 for o in with_marks if o.depth_ok), len(with_marks)),
        accuracy_without_diacritics=ratio(sum(1 for o in without if o.depth_ok), len(without)),
        n_with_diacritics=len(with_marks),
        n_without_diacritics=len(without),
        handoff=handoff,
        false_negatives=[
            _miss(o)
            for o in outcomes
            if o.case.action is HandoffAction.HANDOFF and o.decision.action is HandoffAction.ANSWER
        ],
        false_positives=[
            _miss(o)
            for o in outcomes
            if o.case.action is HandoffAction.ANSWER and o.decision.action is HandoffAction.HANDOFF
        ],
        skill_correct=sum(1 for _, expected, actual in skill_pairs if expected == actual),
        skill_total=len(skill_pairs),
        skill_misses=[pair for pair in skill_pairs if pair[1] != pair[2]],
        critical_ok=all(o.decision.urgency is Urgency.CRITICAL for o in outcomes if o.predicted is Depth.D5),
        urgent_ok=all(
            o.decision.urgency is not Urgency.NORMAL
            for o in outcomes
            if o.predicted is Depth.D4 and o.decision.action is HandoffAction.HANDOFF
        ),
        latency=Latency.from_ns([o.elapsed_ns for o in outcomes]),
        depth_misses=[_miss(o) for o in outcomes if not o.depth_ok],
    )


# ------------------------------------------------------------------------------ diacritics robustness
@dataclass(frozen=True)
class FoldDifference:
    case_id: str
    original: str
    folded: str


async def fold_variant_differences(cases: Sequence[CareCase]) -> tuple[int, list[FoldDifference]]:
    """Run the oracle twice on every case that has diacritics: as written and with them stripped. Returns how
    many cases were compared and the ones where the ACTION or the DEPTH changed. The model is the oracle (it
    does not read the text), so a difference comes from the rules, which is what is being tested."""
    oracle = OracleDepthLlm()
    compared = 0
    differences: list[FoldDifference] = []
    for case in cases:
        if not case.has_diacritics:
            continue
        compared += 1
        oracle.prime(case)
        original = await run_case(case, oracle, oracle)
        folded_texts = [fold_text(to_nfc(text)) for text in case.texts]
        folded = await run_case(case, oracle, oracle, texts=folded_texts)
        if (original.decision.action, original.decision.depth) != (
            folded.decision.action,
            folded.decision.depth,
        ):
            differences.append(
                FoldDifference(
                    case.id,
                    f"{original.decision.action.value}/{original.decision.depth.value}",
                    f"{folded.decision.action.value}/{folded.decision.depth.value}",
                )
            )
    return compared, differences


# --------------------------------------------------------------------------- red-flag perturbations
PERTURBATIONS: tuple[tuple[str, str], ...] = (
    ("UPPER CASE", "upper"),
    ("polite chatter around it", "chatter"),
    ("buried in a long message", "buried"),
    ("emoji and repeated particles", "emoji"),
    ("doubled spaces", "spaces"),
)


def _perturb(text: str, kind: str) -> str:
    if kind == "upper":
        return text.upper()
    if kind == "chatter":
        return f"Chào bác sĩ ạ, em xin phép hỏi. {text}. Em cảm ơn nhiều ạ."
    if kind == "buried":
        return (
            "Hôm qua em đi làm về muộn, trời mưa, em ăn cơm xong rồi nằm nghỉ một lúc, sau đó "
            f"{text} nên em nhắn bên mình, mong phòng khám xem giúp em"
        )
    if kind == "emoji":
        return f"{text} ạ ạ ạ 😢😢"
    if kind == "spaces":
        return text.replace(" ", "  ")
    raise ValueError(kind)


@dataclass(frozen=True)
class PerturbationResult:
    checked: int
    missed: list[tuple[str, str]]
    """``(case id, perturbation)`` of a red-flag case that stopped being D5."""
    llm_calls: int


async def redflag_perturbations(cases: Sequence[CareCase]) -> PerturbationResult:
    """Every red-flag case again with five rewrites of its text. The oracle is the adversarial one (says D1),
    so a missed flag is a miss, and every call to it is counted: there must be none."""
    oracle = OracleDepthLlm()
    checked = 0
    missed: list[tuple[str, str]] = []
    for case in cases:
        if case.depth is not Depth.D5:
            continue
        oracle.prime(case)
        for label, kind in PERTURBATIONS:
            checked += 1
            outcome = await run_case(
                case, oracle, oracle, texts=[_perturb(text, kind) for text in case.texts]
            )
            if outcome.predicted is not Depth.D5:
                missed.append((case.id, label))
    return PerturbationResult(checked, missed, oracle.calls)
