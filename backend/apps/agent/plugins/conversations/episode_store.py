"""Where episodes and their vectors are kept: Postgres (the plugin's ``cv_episode`` tables, scoped by tenant
and agent) or process memory (tests, an agent run without a database).

A new episode whose question has the same fingerprint as one the channel already has is not a new row: the old
one counts one more repeat and takes the newer reaction of the staff. Episodes whose questions only mean the
same thing are joined later, once their vectors exist (``merge_into_nearest``)."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Final, Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .episodes import Draft
from .scenario_models import Counts, Episode, Hit, Reach, episode_id
from .words import terms

SEARCH_FLOOR: Final = 0.5
"""A keyword hit needs this share of the shorter of the two term lists in common."""
MIN_SHARED_TERMS: Final = 2


class EpisodeStore(Protocol):
    async def add(
        self, draft: Draft, *, channel: str, plugin: str, conversation_id: str
    ) -> tuple[Episode, bool]:
        """Stores the episode; the second value is False when it was kept before or joined an episode with the
        same question (which then counts one more repeat)."""
        ...

    async def episodes(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Episode], int]: ...

    async def get(self, episode_id: str) -> Episode | None: ...

    async def set_enabled(self, episode_id: str, enabled: bool) -> bool: ...

    async def delete(self, episode_id: str) -> bool: ...

    async def delete_of_conversations(self, conversation_ids: Sequence[str]) -> int:
        """Deletes the episodes cut from these conversations (vectors with them); how many."""
        ...

    async def search_words(self, query_terms: Sequence[str], reach: Reach, limit: int) -> list[Hit]: ...

    async def search_vector(
        self, space: str, vector: Sequence[float], reach: Reach, limit: int, min_similarity: float
    ) -> list[Hit]: ...

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        """(id, question) of episodes with no vector in ``space``."""
        ...

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None: ...

    async def merge_into_nearest(self, episode_id: str, space: str, min_similarity: float) -> str | None:
        """Joins the episode into the most similar other episode of its channel when that is at least
        ``min_similarity`` alike; the id it joined, or None."""
        ...

    async def counts(self, space: str | None) -> Counts: ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=False))


def _in_reach(episode: Episode, reach: Reach) -> bool:
    if not episode.enabled:
        return False
    if reach.channel is not None and episode.channel != reach.channel:
        return False
    return reach.plugin is None or episode.plugin == reach.plugin


class InMemoryEpisodeStore:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._episodes: dict[str, Episode] = {}
        self._vectors: dict[tuple[str, str], tuple[float, ...]] = {}

    async def add(
        self, draft: Draft, *, channel: str, plugin: str, conversation_id: str
    ) -> tuple[Episode, bool]:
        new_id = episode_id(conversation_id, draft.first_seq)
        if new_id in self._episodes:
            return self._episodes[new_id], False
        same = next(
            (
                e
                for e in self._episodes.values()
                if e.channel == channel and e.fingerprint == draft.fingerprint
            ),
            None,
        )
        if same is not None:
            joined = replace(
                same,
                repeats=same.repeats + 1,
                transcript=draft.transcript,
                ended_at=max(same.ended_at, draft.ended_at),
                updated_at=self._clock(),
            )
            self._episodes[same.id] = joined
            return joined, False
        episode = Episode(
            id=new_id,
            channel=channel,
            plugin=plugin,
            conversation_id=conversation_id,
            started_at=draft.started_at,
            ended_at=draft.ended_at,
            first_seq=draft.first_seq,
            last_seq=draft.last_seq,
            ask=draft.ask,
            transcript=draft.transcript,
            fingerprint=draft.fingerprint,
            repeats=1,
            enabled=True,
            updated_at=self._clock(),
        )
        self._episodes[new_id] = episode
        return episode, True

    async def episodes(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Episode], int]:
        needle = query.strip().lower()

        def matches(e: Episode) -> bool:
            if channel is not None and e.channel != channel:
                return False
            return not needle or needle in e.ask.lower() or any(needle in t.lower() for _, t in e.transcript)

        found = sorted(
            (e for e in self._episodes.values() if matches(e)), key=lambda e: e.updated_at, reverse=True
        )
        return found[offset : offset + limit], len(found)

    async def get(self, episode_id: str) -> Episode | None:
        return self._episodes.get(episode_id)

    async def set_enabled(self, episode_id: str, enabled: bool) -> bool:
        found = self._episodes.get(episode_id)
        if found is None:
            return False
        self._episodes[episode_id] = replace(found, enabled=enabled)
        return True

    async def delete(self, episode_id: str) -> bool:
        for key in [k for k in self._vectors if k[1] == episode_id]:
            del self._vectors[key]
        return self._episodes.pop(episode_id, None) is not None

    async def delete_of_conversations(self, conversation_ids: Sequence[str]) -> int:
        wanted = set(conversation_ids)
        gone = {i for i, e in self._episodes.items() if e.conversation_id in wanted}
        for key in [k for k in self._vectors if k[1] in gone]:
            del self._vectors[key]
        for stale in gone:
            del self._episodes[stale]
        return len(gone)

    async def search_words(self, query_terms: Sequence[str], reach: Reach, limit: int) -> list[Hit]:
        wanted = set(query_terms)
        hits: list[Hit] = []
        for episode in self._episodes.values():
            if not _in_reach(episode, reach):
                continue
            have = set(terms(episode.ask))
            shared = len(wanted & have)
            share = shared / max(1, min(len(wanted), len(have)))
            if shared >= MIN_SHARED_TERMS and share >= SEARCH_FLOOR:
                hits.append(Hit(episode, share, "words"))
        return sorted(hits, key=lambda h: (-h.score, -h.episode.repeats, -h.episode.updated_at.timestamp()))[
            :limit
        ]

    async def search_vector(
        self, space: str, vector: Sequence[float], reach: Reach, limit: int, min_similarity: float
    ) -> list[Hit]:
        hits = [
            Hit(episode, similarity, "meaning")
            for episode in self._episodes.values()
            if _in_reach(episode, reach)
            and (have := self._vectors.get((space, episode.id))) is not None
            and (similarity := _cosine(vector, have)) >= min_similarity
        ]
        return sorted(hits, key=lambda h: (-h.score, h.episode.id))[:limit]

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        missing = [e for e in self._episodes.values() if (space, e.id) not in self._vectors]
        return [(e.id, e.ask) for e in sorted(missing, key=lambda e: e.updated_at)[:limit]]

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None:
        for item_id, vector in items:
            if item_id in self._episodes:
                self._vectors[(space, item_id)] = tuple(vector)

    async def merge_into_nearest(self, episode_id: str, space: str, min_similarity: float) -> str | None:
        mine = self._episodes.get(episode_id)
        have = self._vectors.get((space, episode_id))
        if mine is None or have is None:
            return None
        best = max(
            (
                (_cosine(have, other_vector), other)
                for other in self._episodes.values()
                if other.id != episode_id
                and other.channel == mine.channel
                and (other_vector := self._vectors.get((space, other.id))) is not None
            ),
            key=lambda pair: pair[0],
            default=None,
        )
        if best is None or best[0] < min_similarity:
            return None
        target = best[1]
        self._episodes[target.id] = replace(
            target,
            repeats=target.repeats + mine.repeats,
            transcript=mine.transcript,
            ended_at=max(target.ended_at, mine.ended_at),
            updated_at=self._clock(),
        )
        await self.delete(episode_id)
        return target.id

    async def counts(self, space: str | None) -> Counts:
        total = len(self._episodes)
        if space is None:
            return Counts(total, 0)
        return Counts(total, sum(1 for e in self._episodes if (space, e) not in self._vectors))


_COLUMNS: Final = (
    "e.id, e.channel, e.plugin, e.conversation_id, e.started_at, e.ended_at, e.first_seq, e.last_seq, e.ask, "
    "e.transcript, e.fingerprint, e.repeats, e.enabled, e.updated_at"
)
_EXISTS = text(
    "SELECT 1 FROM agent_rt.cv_episode WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_JOIN_SAME = text(
    "UPDATE agent_rt.cv_episode SET repeats = repeats + 1, transcript = CAST(:transcript AS jsonb), "
    "ended_at = GREATEST(ended_at, :ended_at), updated_at = now() "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND channel = :channel AND fingerprint = :fingerprint "
    "RETURNING id"
)
_INSERT = text(
    "INSERT INTO agent_rt.cv_episode (tenant_id, agent, id, channel, plugin, conversation_id, started_at, "
    "ended_at, first_seq, last_seq, ask, transcript, fingerprint, terms) "
    "VALUES (:tenant_id, :agent, :id, :channel, :plugin, :conversation_id, :started_at, :ended_at, "
    ":first_seq, :last_seq, :ask, CAST(:transcript AS jsonb), :fingerprint, to_tsvector('simple', :terms)) "
    "ON CONFLICT (tenant_id, agent, id) DO NOTHING"
)
_GET = text(
    f"SELECT {_COLUMNS} FROM agent_rt.cv_episode e "  # noqa: S608
    "WHERE e.tenant_id = :tenant_id AND e.agent = :agent AND e.id = :id"
)
_LIST_FROM = (
    "FROM agent_rt.cv_episode e WHERE e.tenant_id = :tenant_id AND e.agent = :agent "
    "AND (CAST(:channel AS text) IS NULL OR e.channel = :channel) "
    "AND (CAST(:like AS text) IS NULL OR e.ask ILIKE :like OR CAST(e.transcript AS text) ILIKE :like)"
)
_LIST = text(f"SELECT {_COLUMNS} {_LIST_FROM} ORDER BY e.updated_at DESC, e.id LIMIT :limit OFFSET :offset")
_LIST_COUNT = text(f"SELECT count(*) {_LIST_FROM}")
_ENABLE = text(
    "UPDATE agent_rt.cv_episode SET enabled = :enabled "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_DELETE = text("DELETE FROM agent_rt.cv_episode WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id")
_DELETE_OF_CONVERSATIONS = text(
    "DELETE FROM agent_rt.cv_episode "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND conversation_id = ANY(:conversation_ids)"
)
_REACH: Final = (
    "e.tenant_id = :tenant_id AND e.agent = :agent AND e.enabled "
    "AND (CAST(:channel AS text) IS NULL OR e.channel = :channel) "
    "AND (CAST(:plugin AS text) IS NULL OR e.plugin = :plugin)"
)
_SEARCH_WORDS = text(
    f"SELECT {_COLUMNS}, ts_rank_cd(e.terms, q.query) AS score "  # noqa: S608
    "FROM agent_rt.cv_episode e CROSS JOIN (SELECT to_tsquery('simple', :query) AS query) q "
    f"WHERE {_REACH} AND e.terms @@ q.query ORDER BY score DESC, e.repeats DESC, e.id LIMIT :limit"
)
_SEARCH_VECTOR = text(
    f"SELECT {_COLUMNS}, 1 - (v.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) AS score "  # noqa: S608
    "FROM agent_rt.cv_episode e JOIN agent_rt.cv_episode_vector v ON v.tenant_id = e.tenant_id "
    "AND v.agent = e.agent AND v.episode_id = e.id AND v.space = :space "
    f"WHERE {_REACH} "
    "AND 1 - (v.vector OPERATOR(public.<=>) CAST(:vector AS public.vector)) >= :min_similarity "
    "ORDER BY v.vector OPERATOR(public.<=>) CAST(:vector AS public.vector), e.id LIMIT :limit"
)
_MISSING = text(
    "SELECT e.id, e.ask FROM agent_rt.cv_episode e WHERE e.tenant_id = :tenant_id AND e.agent = :agent "
    "AND NOT EXISTS (SELECT 1 FROM agent_rt.cv_episode_vector v WHERE v.tenant_id = e.tenant_id "
    "AND v.agent = e.agent AND v.episode_id = e.id AND v.space = :space) "
    "ORDER BY e.updated_at, e.id LIMIT :limit"
)
_SAVE_VECTOR = text(
    "INSERT INTO agent_rt.cv_episode_vector (tenant_id, agent, space, episode_id, vector) "
    "SELECT :tenant_id, :agent, :space, e.id, CAST(:vector AS public.vector) FROM agent_rt.cv_episode e "
    "WHERE e.tenant_id = :tenant_id AND e.agent = :agent AND e.id = :id ON CONFLICT DO NOTHING"
)
_NEAREST = text(
    "SELECT o.id, 1 - (w.vector OPERATOR(public.<=>) v.vector) AS score "
    "FROM agent_rt.cv_episode_vector v JOIN agent_rt.cv_episode me ON me.tenant_id = v.tenant_id "
    "AND me.agent = v.agent AND me.id = v.episode_id "
    "JOIN agent_rt.cv_episode o ON o.tenant_id = me.tenant_id AND o.agent = me.agent AND o.id <> me.id "
    "AND o.channel = me.channel "
    "JOIN agent_rt.cv_episode_vector w ON w.tenant_id = o.tenant_id AND w.agent = o.agent "
    "AND w.episode_id = o.id AND w.space = v.space "
    "WHERE v.tenant_id = :tenant_id AND v.agent = :agent AND v.episode_id = :id AND v.space = :space "
    "ORDER BY w.vector OPERATOR(public.<=>) v.vector LIMIT 1"
)
_ABSORB = text(
    "UPDATE agent_rt.cv_episode t SET repeats = t.repeats + s.repeats, transcript = s.transcript, "
    "ended_at = GREATEST(t.ended_at, s.ended_at), updated_at = now() "
    "FROM agent_rt.cv_episode s WHERE t.tenant_id = :tenant_id AND t.agent = :agent AND t.id = :target "
    "AND s.tenant_id = t.tenant_id AND s.agent = t.agent AND s.id = :id"
)
_COUNTS = text(
    "SELECT count(*) AS total, count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM agent_rt.cv_episode_vector v "
    "WHERE v.tenant_id = e.tenant_id AND v.agent = e.agent AND v.episode_id = e.id "
    "AND v.space = CAST(:space AS text))) AS without_vector "
    "FROM agent_rt.cv_episode e WHERE e.tenant_id = :tenant_id AND e.agent = :agent"
)


class PostgresEpisodeStore:
    def __init__(self, engine: AsyncEngine, *, tenant_id: str, agent: str) -> None:
        self._engine = engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def add(
        self, draft: Draft, *, channel: str, plugin: str, conversation_id: str
    ) -> tuple[Episode, bool]:
        new_id = episode_id(conversation_id, draft.first_seq)
        params = {
            **self._scope,
            "id": new_id,
            "channel": channel,
            "plugin": plugin,
            "conversation_id": conversation_id,
            "started_at": draft.started_at,
            "ended_at": draft.ended_at,
            "first_seq": draft.first_seq,
            "last_seq": draft.last_seq,
            "ask": draft.ask,
            "transcript": json.dumps([[role, line] for role, line in draft.transcript], ensure_ascii=False),
            "fingerprint": draft.fingerprint,
            "terms": " ".join(terms(draft.ask)),
        }
        async with self._engine.begin() as conn:
            if (await conn.execute(_EXISTS, params)).first() is not None:
                created, kept = False, new_id
            elif (joined := (await conn.execute(_JOIN_SAME, params)).first()) is not None:
                created, kept = False, str(joined[0])
            else:
                await conn.execute(_INSERT, params)
                created, kept = True, new_id
            row = (await conn.execute(_GET, {**self._scope, "id": kept})).mappings().one()
        return _episode(row), created

    async def episodes(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Episode], int]:
        params: dict[str, Any] = {
            **self._scope,
            "channel": channel,
            "like": _like(query.strip()) if query.strip() else None,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_LIST, {**params, "limit": limit, "offset": offset})).mappings().all()
            total = (await conn.execute(_LIST_COUNT, params)).scalar_one()
        return [_episode(row) for row in rows], int(total)

    async def get(self, episode_id: str) -> Episode | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_GET, {**self._scope, "id": episode_id})).mappings().one_or_none()
        return None if row is None else _episode(row)

    async def set_enabled(self, episode_id: str, enabled: bool) -> bool:
        async with self._engine.begin() as conn:
            done = await conn.execute(_ENABLE, {**self._scope, "id": episode_id, "enabled": enabled})
        return done.rowcount > 0

    async def delete(self, episode_id: str) -> bool:
        async with self._engine.begin() as conn:
            done = await conn.execute(_DELETE, {**self._scope, "id": episode_id})
        return done.rowcount > 0

    async def delete_of_conversations(self, conversation_ids: Sequence[str]) -> int:
        async with self._engine.begin() as conn:
            done = await conn.execute(
                _DELETE_OF_CONVERSATIONS, {**self._scope, "conversation_ids": list(conversation_ids)}
            )
        return done.rowcount

    async def search_words(self, query_terms: Sequence[str], reach: Reach, limit: int) -> list[Hit]:
        if not query_terms:
            return []
        params = {
            **self._scope,
            "query": " | ".join(query_terms),
            "channel": reach.channel,
            "plugin": reach.plugin,
            "limit": limit * 4,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_SEARCH_WORDS, params)).mappings().all()
        wanted = set(query_terms)
        hits: list[Hit] = []
        for row in rows:
            episode = _episode(row)
            have = set(terms(episode.ask))
            shared = len(wanted & have)
            share = shared / max(1, min(len(wanted), len(have)))
            if shared >= MIN_SHARED_TERMS and share >= SEARCH_FLOOR:
                hits.append(Hit(episode, share, "words"))
        return sorted(hits, key=lambda h: (-h.score, -h.episode.repeats))[:limit]

    async def search_vector(
        self, space: str, vector: Sequence[float], reach: Reach, limit: int, min_similarity: float
    ) -> list[Hit]:
        params = {
            **self._scope,
            "space": space,
            "vector": _vector_literal(vector),
            "channel": reach.channel,
            "plugin": reach.plugin,
            "limit": limit,
            "min_similarity": min_similarity,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_SEARCH_VECTOR, params)).mappings().all()
        return [Hit(_episode(row), float(row["score"]), "meaning") for row in rows]

    async def missing_vectors(self, space: str, limit: int) -> list[tuple[str, str]]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_MISSING, {**self._scope, "space": space, "limit": limit})).all()
        return [(str(row[0]), str(row[1])) for row in rows]

    async def save_vectors(self, space: str, items: Sequence[tuple[str, Sequence[float]]]) -> None:
        if not items:
            return
        rows = [
            {**self._scope, "space": space, "id": item_id, "vector": _vector_literal(vector)}
            for item_id, vector in items
        ]
        async with self._engine.begin() as conn:
            await conn.execute(_SAVE_VECTOR, rows)

    async def merge_into_nearest(self, episode_id: str, space: str, min_similarity: float) -> str | None:
        async with self._engine.begin() as conn:
            nearest = (
                await conn.execute(_NEAREST, {**self._scope, "id": episode_id, "space": space})
            ).first()
            if nearest is None or float(nearest[1]) < min_similarity:
                return None
            target = str(nearest[0])
            await conn.execute(_ABSORB, {**self._scope, "id": episode_id, "target": target})
            await conn.execute(_DELETE, {**self._scope, "id": episode_id})
        return target

    async def counts(self, space: str | None) -> Counts:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_COUNTS, {**self._scope, "space": space})).one()
        total = int(row[0])
        return Counts(total, 0 if space is None else int(row[1]))


def _like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form, cast to its type in the SQL (no Python package for it is needed)."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _episode(row: Any) -> Episode:
    raw: Any = row["transcript"]
    lines = json.loads(raw) if isinstance(raw, str) else raw
    return Episode(
        id=row["id"],
        channel=row["channel"],
        plugin=row["plugin"],
        conversation_id=row["conversation_id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        first_seq=row["first_seq"],
        last_seq=row["last_seq"],
        ask=row["ask"],
        transcript=tuple((str(role), str(line)) for role, line in cast(list[list[Any]], lines)),
        fingerprint=row["fingerprint"],
        repeats=row["repeats"],
        enabled=row["enabled"],
        updated_at=row["updated_at"],
    )
