"""Where the knowledge store keeps its sources, chunks, services, events and gaps: Postgres (the plugin's
own ``kb_`` tables, scoped by tenant and agent) or process memory (tests, an agent run without a database).

The keyword search is the same idea in both: the folded words of a question and of a chunk (``text.terms``),
any of them may match, a rarer and repeated word counts more. Postgres ranks with ``ts_rank_cd`` on a GIN
index, memory with BM25. Only sources in use count: ready, ``active``, and in force on the day asked.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Final, Protocol

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Text

from .models import Chunk, Event, Gap, GapState, Hit, Service, Source, SourceFilter, as_mapping
from .text import fold, terms

HEADING_WEIGHT: Final = 2
"""The words of a chunk's headings count this many times: they say what the chunk is about."""


def chunk_terms(item: Chunk) -> list[str]:
    return terms("\n".join([*[item.path] * HEADING_WEIGHT, item.body]))


BM25_K1: Final = 1.2
BM25_B: Final = 0.75


class KnowledgeStore(Protocol):
    async def add_source(self, source: Source, chunks: Sequence[Chunk]) -> None: ...
    async def get(self, source_id: str) -> Source | None: ...
    async def save(self, source: Source) -> None: ...
    async def replace_chunks(self, source_id: str, chunks: Sequence[Chunk]) -> None: ...
    async def delete(self, source_id: str) -> bool: ...
    async def find(self, query: SourceFilter) -> tuple[list[Source], int]: ...
    async def all_sources(self) -> list[Source]: ...
    async def by_code(self, doc_code: str) -> Source | None: ...
    async def in_force(self, key: str, as_of: date) -> Source | None: ...
    async def by_hash(self, content_hash: str) -> Source | None: ...
    async def chunks(
        self, source_id: str, q: str, page: int, page_size: int, space: str | None
    ) -> tuple[list[Chunk], int]:
        """A source's chunks; each says whether it has a vector in ``space`` (never when that is None)."""
        ...

    async def update_chunk(self, chunk_id: str, services: list[str] | None, kind: str | None) -> bool: ...
    async def search(self, query: Sequence[str], as_of: date, limit: int) -> list[Hit]: ...
    async def vector_search(
        self, space: str, vector: Sequence[float], as_of: date, limit: int, min_similarity: float
    ) -> list[Hit]:
        """Chunks closest to ``vector`` in force on ``as_of`` (same sources as ``search``), best first; the
        score is the cosine similarity and none below ``min_similarity`` is returned."""
        ...

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        """(hash, text) of distinct chunk texts of ready, active sources with no vector in ``space``."""
        ...

    async def missing_count(self, space: str) -> int:
        """Chunks (not distinct texts) of ready, active sources with no vector in ``space``."""
        ...

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None: ...
    async def vector_counts(self, space: str) -> dict[str, int]:
        """Source id -> how many of its chunks have a vector in ``space``."""
        ...

    async def clear_vectors(self, space: str) -> int:
        """Deletes every vector in ``space``; returns how many."""
        ...

    async def drop_stale_vectors(self, space: str) -> int:
        """Deletes the vectors of other spaces and those no chunk refers to any more; returns how many."""
        ...

    async def add_event(self, event: Event) -> None: ...
    async def events(self, source_id: str) -> list[Event]: ...
    async def services(self) -> list[Service]: ...
    async def save_service(self, service: Service) -> None: ...
    async def delete_service(self, service_id: str) -> bool: ...
    async def service_chunks(self) -> dict[str, int]: ...
    async def record_gap(self, gap: Gap) -> None: ...
    async def gaps(self, state: GapState) -> list[Gap]: ...
    async def set_gap(self, gap_id: str, state: GapState) -> Gap | None: ...


def in_use(source: Source, as_of: date) -> bool:
    """Ready, the version in use, and in force on that day."""
    return (
        source.processing == "ready"
        and source.lifecycle == "active"
        and (source.effective_from is None or source.effective_from <= as_of)
        and (source.effective_to is None or source.effective_to >= as_of)
    )


def embeddable(source: Source) -> bool:
    """Worth a vector: ready and the version in use (one that starts later is; a draft or old one is not)."""
    return source.processing == "ready" and source.lifecycle == "active"


def matches(source: Source, query: SourceFilter) -> bool:
    needle = fold(query.q.strip())
    return (
        (not needle or needle in fold(f"{source.title} {source.doc_code or ''}"))
        and (query.processing is None or source.processing == query.processing)
        and (query.audience is None or source.audience == query.audience)
        and (query.service is None or query.service in source.services)
        and (query.lifecycle is None or source.lifecycle == query.lifecycle)
        and (query.approved is None or source.approved == query.approved)
    )


class InMemoryKnowledgeStore:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}
        self._chunks: dict[str, list[Chunk]] = {}
        self._events: list[Event] = []
        self._services: dict[str, Service] = {}
        self._gaps: dict[str, Gap] = {}
        self._vectors: dict[tuple[str, str], tuple[float, ...]] = {}
        """(space, text hash) -> the normalised vector."""

    async def add_source(self, source: Source, chunks: Sequence[Chunk]) -> None:
        self._sources[source.id] = replace(source)
        self._chunks[source.id] = list(chunks)

    async def get(self, source_id: str) -> Source | None:
        found = self._sources.get(source_id)
        return None if found is None else replace(found)

    async def save(self, source: Source) -> None:
        self._sources[source.id] = replace(source)

    async def replace_chunks(self, source_id: str, chunks: Sequence[Chunk]) -> None:
        self._chunks[source_id] = list(chunks)

    async def delete(self, source_id: str) -> bool:
        self._chunks.pop(source_id, None)
        return self._sources.pop(source_id, None) is not None

    async def find(self, query: SourceFilter) -> tuple[list[Source], int]:
        found = sorted(
            (s for s in self._sources.values() if matches(s, query)),
            key=lambda s: (s.updated_at or datetime.min, s.id),
            reverse=True,
        )
        start = (query.page - 1) * query.page_size
        return [replace(s) for s in found[start : start + query.page_size]], len(found)

    async def all_sources(self) -> list[Source]:
        return [replace(s) for s in self._sources.values()]

    async def by_code(self, doc_code: str) -> Source | None:
        found = [s for s in self._sources.values() if s.doc_code == doc_code and s.lifecycle == "active"]
        return replace(found[-1]) if found else None

    async def in_force(self, key: str, as_of: date) -> Source | None:
        found = [s for s in self._sources.values() if key in (s.doc_code, s.id) and in_use(s, as_of)]
        latest = max(
            found, key=lambda s: (s.effective_from or date.min, s.created_at or datetime.min), default=None
        )
        return None if latest is None else replace(latest)

    async def by_hash(self, content_hash: str) -> Source | None:
        found = [s for s in self._sources.values() if s.content_hash == content_hash]
        return replace(found[0]) if found else None

    async def chunks(
        self, source_id: str, q: str, page: int, page_size: int, space: str | None
    ) -> tuple[list[Chunk], int]:
        needle = fold(q.strip())
        found = [
            replace(c, embedded=space is not None and (space, c.embed_hash) in self._vectors)
            for c in self._chunks.get(source_id, [])
            if not needle or needle in fold(f"{c.path} {c.body}")
        ]
        start = (page - 1) * page_size
        return found[start : start + page_size], len(found)

    async def update_chunk(self, chunk_id: str, services: list[str] | None, kind: str | None) -> bool:
        for source_id, chunks in self._chunks.items():
            for index, item in enumerate(chunks):
                if item.id != chunk_id:
                    continue
                changed = replace(
                    item,
                    services=tuple(services) if services is not None else item.services,
                    kind=kind if kind is not None else item.kind,
                )
                self._chunks[source_id] = [*chunks[:index], changed, *chunks[index + 1 :]]
                return True
        return False

    async def search(self, query: Sequence[str], as_of: date, limit: int) -> list[Hit]:
        live = [s for s in self._sources.values() if in_use(s, as_of)]
        docs = [
            (source, item, Counter(chunk_terms(item)))
            for source in live
            for item in self._chunks.get(source.id, [])
        ]
        if not docs or not query:
            return []
        average = sum(sum(counts.values()) for _, _, counts in docs) / len(docs)
        frequency = {term: sum(1 for _, _, counts in docs if term in counts) for term in query}
        total = len(docs)

        def score(counts: Counter[str]) -> float:
            length = sum(counts.values())
            return sum(
                _idf(total, frequency[term])
                * counts[term]
                * (BM25_K1 + 1)
                / (counts[term] + BM25_K1 * (1 - BM25_B + BM25_B * length / average))
                for term in query
                if counts[term]
            )

        ranked = sorted(
            (Hit(item, source.title, source.doc_code, score(counts)) for source, item, counts in docs),
            key=lambda hit: hit.score,
            reverse=True,
        )
        return [hit for hit in ranked if hit.score > 0][:limit]

    async def vector_search(
        self, space: str, vector: Sequence[float], as_of: date, limit: int, min_similarity: float
    ) -> list[Hit]:
        scored = [
            Hit(replace(item, embedded=True), source.title, source.doc_code, _cosine(vector, have))
            for source in self._sources.values()
            if in_use(source, as_of)
            for item in self._chunks.get(source.id, [])
            if (have := self._vectors.get((space, item.embed_hash))) is not None
        ]
        close = [hit for hit in scored if hit.score >= min_similarity]
        return sorted(close, key=lambda hit: (-hit.score, hit.chunk.id))[:limit]

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        wanting = {
            item.embed_hash: item.embed_text
            for source in self._sources.values()
            if embeddable(source)
            for item in self._chunks.get(source.id, [])
            if item.embed_hash and (space, item.embed_hash) not in self._vectors
        }
        return sorted(wanting.items())[:limit]

    async def missing_count(self, space: str) -> int:
        return sum(
            1
            for source in self._sources.values()
            if embeddable(source)
            for item in self._chunks.get(source.id, [])
            if item.embed_hash and (space, item.embed_hash) not in self._vectors
        )

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None:
        for text_hash, vector in items:
            self._vectors.setdefault((space, text_hash), tuple(vector))

    async def vector_counts(self, space: str) -> dict[str, int]:
        counts = {
            source_id: sum(1 for item in items if (space, item.embed_hash) in self._vectors)
            for source_id, items in self._chunks.items()
        }
        return {source_id: count for source_id, count in counts.items() if count}

    async def clear_vectors(self, space: str) -> int:
        gone = [key for key in self._vectors if key[0] == space]
        for key in gone:
            del self._vectors[key]
        return len(gone)

    async def drop_stale_vectors(self, space: str) -> int:
        used = {item.embed_hash for items in self._chunks.values() for item in items}
        gone = [key for key in self._vectors if key[0] != space or key[1] not in used]
        for key in gone:
            del self._vectors[key]
        return len(gone)

    async def add_event(self, event: Event) -> None:
        self._events.append(event)

    async def events(self, source_id: str) -> list[Event]:
        return sorted((e for e in self._events if e.source_id == source_id), key=lambda e: e.at, reverse=True)

    async def services(self) -> list[Service]:
        return sorted((replace(s) for s in self._services.values()), key=lambda s: s.code)

    async def save_service(self, service: Service) -> None:
        self._services[service.id] = replace(service)

    async def delete_service(self, service_id: str) -> bool:
        return self._services.pop(service_id, None) is not None

    async def service_chunks(self) -> dict[str, int]:
        counts: Counter[str] = Counter(
            code for chunks in self._chunks.values() for c in chunks for code in c.services
        )
        return dict(counts)

    async def record_gap(self, gap: Gap) -> None:
        known = next((g for g in self._gaps.values() if g.folded == gap.folded), None)
        if known is None:
            self._gaps[gap.id] = replace(gap)
            return
        known.count += 1
        known.last_asked_at = gap.last_asked_at
        known.channel = gap.channel
        known.state = "open" if known.state == "answered" else known.state

    async def gaps(self, state: GapState) -> list[Gap]:
        return sorted(
            (replace(g) for g in self._gaps.values() if g.state == state),
            key=lambda g: g.last_asked_at,
            reverse=True,
        )

    async def set_gap(self, gap_id: str, state: GapState) -> Gap | None:
        found = self._gaps.get(gap_id)
        if found is None:
            return None
        found.state = state
        return replace(found)


def _idf(total: int, containing: int) -> float:
    return math.log(1 + (total - containing + 0.5) / (containing + 0.5))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two normalised vectors of the same space: their dot product."""
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


# -- Postgres ------------------------------------------------------------------------------------------------

_SOURCE_COLUMNS: Final = (
    "id, title, doc_code, kind, format, size, services, audience, processing, progress, error, lifecycle, "
    "version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, note, markdown, "
    "content_hash, supersedes, created_by, created_at, updated_at"
)
_SCOPE: Final = "tenant_id = :tenant_id AND agent = :agent"

_UPSERT_SOURCE = text(
    "INSERT INTO agent_rt.kb_source (tenant_id, agent, id, title, doc_code, kind, format, size, services, "
    "audience, processing, progress, error, lifecycle, version, effective_from, effective_to, approved, "
    "approved_by, approved_at, chunk_count, note, markdown, content_hash, supersedes, created_by) "
    "VALUES (:tenant_id, :agent, :id, :title, :doc_code, :kind, :format, :size, :services, :audience, "
    ":processing, CAST(:progress AS jsonb), :error, :lifecycle, :version, :effective_from, :effective_to, "
    ":approved, :approved_by, :approved_at, :chunk_count, :note, :markdown, :content_hash, :supersedes, "
    ":created_by) "
    "ON CONFLICT (tenant_id, agent, id) DO UPDATE SET title = EXCLUDED.title, doc_code = EXCLUDED.doc_code, "
    "services = EXCLUDED.services, audience = EXCLUDED.audience, processing = EXCLUDED.processing, "
    "progress = EXCLUDED.progress, error = EXCLUDED.error, lifecycle = EXCLUDED.lifecycle, "
    "version = EXCLUDED.version, effective_from = EXCLUDED.effective_from, "
    "effective_to = EXCLUDED.effective_to, approved = EXCLUDED.approved, approved_by = EXCLUDED.approved_by, "
    "approved_at = EXCLUDED.approved_at, chunk_count = EXCLUDED.chunk_count, note = EXCLUDED.note, "
    "markdown = EXCLUDED.markdown, content_hash = EXCLUDED.content_hash, supersedes = EXCLUDED.supersedes, "
    "updated_at = now()"
).bindparams(bindparam("services", type_=ARRAY(Text)))
_INSERT_CHUNK = text(
    "INSERT INTO agent_rt.kb_chunk (tenant_id, agent, id, source_id, ordinal, path, body, chars, services, "
    "kind, embed_text, embed_hash, terms) VALUES (:tenant_id, :agent, :id, :source_id, :ordinal, :path, "
    ":body, :chars, :services, :kind, :embed_text, :embed_hash, to_tsvector('simple', :terms))"
).bindparams(bindparam("services", type_=ARRAY(Text)))
_DELETE_CHUNKS = text(
    "DELETE FROM agent_rt.kb_chunk WHERE tenant_id = :tenant_id AND agent = :agent AND source_id = :source_id"
)
_GET_SOURCE = text(
    "SELECT id, title, doc_code, kind, format, size, services, audience, processing, progress, error, "
    "lifecycle, version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, "
    "note, markdown, content_hash, supersedes, created_by, created_at, updated_at FROM agent_rt.kb_source "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_DELETE_SOURCE = text(
    "DELETE FROM agent_rt.kb_source WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_ALL_SOURCES = text(
    "SELECT id, title, doc_code, kind, format, size, services, audience, processing, progress, error, "
    "lifecycle, version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, "
    "note, markdown, content_hash, supersedes, created_by, created_at, updated_at FROM agent_rt.kb_source "
    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY updated_at DESC"
)
_BY_CODE = text(
    "SELECT id, title, doc_code, kind, format, size, services, audience, processing, progress, error, "
    "lifecycle, version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, "
    "note, markdown, content_hash, supersedes, created_by, created_at, updated_at FROM agent_rt.kb_source "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND doc_code = :code "
    "AND lifecycle = 'active' ORDER BY created_at DESC LIMIT 1"
)
_IN_FORCE = text(
    "SELECT id, title, doc_code, kind, format, size, services, audience, processing, progress, error, "
    "lifecycle, version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, "
    "note, markdown, content_hash, supersedes, created_by, created_at, updated_at FROM agent_rt.kb_source "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND (doc_code = :key OR id = :key) "
    "AND processing = 'ready' AND lifecycle = 'active' "
    "AND (effective_from IS NULL OR effective_from <= :as_of) "
    "AND (effective_to IS NULL OR effective_to >= :as_of) "
    "ORDER BY effective_from DESC NULLS LAST, created_at DESC LIMIT 1"
)
_BY_HASH = text(
    "SELECT id, title, doc_code, kind, format, size, services, audience, processing, progress, error, "
    "lifecycle, version, effective_from, effective_to, approved, approved_by, approved_at, chunk_count, "
    "note, markdown, content_hash, supersedes, created_by, created_at, updated_at FROM agent_rt.kb_source "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND content_hash = :hash LIMIT 1"
)
_CHUNKS = text(
    "SELECT c.id, c.source_id, c.ordinal, c.path, c.body, c.services, c.kind, c.embed_text, "
    "(e.text_hash IS NOT NULL) AS embedded FROM agent_rt.kb_chunk c "
    "LEFT JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent "
    "AND e.space = :space AND e.text_hash = c.embed_hash "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.source_id = :source_id ORDER BY c.ordinal"
)
_UPDATE_CHUNK = text(
    "UPDATE agent_rt.kb_chunk SET services = COALESCE(:services, services), kind = COALESCE(:kind, kind) "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
).bindparams(bindparam("services", type_=ARRAY(Text)))
_SEARCH = text(
    "SELECT c.id, c.source_id, c.ordinal, c.path, c.body, c.services, c.kind, c.embed_text, "
    "false AS embedded, s.title, s.doc_code, "
    "ts_rank_cd(c.terms, q.query) AS score "
    "FROM agent_rt.kb_chunk c "
    "JOIN agent_rt.kb_source s ON s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id "
    "CROSS JOIN (SELECT to_tsquery('simple', :query) AS query) q "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.terms @@ q.query "
    "AND s.processing = 'ready' AND s.lifecycle = 'active' "
    "AND (s.effective_from IS NULL OR s.effective_from <= :as_of) "
    "AND (s.effective_to IS NULL OR s.effective_to >= :as_of) "
    "ORDER BY score DESC, c.id LIMIT :limit"
)
_VECTOR_SEARCH = text(
    "SELECT c.id, c.source_id, c.ordinal, c.path, c.body, c.services, c.kind, c.embed_text, "
    "true AS embedded, s.title, s.doc_code, "
    "1 - (e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) AS score "
    "FROM agent_rt.kb_chunk c "
    "JOIN agent_rt.kb_source s ON s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id "
    "JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent "
    "AND e.space = :space AND e.text_hash = c.embed_hash "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent "
    "AND s.processing = 'ready' AND s.lifecycle = 'active' "
    "AND (s.effective_from IS NULL OR s.effective_from <= :as_of) "
    "AND (s.effective_to IS NULL OR s.effective_to >= :as_of) "
    "AND 1 - (e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) >= :min_similarity "
    "ORDER BY e.vector OPERATOR(public.<=>) CAST(:vector AS public.vector), c.id LIMIT :limit"
)
_MISSING_FROM: Final = (
    "FROM agent_rt.kb_chunk c "
    "JOIN agent_rt.kb_source s ON s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.embed_hash <> '' "
    "AND s.processing = 'ready' AND s.lifecycle = 'active' "
    "AND NOT EXISTS (SELECT 1 FROM agent_rt.kb_embedding e WHERE e.tenant_id = c.tenant_id "
    "AND e.agent = c.agent AND e.space = :space AND e.text_hash = c.embed_hash)"
)
_MISSING_VECTORS = text(
    f"SELECT DISTINCT ON (c.embed_hash) c.embed_hash, c.embed_text {_MISSING_FROM} "
    "ORDER BY c.embed_hash LIMIT :limit"
)
_MISSING_COUNT = text(f"SELECT count(*) {_MISSING_FROM}")
_SAVE_VECTOR = text(
    "INSERT INTO agent_rt.kb_embedding (tenant_id, agent, space, text_hash, vector) "
    "VALUES (:tenant_id, :agent, :space, :text_hash, CAST(:vector AS public.vector)) ON CONFLICT DO NOTHING"
)
_VECTOR_COUNTS = text(
    "SELECT c.source_id, count(*) FROM agent_rt.kb_chunk c "
    "JOIN agent_rt.kb_embedding e ON e.tenant_id = c.tenant_id AND e.agent = c.agent "
    "AND e.space = :space AND e.text_hash = c.embed_hash "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent GROUP BY c.source_id"
)
_CLEAR_VECTORS = text(
    "DELETE FROM agent_rt.kb_embedding WHERE tenant_id = :tenant_id AND agent = :agent AND space = :space"
)
_DROP_STALE = text(
    "DELETE FROM agent_rt.kb_embedding e WHERE e.tenant_id = :tenant_id AND e.agent = :agent "
    "AND (e.space <> :space OR NOT EXISTS (SELECT 1 FROM agent_rt.kb_chunk c WHERE c.tenant_id = e.tenant_id "
    "AND c.agent = e.agent AND c.embed_hash = e.text_hash))"
)
_INSERT_EVENT = text(
    "INSERT INTO agent_rt.kb_event (tenant_id, agent, id, source_id, at, kind, by_whom, note) "
    "VALUES (:tenant_id, :agent, :id, :source_id, :at, :kind, :by, :note)"
)
_EVENTS = text(
    "SELECT id, source_id, at, kind, by_whom, note FROM agent_rt.kb_event WHERE tenant_id = :tenant_id AND "
    "agent = :agent "
    "AND source_id = :source_id ORDER BY at DESC LIMIT 200"
)
_SERVICES = text(
    "SELECT id, code, name, aliases, description, branches, enabled FROM agent_rt.kb_service "
    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY code"
)
_UPSERT_SERVICE = text(
    "INSERT INTO agent_rt.kb_service (tenant_id, agent, id, code, name, aliases, description, branches, "
    "enabled) "
    "VALUES (:tenant_id, :agent, :id, :code, :name, :aliases, :description, :branches, :enabled) "
    "ON CONFLICT (tenant_id, agent, id) DO UPDATE SET code = EXCLUDED.code, name = EXCLUDED.name, "
    "aliases = EXCLUDED.aliases, description = EXCLUDED.description, branches = EXCLUDED.branches, "
    "enabled = EXCLUDED.enabled"
).bindparams(bindparam("aliases", type_=ARRAY(Text)), bindparam("branches", type_=ARRAY(Text)))
_DELETE_SERVICE = text(
    "DELETE FROM agent_rt.kb_service WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_SERVICE_CHUNKS = text(
    "SELECT code, count(*) FROM agent_rt.kb_chunk, unnest(services) AS code WHERE tenant_id = :tenant_id "
    "AND agent = :agent GROUP BY code"
)
_RECORD_GAP = text(
    "INSERT INTO agent_rt.kb_gap (tenant_id, agent, id, folded, question, count, channel, last_asked_at, "
    "state) "
    "VALUES (:tenant_id, :agent, :id, :folded, :question, 1, :channel, :at, 'open') "
    "ON CONFLICT (tenant_id, agent, folded) DO UPDATE SET count = agent_rt.kb_gap.count + 1, "
    "channel = EXCLUDED.channel, last_asked_at = EXCLUDED.last_asked_at, "
    "state = CASE WHEN agent_rt.kb_gap.state = 'answered' THEN 'open' ELSE agent_rt.kb_gap.state END"
)
_GAPS = text(
    "SELECT id, folded, question, count, channel, last_asked_at, state FROM agent_rt.kb_gap "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND state = :state ORDER BY last_asked_at DESC LIMIT 500"
)
_SET_GAP = text(
    "UPDATE agent_rt.kb_gap SET state = :state WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id "
    "RETURNING id, folded, question, count, channel, last_asked_at, state"
)


class PostgresKnowledgeStore:
    """The plugin's ``kb_`` tables, as the runtime role (no DDL: ``agent db migrate-plugins`` made them)."""

    def __init__(self, engine: AsyncEngine, *, tenant_id: str, agent: str) -> None:
        self._engine = engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def add_source(self, source: Source, chunks: Sequence[Chunk]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(_UPSERT_SOURCE, self._source_params(source))
            await conn.execute(_DELETE_CHUNKS, {**self._scope, "source_id": source.id})
            if chunks:
                await conn.execute(_INSERT_CHUNK, [self._chunk_params(c) for c in chunks])

    async def get(self, source_id: str) -> Source | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_GET_SOURCE, {**self._scope, "id": source_id})).mappings().one_or_none()
        return None if row is None else _source(row)

    async def save(self, source: Source) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(_UPSERT_SOURCE, self._source_params(source))

    async def replace_chunks(self, source_id: str, chunks: Sequence[Chunk]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(_DELETE_CHUNKS, {**self._scope, "source_id": source_id})
            if chunks:
                await conn.execute(_INSERT_CHUNK, [self._chunk_params(c) for c in chunks])

    async def delete(self, source_id: str) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(_DELETE_SOURCE, {**self._scope, "id": source_id})
        return bool(getattr(result, "rowcount", 0))

    async def find(self, query: SourceFilter) -> tuple[list[Source], int]:
        found = [s for s in await self.all_sources() if matches(s, query)]
        start = (query.page - 1) * query.page_size
        return found[start : start + query.page_size], len(found)

    async def all_sources(self) -> list[Source]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_ALL_SOURCES, self._scope)).mappings().all()
        return [_source(row) for row in rows]

    async def by_code(self, doc_code: str) -> Source | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_BY_CODE, {**self._scope, "code": doc_code})).mappings().one_or_none()
        return None if row is None else _source(row)

    async def in_force(self, key: str, as_of: date) -> Source | None:
        params = {**self._scope, "key": key, "as_of": as_of}
        async with self._engine.connect() as conn:
            row = (await conn.execute(_IN_FORCE, params)).mappings().one_or_none()
        return None if row is None else _source(row)

    async def by_hash(self, content_hash: str) -> Source | None:
        async with self._engine.connect() as conn:
            row = (
                (await conn.execute(_BY_HASH, {**self._scope, "hash": content_hash})).mappings().one_or_none()
            )
        return None if row is None else _source(row)

    async def chunks(
        self, source_id: str, q: str, page: int, page_size: int, space: str | None
    ) -> tuple[list[Chunk], int]:
        params = {**self._scope, "source_id": source_id, "space": space or ""}
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_CHUNKS, params)).mappings().all()
        needle = fold(q.strip())
        found = [_chunk(row) for row in rows]
        kept = [c for c in found if not needle or needle in fold(f"{c.path} {c.body}")]
        start = (page - 1) * page_size
        return kept[start : start + page_size], len(kept)

    async def update_chunk(self, chunk_id: str, services: list[str] | None, kind: str | None) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                _UPDATE_CHUNK, {**self._scope, "id": chunk_id, "services": services, "kind": kind}
            )
        return bool(getattr(result, "rowcount", 0))

    async def search(self, query: Sequence[str], as_of: date, limit: int) -> list[Hit]:
        if not query:
            return []
        params = {**self._scope, "query": " | ".join(query), "as_of": as_of, "limit": limit}
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_SEARCH, params)).mappings().all()
        return [Hit(_chunk(row), row["title"], row["doc_code"], float(row["score"])) for row in rows]

    async def vector_search(
        self, space: str, vector: Sequence[float], as_of: date, limit: int, min_similarity: float
    ) -> list[Hit]:
        params = {
            **self._scope,
            "space": space,
            "vector": _vector_literal(vector),
            "as_of": as_of,
            "limit": limit,
            "min_similarity": min_similarity,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_VECTOR_SEARCH, params)).mappings().all()
        return [Hit(_chunk(row), row["title"], row["doc_code"], float(row["score"])) for row in rows]

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(_MISSING_VECTORS, {**self._scope, "space": space, "limit": limit})
            ).all()
        return [(str(text_hash), str(embed_text)) for text_hash, embed_text in rows]

    async def missing_count(self, space: str) -> int:
        async with self._engine.connect() as conn:
            return int((await conn.execute(_MISSING_COUNT, {**self._scope, "space": space})).scalar_one())

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None:
        if not items:
            return
        rows = [
            {**self._scope, "space": space, "text_hash": text_hash, "vector": _vector_literal(vector)}
            for text_hash, vector in items
        ]
        async with self._engine.begin() as conn:
            await conn.execute(_SAVE_VECTOR, rows)

    async def vector_counts(self, space: str) -> dict[str, int]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_VECTOR_COUNTS, {**self._scope, "space": space})).all()
        return {str(source_id): int(count) for source_id, count in rows}

    async def clear_vectors(self, space: str) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(_CLEAR_VECTORS, {**self._scope, "space": space})
        return int(getattr(result, "rowcount", 0))

    async def drop_stale_vectors(self, space: str) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(_DROP_STALE, {**self._scope, "space": space})
        return int(getattr(result, "rowcount", 0))

    async def add_event(self, event: Event) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                _INSERT_EVENT,
                {
                    **self._scope,
                    "id": event.id,
                    "source_id": event.source_id,
                    "at": event.at,
                    "kind": event.kind,
                    "by": event.by,
                    "note": event.note,
                },
            )

    async def events(self, source_id: str) -> list[Event]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_EVENTS, {**self._scope, "source_id": source_id})).mappings().all()
        return [
            Event(row["id"], row["source_id"], row["at"], row["kind"], row["by_whom"], row["note"])
            for row in rows
        ]

    async def services(self) -> list[Service]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_SERVICES, self._scope)).mappings().all()
        return [
            Service(
                row["id"],
                row["code"],
                row["name"],
                list(row["aliases"]),
                row["description"],
                list(row["branches"]),
                row["enabled"],
            )
            for row in rows
        ]

    async def save_service(self, service: Service) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                _UPSERT_SERVICE,
                {
                    **self._scope,
                    "id": service.id,
                    "code": service.code,
                    "name": service.name,
                    "aliases": service.aliases,
                    "description": service.description,
                    "branches": service.branches,
                    "enabled": service.enabled,
                },
            )

    async def delete_service(self, service_id: str) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(_DELETE_SERVICE, {**self._scope, "id": service_id})
        return bool(getattr(result, "rowcount", 0))

    async def service_chunks(self) -> dict[str, int]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_SERVICE_CHUNKS, self._scope)).all()
        return {str(code): int(count) for code, count in rows}

    async def record_gap(self, gap: Gap) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                _RECORD_GAP,
                {
                    **self._scope,
                    "id": gap.id,
                    "folded": gap.folded,
                    "question": gap.question,
                    "channel": gap.channel,
                    "at": gap.last_asked_at,
                },
            )

    async def gaps(self, state: GapState) -> list[Gap]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_GAPS, {**self._scope, "state": state})).mappings().all()
        return [_gap(row) for row in rows]

    async def set_gap(self, gap_id: str, state: GapState) -> Gap | None:
        async with self._engine.begin() as conn:
            row = (
                (await conn.execute(_SET_GAP, {**self._scope, "id": gap_id, "state": state}))
                .mappings()
                .one_or_none()
            )
        return None if row is None else _gap(row)

    def _source_params(self, source: Source) -> dict[str, Any]:
        return {
            **self._scope,
            "id": source.id,
            "title": source.title,
            "doc_code": source.doc_code,
            "kind": source.kind,
            "format": source.format,
            "size": source.size,
            "services": source.services,
            "audience": source.audience,
            "processing": source.processing,
            "progress": json.dumps(
                {"chunks": source.chunks, "labelled": source.labelled, "embedded": source.embedded}
            ),
            "error": source.error,
            "lifecycle": source.lifecycle,
            "version": source.version,
            "effective_from": source.effective_from,
            "effective_to": source.effective_to,
            "approved": source.approved,
            "approved_by": source.approved_by,
            "approved_at": source.approved_at,
            "chunk_count": source.chunk_count,
            "note": source.note,
            "markdown": source.markdown,
            "content_hash": source.content_hash,
            "supersedes": source.supersedes,
            "created_by": source.created_by,
        }

    def _chunk_params(self, item: Chunk) -> dict[str, Any]:
        return {
            **self._scope,
            "id": item.id,
            "source_id": item.source_id,
            "ordinal": item.ordinal,
            "path": item.path,
            "body": item.body,
            "chars": len(item.body),
            "services": list(item.services),
            "kind": item.kind,
            "embed_text": item.embed_text,
            "embed_hash": item.embed_hash,
            "terms": " ".join(chunk_terms(item)),
        }


def _source(row: Any) -> Source:
    progress = as_mapping(row["progress"])
    return Source(
        id=row["id"],
        title=row["title"],
        doc_code=row["doc_code"],
        kind=row["kind"],
        format=row["format"],
        size=row["size"],
        audience=row["audience"],
        lifecycle=row["lifecycle"],
        content_hash=row["content_hash"],
        created_by=row["created_by"],
        markdown=row["markdown"],
        services=list(row["services"]),
        processing=row["processing"],
        chunks=int(progress.get("chunks", 0)),
        labelled=int(progress.get("labelled", 0)),
        embedded=int(progress.get("embedded", 0)),
        error=row["error"],
        version=row["version"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        approved=row["approved"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        chunk_count=row["chunk_count"],
        note=row["note"],
        supersedes=row["supersedes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _chunk(row: Any) -> Chunk:
    return Chunk(
        id=row["id"],
        source_id=row["source_id"],
        ordinal=row["ordinal"],
        path=row["path"],
        body=row["body"],
        services=tuple(row["services"]),
        kind=row["kind"],
        embedded=bool(row["embedded"]),
        embed_text=row["embed_text"],
    )


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form, cast to its type in the SQL (no Python package for it is needed)."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _gap(row: Any) -> Gap:
    return Gap(
        id=row["id"],
        folded=row["folded"],
        question=row["question"],
        count=row["count"],
        channel=row["channel"],
        last_asked_at=row["last_asked_at"],
        state=row["state"],
    )
