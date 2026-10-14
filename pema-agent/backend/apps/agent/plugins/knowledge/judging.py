"""Judging what a search found before the agent reads it, with the service ``judge`` (plugin ``jev``).

Each of the best chunks is put to the judge with the question, as one yes/no question under the clinic's
policy: would this passage be ranked top for the customer's question (it states the specific fact asked for)?
The answer is a probability. The code decides: the chunks are ordered by it; when even the best is under
the floor of the level chosen on the settings page nothing is handed to the agent (it says it has no
information); otherwise the chunks far below the best are dropped. The policy is in the ``criteria`` below;
the search itself already left out documents not in force on the day asked.

Measured on the Pema demo corpus (``docs/PLAN-jev-plugin.md`` §7): this way of using the answers (order,
refuse only when all are low) beat cutting each chunk at a threshold, which lost right documents. A
question about "steering the assistant" was left out: the clinic's own documents say things like "the
assistant never decides a refund", which it flagged, and the documents are written by the clinic.

The judge never makes a search fail: off, missing, without a key, out of allowance, slow or failing, the
chunks go to the agent as the search ranked them and the reason is noted.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal

from agent_app.plugins import JudgeService, JudgeUnavailableError

from .models import Hit

JUDGED: Final = 10
"""Chunks put to the judge (one request each); the others are not given to the agent when it judged."""
PASSAGE_CHARS: Final = 6000
LEVELS: Final = {"strict": 0.30, "medium": 0.10, "loose": 0.05}
"""The least the best chunk must score for anything to be handed over: strict refuses more, loose refuses
only when nothing has any evidence."""
DEFAULT_LEVEL: Final = "medium"
KEEP_SHARE: Final = 0.20
"""A chunk scoring under this share of the best one is left out."""
RANK: Final = "ranks_top"
QUESTIONS: Final[dict[str, dict[str, Any]]] = {
    RANK: {
        "type": "noul",
        "instructions": (
            "Should this passage be ranked top for the customer's question under the clinic's policy?"
        ),
        "criteria": {
            "true": (
                "It states the specific fact the question asks for (a price, a duration, a condition, "
                "a step) for the service the question is about, as an official clinic document would"
            ),
            "false": (
                "It only shares words or the topic, or it is about a different service, or it is general "
                "background that does not state the fact asked, or it answers a different question"
            ),
        },
    }
}

Reason = Literal["kept", "weak", "no_evidence"]
NOT_ON: Final = "Plugin Jev chưa bật: lượt này dùng kết quả chưa lọc."


@dataclass(frozen=True, slots=True)
class JudgePlan:
    """What a search needs to judge: the service (None while plugin ``jev`` is off), the level, the wait."""

    service: JudgeService | None
    level: str
    timeout_s: float
    questions: Mapping[str, Mapping[str, Any]] = field(default_factory=lambda: QUESTIONS)
    """What the judge is asked; the bench tries other wordings."""


@dataclass(frozen=True, slots=True)
class Verdict:
    hit: Hit
    ranks: float
    reason: Reason

    @property
    def kept(self) -> bool:
        return self.reason == "kept"


@dataclass(frozen=True, slots=True)
class JudgeOutcome:
    kept: tuple[Hit, ...]
    """The chunks to give the agent, the likeliest first; every chunk, as the search ranked them, when it did
    not judge."""
    verdicts: tuple[Verdict, ...] = ()
    ms: float = 0.0
    note: str | None = None
    """Why it did not judge (a sentence for a person); None when it did."""

    @property
    def judged(self) -> bool:
        return self.note is None


def reasons(ranks: Sequence[float], level: str) -> list[Reason]:
    """What becomes of each chunk: nothing at all when even the best is under the level's floor, else the
    ones far below the best are ``weak``."""
    best = max(ranks, default=0.0)
    if best < LEVELS.get(level, LEVELS[DEFAULT_LEVEL]):
        return ["no_evidence" for _ in ranks]
    return ["kept" if rank >= KEEP_SHARE * best else "weak" for rank in ranks]


def state_of(question: str, variants: Sequence[str], hit: Hit) -> str:
    """What the judge reads: the question (and the other ways it was asked), then the chunk with its place."""
    asked = f"Customer question: {question}"
    others = f"\nOther ways the customer may have asked it: {'; '.join(variants)}" if variants else ""
    where = f"document: {hit.source_title}; section: {hit.chunk.path}"
    return f"{asked}{others}\n\nPassage ({where}):\n{hit.chunk.body[:PASSAGE_CHARS]}"


async def judge_hits(
    plan: JudgePlan,
    question: str,
    variants: Sequence[str],
    hits: Sequence[Hit],
    *,
    timer: Callable[[], float] = time.perf_counter,
) -> JudgeOutcome:
    """Never raises."""
    if not hits:
        return JudgeOutcome(kept=())
    started = timer()

    def passed(note: str) -> JudgeOutcome:
        return JudgeOutcome(kept=tuple(hits), ms=(timer() - started) * 1000, note=note)

    if plan.service is None:
        return passed(NOT_ON)
    try:
        answers = await plan.service.ask(
            [state_of(question, variants, hit) for hit in hits], plan.questions, timeout_s=plan.timeout_s
        )
        ranks = [float(answer[RANK]["noul"]) for answer in answers]
    except JudgeUnavailableError as err:
        return passed(f"Bộ chấm Jev không dùng được: {err.message} Lượt này dùng kết quả chưa lọc.")
    except (KeyError, TypeError, ValueError):
        return passed("Bộ chấm Jev trả về dữ liệu lạ: lượt này dùng kết quả chưa lọc.")
    if len(ranks) != len(hits):
        return passed("Bộ chấm Jev trả về thiếu kết quả: lượt này dùng kết quả chưa lọc.")
    verdicts = tuple(
        Verdict(hit, rank, reason)
        for hit, rank, reason in zip(hits, ranks, reasons(ranks, plan.level), strict=True)
    )
    kept = sorted((v for v in verdicts if v.kept), key=lambda v: v.ranks, reverse=True)
    return JudgeOutcome(
        kept=tuple(replace(v.hit, score=v.ranks) for v in kept),
        verdicts=verdicts,
        ms=(timer() - started) * 1000,
    )
