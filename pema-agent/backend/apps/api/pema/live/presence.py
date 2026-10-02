"""Presence: who has a conversation open right now (ST-R).

New module (not a port). A WARNING shown beside the reply box ("Lan is replying"), never a lock: nothing in
this file, and nothing that reads it, can stop a person from sending. The browser sends a heartbeat every 15
seconds; an entry lives ``PRESENCE_TTL_S`` (30) seconds, so a closed tab or a crashed browser disappears by
itself, and a leave call (``DELETE``) removes it at once.

Two adapters of ``PresenceStore``: Redis (production; a sorted set per conversation whose score is the expiry
time, so ONE pipeline reads the viewers of a whole page of conversations) and memory (tests). The
``PresenceService`` on top is the only thing the routes use: it publishes ``presence.changed`` when the set of
viewers changes (and once more when the last heartbeat of someone expired, so the others stop showing
them) and
degrades to "nobody is here" when Redis is down: a heartbeat never fails, ``viewers`` is empty.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from pema.live.publisher import emit_live
from pema.shared.logger import create_logger
from pema_contracts.live import LiveEventType, PresenceState

log = create_logger("live.presence")

PRESENCE_TTL_S = 30.0
KEY_PREFIX = "pema:presence"
EXPIRY_NOTICE_SLACK_S = 1.0
"""The extra ``presence.changed`` after the last heartbeat is sent this long after the entry expired."""
MAX_OPS_PER_WINDOW = 120
WINDOW_S = 60.0
"""SEC-54: heartbeats and leave calls one person may make per window (the browser makes about 4 a minute per
open conversation plus one per click and per typing start/stop). Past it the call is acknowledged and ignored:
without a ceiling, flipping ``viewing``/``replying`` would make every colleague's Inbox reload several times a
second."""


@dataclass(frozen=True)
class PresenceEntry:
    user_id: UUID
    state: PresenceState


class PresenceStore(Protocol):
    async def touch(self, conversation_id: UUID, user_id: UUID, state: PresenceState) -> bool:
        """Record a heartbeat. ``True`` when the person was not there (or had another state) before."""
        ...

    async def leave(self, conversation_id: UUID, user_id: UUID) -> bool:
        """Remove the person. ``True`` when they were there."""
        ...

    async def viewers(self, conversation_ids: Sequence[UUID]) -> dict[UUID, list[PresenceEntry]]:
        """The live entries of each conversation (users who are not expired). One round trip."""
        ...


class InMemoryPresenceStore:
    """Tests: the clock is injected so the TTL is exercised without sleeping."""

    def __init__(self, *, ttl_s: float = PRESENCE_TTL_S, clock: Callable[[], float] = time.time) -> None:
        self._ttl = ttl_s
        self._clock = clock
        self._rows: dict[UUID, dict[UUID, tuple[PresenceState, float]]] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("presence store is down")

    async def touch(self, conversation_id: UUID, user_id: UUID, state: PresenceState) -> bool:
        self._check()
        now = self._clock()
        rows = self._rows.setdefault(conversation_id, {})
        prior = rows.get(user_id)
        changed = prior is None or prior[1] <= now or prior[0] is not state
        rows[user_id] = (state, now + self._ttl)
        return changed

    async def leave(self, conversation_id: UUID, user_id: UUID) -> bool:
        self._check()
        prior = self._rows.get(conversation_id, {}).pop(user_id, None)
        return prior is not None and prior[1] > self._clock()

    async def viewers(self, conversation_ids: Sequence[UUID]) -> dict[UUID, list[PresenceEntry]]:
        self._check()
        now = self._clock()
        out: dict[UUID, list[PresenceEntry]] = {}
        for conversation_id in conversation_ids:
            live = [
                PresenceEntry(user_id, state)
                for user_id, (state, expires) in self._rows.get(conversation_id, {}).items()
                if expires > now
            ]
            if live:
                out[conversation_id] = sorted(live, key=lambda e: str(e.user_id))
        return out


class RedisPresenceStore:
    """One sorted set per conversation: member ``<user_id>:<state>``, score = expiry in epoch milliseconds."""

    def __init__(
        self, client: Any, *, ttl_s: float = PRESENCE_TTL_S, clock: Callable[[], float] = time.time
    ) -> None:
        self._client = client
        self._ttl_ms = int(ttl_s * 1000)
        self._clock = clock

    @staticmethod
    def _key(conversation_id: UUID) -> str:
        return f"{KEY_PREFIX}:{conversation_id}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    async def touch(self, conversation_id: UUID, user_id: UUID, state: PresenceState) -> bool:
        key = self._key(conversation_id)
        now_ms = self._now_ms()
        member = f"{user_id}:{state.value}"
        others = [f"{user_id}:{s.value}" for s in PresenceState if s is not state]
        prior: Any = await self._client.zscore(key, member)
        changed = prior is None or int(prior) <= now_ms
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.zrem(key, *others)
            pipe.zadd(key, {member: now_ms + self._ttl_ms})
            pipe.zremrangebyscore(key, "-inf", now_ms)
            pipe.pexpire(key, self._ttl_ms * 2)
            await pipe.execute()
        return changed

    async def leave(self, conversation_id: UUID, user_id: UUID) -> bool:
        key = self._key(conversation_id)
        members = [f"{user_id}:{s.value}" for s in PresenceState]
        removed: Any = await self._client.zrem(key, *members)
        return int(removed) > 0

    async def viewers(self, conversation_ids: Sequence[UUID]) -> dict[UUID, list[PresenceEntry]]:
        if not conversation_ids:
            return {}
        now_ms = self._now_ms()
        async with self._client.pipeline(transaction=False) as pipe:
            for conversation_id in conversation_ids:
                pipe.zrangebyscore(self._key(conversation_id), f"({now_ms}", "+inf")
            rows: list[Any] = await pipe.execute()
        out: dict[UUID, list[PresenceEntry]] = {}
        for conversation_id, members in zip(conversation_ids, rows, strict=True):
            entries = [entry for member in members if (entry := _parse_member(str(member))) is not None]
            if entries:
                out[conversation_id] = sorted(entries, key=lambda e: str(e.user_id))
        return out


def _parse_member(member: str) -> PresenceEntry | None:
    user, _, state = member.rpartition(":")
    try:
        return PresenceEntry(UUID(user), PresenceState(state))
    except ValueError:
        return None


class PresenceService:
    """What the routes use. Never raises for a store failure."""

    def __init__(
        self,
        store: PresenceStore,
        *,
        ttl_s: float = PRESENCE_TTL_S,
        expiry_slack_s: float = EXPIRY_NOTICE_SLACK_S,
        max_ops: int = MAX_OPS_PER_WINDOW,
        window_s: float = WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._expiry_delay_s = ttl_s + expiry_slack_s
        self._timers: dict[tuple[UUID, UUID], asyncio.TimerHandle] = {}
        self._max_ops = max_ops
        self._window_s = window_s
        self._clock = clock
        self._recent: defaultdict[UUID, deque[float]] = defaultdict(deque)

    def _allow(self, user_id: UUID) -> bool:
        """Sliding window per person; the dict holds only people with a call inside the window."""
        now = self._clock()
        recent = self._recent[user_id]
        while recent and now - recent[0] >= self._window_s:
            recent.popleft()
        if len(recent) >= self._max_ops:
            return False
        recent.append(now)
        return True

    async def beat(self, conversation_id: UUID, user_id: UUID, state: PresenceState) -> None:
        if not self._allow(user_id):
            return
        try:
            changed = await self._store.touch(conversation_id, user_id, state)
        except Exception as err:
            log.warning("presence heartbeat not stored", err=err)
            return
        self._arm_expiry_notice(conversation_id, user_id)
        if changed:
            emit_live(LiveEventType.PRESENCE_CHANGED, conversation_id)

    async def leave(self, conversation_id: UUID, user_id: UUID) -> None:
        if not self._allow(user_id):
            return
        self._disarm(conversation_id, user_id)
        try:
            was_there = await self._store.leave(conversation_id, user_id)
        except Exception as err:
            log.warning("presence leave not stored", err=err)
            return
        if was_there:
            emit_live(LiveEventType.PRESENCE_CHANGED, conversation_id)

    async def viewers(self, conversation_ids: Sequence[UUID]) -> dict[UUID, list[PresenceEntry]]:
        """Empty when the store is down: the Inbox works without presence."""
        try:
            return await self._store.viewers(conversation_ids)
        except Exception as err:
            log.warning("presence not readable", err=err)
            return {}

    def _arm_expiry_notice(self, conversation_id: UUID, user_id: UUID) -> None:
        """One timer per (conversation, person), replaced by every heartbeat: it fires only once the
        heartbeats
        stopped, so the colleagues' screens drop a closed tab without waiting for another event."""
        self._disarm(conversation_id, user_id)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._timers[(conversation_id, user_id)] = loop.call_later(
            self._expiry_delay_s, self._expired, conversation_id, user_id
        )

    def _expired(self, conversation_id: UUID, user_id: UUID) -> None:
        self._timers.pop((conversation_id, user_id), None)
        emit_live(LiveEventType.PRESENCE_CHANGED, conversation_id)

    def _disarm(self, conversation_id: UUID, user_id: UUID) -> None:
        handle = self._timers.pop((conversation_id, user_id), None)
        if handle is not None:
            handle.cancel()

    def aclose(self) -> None:
        for handle in self._timers.values():
            handle.cancel()
        self._timers.clear()
