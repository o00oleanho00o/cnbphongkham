"""Looking something up in the store, the way the agent's ``kb_search`` and the page "Thử tìm" do.

Stages: understand the question (folded words, the services it names), keyword candidates, a small boost for
chunks labelled with a named service, at most a few chunks per document, then a character budget. The vector
branch is not there yet and says so. Every channel sees the same store (no patient/staff split for now).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Final

from .ingest import recognise
from .models import Hit, Service
from .store import KnowledgeStore
from .text import fold, query_terms

CANDIDATES: Final = 40
SERVICE_BOOST: Final = 1.25
PER_DOCUMENT: Final = 3
EXCERPT_CHARS: Final = 280
NO_VECTOR: Final = "Embedding chưa bật: bỏ qua nhánh vector, chỉ tìm bằng từ khóa."


@dataclass(frozen=True, slots=True)
class SearchResult:
    question: str
    folded: str
    terms: tuple[str, ...]
    services: tuple[str, ...]
    as_of: date
    candidates: tuple[Hit, ...]
    final: tuple[Hit, ...]
    keyword_ms: float
    total_ms: float


class Searcher:
    def __init__(self, store: KnowledgeStore, *, timer: Callable[[], float] = time.perf_counter) -> None:
        self._store = store
        self._timer = timer

    async def search(
        self, question: str, as_of: date, *, results: int, char_budget: int, services: Sequence[Service]
    ) -> SearchResult:
        started = self._timer()
        named = tuple(recognise(question, services))
        wanted = tuple(query_terms(question))
        keyword_started = self._timer()
        candidates = await self._store.search(wanted, as_of, CANDIDATES)
        keyword_ms = (self._timer() - keyword_started) * 1000
        boosted = sorted(
            (_boosted(hit, named) for hit in candidates), key=lambda hit: hit.score, reverse=True
        )
        final = _packed(_spread(boosted), results, char_budget)
        return SearchResult(
            question=question,
            folded=fold(question).strip(),
            terms=wanted,
            services=named,
            as_of=as_of,
            candidates=tuple(candidates),
            final=tuple(final),
            keyword_ms=keyword_ms,
            total_ms=(self._timer() - started) * 1000,
        )


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
    """For the trace: how many candidates, the best score and which documents the answer may use."""
    return {
        "terms": len(result.terms),
        "services": list(result.services),
        "candidates": len(result.candidates),
        "returned": len(result.final),
        "top_score": round(result.final[0].score, 4) if result.final else 0,
        "doc_ids": list(dict.fromkeys(hit.doc_code or hit.chunk.source_id for hit in result.final)),
        "as_of": result.as_of.isoformat(),
    }


def debug_view(result: SearchResult) -> dict[str, Any]:
    """The stages for the page "Thử tìm" (``SearchDebug`` of types.ts)."""
    understand = f"Từ khóa: {', '.join(result.terms[:15]) or '(không có)'}" + (
        f". Dịch vụ: {', '.join(result.services)}" if result.services else ""
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
            _stage("vector", "Ứng viên vector", 0.0, NO_VECTOR, [], skipped=True),
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
