"""Looking something up in the store, the way the agent's ``kb_search`` and the page "Thử tìm" do.

Stages: understand the question (folded words, the services it names), keyword candidates and, when the
embedding service is connected, vector candidates found at the same time (the vector list leads, the keyword
list follows), a small boost for chunks labelled with a named service, at most a few chunks per document, then
a character budget. A question may come with up to two variants (the agent writes them in the same call):
each is searched the same way and the lists are merged by rank (``fusion.rank_fusion``). When the
judge is on (``judging.py``), the best chunks are judged before the budget and only those with evidence go on.
The vector branch never makes a search fail or wait long: when it is off, failing or slow the result is
exactly the keyword result. Every channel sees the same store (no patient/staff split for now).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Final

from .embedding import EmbeddingError
from .fusion import rank_fusion, vector_first
from .ingest import recognise
from .judging import JUDGED, JudgeOutcome, JudgePlan, judge_hits
from .models import Hit, Service
from .store import KnowledgeStore
from .text import fold, query_terms

logger = logging.getLogger(__name__)

CANDIDATES: Final = 40
SERVICE_BOOST: Final = 1.25
PER_DOCUMENT: Final = 3
MAX_QUERIES: Final = 3
"""The question and at most two variants."""
EXCERPT_CHARS: Final = 280
NO_VECTOR: Final = "Embedding chưa bật: chỉ tìm bằng từ khóa."
VECTOR_FAILED: Final = "Lỗi khi tìm theo nghĩa: lượt này chỉ tìm bằng từ khóa."


@dataclass(frozen=True, slots=True)
class VectorPlan:
    """What the vector branch needs: the least similarity, how long to wait, and how to embed a question
    (``Embedder.query_vector``: the vector and the space it belongs to)."""

    min_similarity: float
    timeout_s: float
    embed: Callable[[str, float], Awaitable[tuple[list[float], str]]]


@dataclass(frozen=True, slots=True)
class SearchResult:
    question: str
    folded: str
    terms: tuple[str, ...]
    services: tuple[str, ...]
    as_of: date
    candidates: tuple[Hit, ...]
    """The keyword list."""
    vector: tuple[Hit, ...]
    """The vector list; empty when that branch was not used or found nothing."""
    fused: tuple[Hit, ...]
    """After merging; the keyword list as it is when nothing was merged."""
    final: tuple[Hit, ...]
    keyword_ms: float
    vector_ms: float
    vector_note: str | None
    """Why the vector branch was skipped or failed (a sentence for a person); None when it ran."""
    vector_skip: str | None
    """The same as a short code for the trace: ``off``, ``timeout`` or ``error``; None when it ran."""
    fusion: bool
    total_ms: float
    variants: tuple[str, ...] = ()
    """The other ways of asking that were searched with the question."""
    judge: JudgeOutcome | None = None
    """What the judge did; None when it is off."""

    @property
    def vector_used(self) -> bool:
        return self.vector_note is None


@dataclass(frozen=True, slots=True)
class _VectorOutcome:
    hits: tuple[Hit, ...] = ()
    ms: float = 0.0
    note: str | None = None
    skip: str | None = None


@dataclass(frozen=True, slots=True)
class _Branch:
    """What one way of asking found."""

    keyword: tuple[Hit, ...]
    keyword_ms: float
    vector: _VectorOutcome

    @property
    def fused(self) -> bool:
        return self.vector.note is None and bool(self.vector.hits)

    def ranked(self) -> list[Hit]:
        return vector_first(self.vector.hits, self.keyword) if self.fused else list(self.keyword)


class Searcher:
    def __init__(self, store: KnowledgeStore, *, timer: Callable[[], float] = time.perf_counter) -> None:
        self._store = store
        self._timer = timer

    async def search(
        self,
        question: str,
        as_of: date,
        *,
        results: int,
        char_budget: int,
        services: Sequence[Service],
        vector: VectorPlan | None = None,
        variants: Sequence[str] = (),
        judge: JudgePlan | None = None,
    ) -> SearchResult:
        started = self._timer()
        asked = _distinct(question, variants)
        named = tuple(dict.fromkeys(code for text in asked for code in recognise(text, services)))
        wanted = tuple(query_terms(question))
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._branch(text, as_of, vector)) for text in asked]
        branches = [task.result() for task in tasks]
        candidates = _union(hit for branch in branches for hit in branch.keyword)
        found = _union(hit for branch in branches for hit in branch.vector.hits)
        outcome = next((b.vector for b in branches if b.vector.note is None), branches[0].vector)
        fusion = any(branch.fused for branch in branches)
        ranked = branches[0].ranked() if len(branches) == 1 else rank_fusion([b.ranked() for b in branches])
        boosted = sorted((_boosted(hit, named) for hit in ranked), key=lambda hit: hit.score, reverse=True)
        spread = _spread(boosted)
        judged = None if judge is None else await judge_hits(judge, question, asked[1:], spread[:JUDGED])
        final = _packed(judged.kept if judged is not None and judged.judged else spread, results, char_budget)
        return SearchResult(
            question=question,
            folded=fold(question).strip(),
            terms=wanted,
            services=named,
            as_of=as_of,
            candidates=candidates,
            vector=found,
            fused=tuple(ranked),
            final=tuple(final),
            keyword_ms=max(branch.keyword_ms for branch in branches),
            vector_ms=max(branch.vector.ms for branch in branches),
            vector_note=outcome.note,
            vector_skip=outcome.skip,
            fusion=fusion,
            total_ms=(self._timer() - started) * 1000,
            variants=tuple(asked[1:]),
            judge=judged,
        )

    async def _branch(self, text: str, as_of: date, plan: VectorPlan | None) -> _Branch:
        async with asyncio.TaskGroup() as group:
            keyword_task = group.create_task(self._keyword(tuple(query_terms(text)), as_of))
            vector_task = group.create_task(self._vector(text, as_of, plan))
        keyword, keyword_ms = keyword_task.result()
        return _Branch(tuple(keyword), keyword_ms, vector_task.result())

    async def _keyword(self, wanted: Sequence[str], as_of: date) -> tuple[list[Hit], float]:
        started = self._timer()
        found = await self._store.search(wanted, as_of, CANDIDATES)
        return found, (self._timer() - started) * 1000

    async def _vector(self, question: str, as_of: date, plan: VectorPlan | None) -> _VectorOutcome:
        """The vector candidates, or why there are none. Never raises: the keyword search must go on."""
        if plan is None:
            return _VectorOutcome(note=NO_VECTOR, skip="off")
        started = self._timer()

        def spent() -> float:
            return (self._timer() - started) * 1000

        try:
            vector, space = await asyncio.wait_for(plan.embed(question, plan.timeout_s), plan.timeout_s)
            hits = await self._store.vector_search(space, vector, as_of, CANDIDATES, plan.min_similarity)
        except EmbeddingError as err:
            return _VectorOutcome(
                ms=spent(), note=err.message, skip="timeout" if err.kind == "timeout" else "error"
            )
        except TimeoutError:
            note = f"Nhúng câu hỏi quá {plan.timeout_s:g} giây: lượt này chỉ tìm bằng từ khóa."
            return _VectorOutcome(ms=spent(), note=note, skip="timeout")
        except Exception:
            logger.warning("vector search failed", exc_info=True)
            return _VectorOutcome(ms=spent(), note=VECTOR_FAILED, skip="error")
        return _VectorOutcome(hits=tuple(hits), ms=spent())


def _distinct(question: str, variants: Sequence[str]) -> list[str]:
    """The question first, then its variants, each once (same words, whatever the case or accents)."""
    seen: dict[str, str] = {}
    for text in (question, *variants):
        seen.setdefault(" ".join(fold(text).split()), text.strip())
    return [text for key, text in seen.items() if key][:MAX_QUERIES]


def _union(hits: Iterable[Hit]) -> tuple[Hit, ...]:
    """The hits without a chunk twice, in the order first seen."""
    return tuple({hit.chunk.id: hit for hit in reversed(tuple(hits))}.values())[::-1]


def _boosted(hit: Hit, named: Sequence[str]) -> Hit:
    if named and set(named) & set(hit.chunk.services):
        return replace(hit, score=hit.score * SERVICE_BOOST)
    return hit


def _spread(hits: Sequence[Hit]) -> list[Hit]:
    """At most ``PER_DOCUMENT`` chunks of one document, so one long document does not fill the answer."""
    seen: dict[str, int] = {}
    kept: list[Hit] = []
    for hit in hits:
        count = seen.get(hit.chunk.source_id, 0)
        if count < PER_DOCUMENT:
            kept.append(hit)
            seen[hit.chunk.source_id] = count + 1
    return kept


def _packed(hits: Sequence[Hit], results: int, char_budget: int) -> list[Hit]:
    kept: list[Hit] = []
    used = 0
    for hit in hits[:results]:
        size = len(hit.chunk.body)
        if kept and used + size > char_budget:
            break
        kept.append(hit)
        used += size
    return kept


def tool_text(result: SearchResult) -> str:
    """What the agent reads: each chunk with the document's code, its headings and its text."""
    if not result.final and result.judge is not None and result.judge.verdicts:
        return (
            "Có đoạn tài liệu gần chủ đề nhưng không đoạn nào đủ căn cứ để trả lời câu hỏi này. Đừng đoán: "
            "thử tìm lại với từ khóa khác, hoặc nói với khách là chưa có thông tin và đề nghị chuyển "
            "nhân viên."
        )
    if not result.final:
        return (
            "Không có đoạn tài liệu nào khớp câu hỏi này trong kho tri thức. Đừng đoán: thử tìm lại với từ "
            "khóa "
            "khác (tên dịch vụ, chính sách) hoặc nói với khách là chưa có thông tin và đề nghị chuyển nhân "
            "viên."
        )
    asked = result.as_of.strftime("%d/%m/%Y")
    blocks = [
        f"[{index}] {hit.doc_code or hit.chunk.source_id} · {hit.source_title} · {hit.chunk.path}\n"
        f"{hit.chunk.body}"
        for index, hit in enumerate(result.final, start=1)
    ]
    return f"Tìm thấy {len(result.final)} đoạn (áp dụng ngày {asked}):\n\n" + "\n\n---\n\n".join(blocks)


def tool_detail(result: SearchResult) -> dict[str, Any]:
    """For the trace: how many candidates each branch gave, the best score and which documents the answer
    may use. Short codes only: no sentences, no text of the question."""
    return {
        "terms": len(result.terms),
        "services": list(result.services),
        "candidates": len(result.candidates),
        "queries": 1 + len(result.variants),
        "keyword_candidates": len(result.candidates),
        "vector_candidates": len(result.vector),
        "vector_used": result.vector_used,
        "vector_ms": round(result.vector_ms),
        "vector_skip": result.vector_skip,
        "top_similarity": round(result.vector[0].score, 4) if result.vector else 0,
        "returned": len(result.final),
        "top_score": round(result.final[0].score, 4) if result.final else 0,
        "doc_ids": list(dict.fromkeys(hit.doc_code or hit.chunk.source_id for hit in result.final)),
        "as_of": result.as_of.isoformat(),
        **_judge_detail(result.judge),
    }


def _judge_detail(outcome: JudgeOutcome | None) -> dict[str, Any]:
    if outcome is None:
        return {}
    return {
        "judged": outcome.judged,
        "judge_dropped": sum(not v.kept for v in outcome.verdicts),
        "judge_ms": round(outcome.ms),
    }


def debug_view(result: SearchResult, min_similarity: float) -> dict[str, Any]:
    """The stages for the page "Thử tìm" (``SearchDebug`` of types.ts)."""
    understand = (
        f"Từ khóa: {', '.join(result.terms[:15]) or '(không có)'}"
        + (f". Dịch vụ: {', '.join(result.services)}" if result.services else "")
        + (f". Cách hỏi khác: {' | '.join(result.variants)}" if result.variants else "")
    )
    return {
        "question": result.question,
        "folded": result.folded,
        "services": list(result.services),
        "total_ms": round(result.total_ms, 1),
        "stages": [
            _stage("understand", "Hiểu câu hỏi", 0.0, understand, []),
            _stage(
                "keyword",
                "Ứng viên từ khóa",
                result.keyword_ms,
                f"{len(result.candidates)} đoạn khớp, chỉ tính nguồn đang dùng vào ngày "
                f"{result.as_of.isoformat()}",
                result.candidates[:20],
            ),
            _stage(
                "vector",
                "Ứng viên vector",
                result.vector_ms,
                result.vector_note or f"{len(result.vector)} đoạn gần nghĩa, độ giống ≥ {min_similarity:g}",
                result.vector[:20],
                skipped=not result.vector_used,
            ),
            _stage(
                "fused",
                "Xếp hạng: vector trước, từ khóa sau",
                0.0,
                "Các đoạn gần nghĩa đứng trước, các đoạn chỉ khớp từ khóa nối sau."
                if result.fusion
                else "Không xếp lại: lượt này chỉ có kết quả từ khóa.",
                result.fused[:20] if result.fusion else [],
                skipped=not result.fusion,
            ),
            *_judge_stages(result.judge),
            _stage(
                "final",
                "Gói cuối đúng như agent thấy",
                0.0,
                f"{len(result.final)} đoạn, tối đa {PER_DOCUMENT} đoạn mỗi tài liệu"
                if result.final
                else "Không có đoạn nào: agent sẽ nói chưa có thông tin.",
                result.final,
            ),
        ],
    }


JUDGE_REASON: Final = {
    "weak": "kém hơn hẳn đoạn tốt nhất",
    "no_evidence": "không đoạn nào đủ căn cứ",
}


def _judge_stages(outcome: JudgeOutcome | None) -> list[dict[str, Any]]:
    """Two stages for "Thử tìm": the chunks the judge kept (scored by how likely they state the fact asked)
    and the ones it dropped, with why."""
    if outcome is None:
        return []
    if not outcome.judged:
        return [_stage("judge", "Bộ chấm Jev", outcome.ms, outcome.note or "", [], skipped=True)]
    dropped = [v for v in outcome.verdicts if not v.kept]
    why = ", ".join(
        f"{sum(v.reason == reason for v in dropped)} {label}"
        for reason, label in JUDGE_REASON.items()
        if any(v.reason == reason for v in dropped)
    )
    note = (
        f"Giữ {len(outcome.kept)}/{len(outcome.verdicts)} đoạn, xếp theo khả năng nêu đúng điều khách hỏi"
        + (f"; bỏ {why}" if why else "")
    )
    return [
        _stage("judge", "Bộ chấm Jev: giữ", outcome.ms, note, outcome.kept),
        _stage(
            "judge_dropped",
            "Bộ chấm Jev: bỏ",
            0.0,
            f"{len(dropped)} đoạn không đưa cho agent" if dropped else "Không bỏ đoạn nào.",
            [replace(v.hit, score=v.ranks) for v in dropped],
            skipped=not dropped,
        ),
    ]


def _stage(
    stage_id: str, title: str, ms: float, note: str, hits: Sequence[Hit], *, skipped: bool = False
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "title": title,
        "ms": round(ms, 1),
        "note": note,
        "skipped": skipped,
        "candidates": [
            {
                "chunk_id": hit.chunk.id,
                "doc_code": hit.doc_code,
                "source_title": hit.source_title,
                "path": hit.chunk.path,
                "excerpt": hit.chunk.body[:EXCERPT_CHARS],
                "score": round(hit.score, 4),
            }
            for hit in hits
        ],
    }
