"""Where cases and their log are kept: ``agent_rt.agent_case`` and ``agent_rt.agent_case_event``
(Postgres), or process memory (tests, a service without a database).

A save only lands on the version it read (``version``): two runs of one case never both write, the one
that lost drops its result. Opening is idempotent per (kind, key): while a case is live, opening it again
returns it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Final, Protocol, cast

from sqlalchemy import text as sql

from agent_app.storage import AgentDatabase, retrying
from agentcore.cases import LIVE, CaseRecord

MAX_DETAIL_CHARS: Final = 1900
LIST_LIMIT: Final = 100

EventKind = str
"""``opened``, ``woken``, ``blocked``, ``sent``, ``decision``, ``stopped``, ``error``, ``lost``."""


class CaseStore(Protocol):
    async def open(self, plugin: str, record: CaseRecord) -> tuple[CaseRecord, bool]:
        """Stores a new case; returns it with its id and True, or the live one of the same kind and key and
        False."""
        ...

    async def get(self, case_id: int) -> CaseRecord | None: ...

    async def live(self, kind: str, key: str) -> CaseRecord | None: ...

    async def waiting_in_chat(self, channel: str, conversation_id: str) -> list[CaseRecord]: ...

    async def due(self, now: datetime, limit: int) -> list[CaseRecord]:
        """Cases ready to run: open ones, and waiting ones whose ``wake_at`` came, earliest first."""
        ...

    async def save(self, record: CaseRecord) -> CaseRecord | None:
        """Writes the record if it still has the version it was read at; the saved one, or None (lost)."""
        ...

    async def log(
        self, case_id: int, kind: EventKind, node: str | None, detail: dict[str, Any], at: datetime
    ) -> None: ...

    async def sent_since(self, channel: str, user_id: str, since: datetime) -> int:
        """Messages every case together sent this person since ``since``."""
        ...

    async def set_pending(
        self, case_id: int, turn: int, channel: str, conversation_id: str, decision: dict[str, Any]
    ) -> bool:
        """Keeps the decision a steering tool gave in ``turn`` of a live case of that chat; False when there
        is no such case or it has moved past that turn. Never changes ``version``: the engine holds the record
        it read before the turn."""
        ...

    async def pending(self, case_id: int, turn: int) -> dict[str, Any] | None:
        """The decision kept for ``turn``, or None."""
        ...

    async def list(self, status: str | None = None, limit: int = LIST_LIMIT) -> list[CaseRecord]: ...

    async def events(self, case_id: int, limit: int = LIST_LIMIT) -> list[dict[str, Any]]: ...


def _detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Short enough for the table's limit: a long value is cut, never the whole entry dropped."""
    text = json.dumps(detail, ensure_ascii=False, default=str)
    if len(text) <= MAX_DETAIL_CHARS:
        return detail
    return {"cut": text[:MAX_DETAIL_CHARS]}


class InMemoryCaseStore:
    def __init__(self) -> None:
        self._rows: dict[int, tuple[str, CaseRecord]] = {}
        self._events: dict[int, list[dict[str, Any]]] = {}
        self._pending: dict[int, dict[str, Any]] = {}
        self._next = 1

    async def open(self, plugin: str, record: CaseRecord) -> tuple[CaseRecord, bool]:
        found = await self.live(record.kind, record.key)
        if found is not None:
            return found, False
        stored = replace(record, id=self._next, version=0)
        self._next += 1
        self._rows[stored.id] = (plugin, stored)
        return stored, True

    async def get(self, case_id: int) -> CaseRecord | None:
        row = self._rows.get(case_id)
        return None if row is None else row[1]

    async def live(self, kind: str, key: str) -> CaseRecord | None:
        return next(
            (r for _, r in self._rows.values() if r.kind == kind and r.key == key and r.status in LIVE), None
        )

    async def waiting_in_chat(self, channel: str, conversation_id: str) -> list[CaseRecord]:
        return [
            r
            for _, r in self._rows.values()
            if r.status == "waiting" and r.channel == channel and r.conversation_id == conversation_id
        ]

    async def due(self, now: datetime, limit: int) -> list[CaseRecord]:
        found = [
            r
            for _, r in self._rows.values()
            if r.status == "open" or (r.status == "waiting" and r.wake_at is not None and r.wake_at <= now)
        ]
        return sorted(found, key=lambda r: r.wake_at or r.updated_at)[:limit]

    async def save(self, record: CaseRecord) -> CaseRecord | None:
        plugin, current = self._rows[record.id]
        if current.version != record.version:
            return None
        saved = replace(record, version=record.version + 1)
        self._rows[record.id] = (plugin, saved)
        return saved

    async def log(
        self, case_id: int, kind: EventKind, node: str | None, detail: dict[str, Any], at: datetime
    ) -> None:
        events = self._events.setdefault(case_id, [])
        events.append(
            {
                "seq": len(events) + 1,
                "at": at.isoformat(),
                "kind": kind,
                "node": node,
                "detail": _detail(detail),
            }
        )

    async def sent_since(self, channel: str, user_id: str, since: datetime) -> int:
        cases = {i for i, (_, r) in self._rows.items() if r.channel == channel and r.user_id == user_id}
        return sum(
            1
            for case_id in cases
            for e in self._events.get(case_id, [])
            if e["kind"] == "sent" and datetime.fromisoformat(e["at"]) >= since
        )

    async def set_pending(
        self, case_id: int, turn: int, channel: str, conversation_id: str, decision: dict[str, Any]
    ) -> bool:
        row = self._rows.get(case_id)
        if row is None:
            return False
        record = row[1]
        if (record.turns, record.channel, record.conversation_id) != (turn, channel, conversation_id):
            return False
        if record.status not in LIVE:
            return False
        self._pending[case_id] = {"turn": turn, "decision": decision}
        return True

    async def pending(self, case_id: int, turn: int) -> dict[str, Any] | None:
        found = self._pending.get(case_id)
        return found["decision"] if found is not None and found["turn"] == turn else None

    async def list(self, status: str | None = None, limit: int = LIST_LIMIT) -> list[CaseRecord]:
        rows = [r for _, r in self._rows.values() if status is None or r.status == status]
        return sorted(rows, key=lambda r: r.updated_at, reverse=True)[:limit]

    async def events(self, case_id: int, limit: int = LIST_LIMIT) -> list[dict[str, Any]]:
        return self._events.get(case_id, [])[-limit:]


_OPEN = sql(
    "INSERT INTO agent_rt.agent_case (tenant_id, agent, plugin, kind, key, channel, conversation_id, "
    "user_id, "
    "session_id, goal, status, node, state, deadline, created_at, updated_at) VALUES (:tenant_id, :agent, "
    ":plugin, :kind, :key, :channel, :conversation_id, :user_id, :session_id, :goal, :status, :node, "
    "CAST(:state AS jsonb), :deadline, :created_at, :updated_at) "
    "ON CONFLICT (tenant_id, agent, plugin, kind, key) WHERE status IN ('open', 'waiting', 'needs_human') "
    "DO NOTHING RETURNING "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
)
_GET = sql(
    "SELECT "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
    " FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_LIVE = sql(
    "SELECT "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
    " FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND kind = :kind AND key = :key "
    "AND status IN ('open', 'waiting', 'needs_human')"
)
_WAITING_IN_CHAT = sql(
    "SELECT "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
    " FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent AND channel = :channel "
    "AND conversation_id = :conversation_id AND status = 'waiting'"
)
_DUE = sql(
    "SELECT "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
    " FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent AND (status = 'open' "
    "OR (status = 'waiting' AND wake_at <= :now)) ORDER BY COALESCE(wake_at, updated_at) LIMIT :limit"
)
_SAVE = sql(
    "UPDATE agent_rt.agent_case SET goal = :goal, status = :status, node = :node, "
    "state = CAST(:state AS jsonb), wait_for = :wait_for, wake_at = :wake_at, turns = :turns, "
    "proactive_sent = :proactive_sent, end_reason = :end_reason, closed_at = :closed_at, "
    "updated_at = :updated_at, version = version + 1 WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND id = :id AND version = :version "
    "RETURNING version"
)
# shortcut: seq is max + 1 without a lock; one engine per agent writes the log, two would clash on the key.
_LOG = sql(
    "INSERT INTO agent_rt.agent_case_event (case_id, seq, at, kind, node, detail) "
    "SELECT :case_id, COALESCE(MAX(seq), 0) + 1, :at, :kind, :node, CAST(:detail AS jsonb) "
    "FROM agent_rt.agent_case_event WHERE case_id = :case_id"
)
_SENT_SINCE = sql(
    "SELECT count(*) FROM agent_rt.agent_case_event e JOIN agent_rt.agent_case c ON c.id = e.case_id "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.channel = :channel AND c.user_id = :user_id "
    "AND e.kind = 'sent' AND e.at >= :since"
)
_SET_PENDING = sql(
    "UPDATE agent_rt.agent_case SET pending = CAST(:pending AS jsonb) "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id AND turns = :turn "
    "AND channel = :channel AND conversation_id = :conversation_id "
    "AND status IN ('open', 'waiting', 'needs_human') RETURNING id"
)
_PENDING = sql(
    "SELECT pending FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_LIST = sql(
    "SELECT "
    "id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state, deadline, "
    "created_at, updated_at, wait_for, wake_at, turns, proactive_sent, end_reason, closed_at, version"
    " FROM agent_rt.agent_case WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND (CAST(:status AS text) IS NULL OR status = :status) ORDER BY updated_at DESC LIMIT :limit"
)
_EVENTS = sql(
    "SELECT e.seq, e.at, e.kind, e.node, e.detail FROM agent_rt.agent_case_event e "
    "JOIN agent_rt.agent_case c ON c.id = e.case_id "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND e.case_id = :id ORDER BY e.seq DESC LIMIT :limit"
)


def _record(row: Any) -> CaseRecord:
    return CaseRecord(
        id=row.id,
        kind=row.kind,
        key=row.key,
        channel=row.channel,
        conversation_id=row.conversation_id,
        user_id=row.user_id,
        session_id=row.session_id,
        goal=row.goal,
        status=row.status,
        node=row.node,
        state=dict(row.state),
        deadline=row.deadline,
        created_at=row.created_at,
        updated_at=row.updated_at,
        wait_for=row.wait_for,
        wake_at=row.wake_at,
        turns=row.turns,
        proactive_sent=row.proactive_sent,
        end_reason=row.end_reason,
        closed_at=row.closed_at,
        version=row.version,
    )


class PostgresCaseStore:
    def __init__(self, db: AgentDatabase, *, tenant_id: str, agent: str) -> None:
        self._engine = db.engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def _one(self, what: str, query: Any, params: dict[str, Any]) -> CaseRecord | None:
        async def work() -> CaseRecord | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(query, {**self._scope, **params})).one_or_none()
            return None if row is None else _record(row)

        return await retrying(what, work)

    async def _many(self, what: str, query: Any, params: dict[str, Any]) -> list[CaseRecord]:
        async def work() -> list[CaseRecord]:
            async with self._engine.connect() as conn:
                return [_record(r) for r in (await conn.execute(query, {**self._scope, **params})).all()]

        return await retrying(what, work)

    async def open(self, plugin: str, record: CaseRecord) -> tuple[CaseRecord, bool]:
        params = {
            **self._scope,
            "plugin": plugin,
            "kind": record.kind,
            "key": record.key,
            "channel": record.channel,
            "conversation_id": record.conversation_id,
            "user_id": record.user_id,
            "session_id": record.session_id,
            "goal": record.goal,
            "status": record.status,
            "node": record.node,
            "state": json.dumps(dict(record.state), ensure_ascii=False),
            "deadline": record.deadline,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

        async def work() -> CaseRecord | None:
            async with self._engine.begin() as conn:
                row = (await conn.execute(_OPEN, params)).one_or_none()
            return None if row is None else _record(row)

        created = await retrying("open a case", work)
        if created is not None:
            return created, True
        found = await self.live(record.kind, record.key)
        if found is None:  # closed between the insert and the read: open it again
            return await self.open(plugin, record)
        return found, False

    async def get(self, case_id: int) -> CaseRecord | None:
        return await self._one("load a case", _GET, {"id": case_id})

    async def live(self, kind: str, key: str) -> CaseRecord | None:
        return await self._one("find a live case", _LIVE, {"kind": kind, "key": key})

    async def waiting_in_chat(self, channel: str, conversation_id: str) -> list[CaseRecord]:
        params = {"channel": channel, "conversation_id": conversation_id}
        return await self._many("find the cases of a chat", _WAITING_IN_CHAT, params)

    async def due(self, now: datetime, limit: int) -> list[CaseRecord]:
        return await self._many("find due cases", _DUE, {"now": now, "limit": limit})

    async def save(self, record: CaseRecord) -> CaseRecord | None:
        params = {
            **self._scope,
            "id": record.id,
            "version": record.version,
            "goal": record.goal,
            "status": record.status,
            "node": record.node,
            "state": json.dumps(dict(record.state), ensure_ascii=False),
            "wait_for": record.wait_for,
            "wake_at": record.wake_at,
            "turns": record.turns,
            "proactive_sent": record.proactive_sent,
            "end_reason": record.end_reason,
            "closed_at": record.closed_at,
            "updated_at": record.updated_at,
        }

        async def work() -> int | None:
            async with self._engine.begin() as conn:
                return (await conn.execute(_SAVE, params)).scalar_one_or_none()

        version = await retrying("save a case", work)
        return None if version is None else replace(record, version=version)

    async def log(
        self, case_id: int, kind: EventKind, node: str | None, detail: dict[str, Any], at: datetime
    ) -> None:
        params = {
            "case_id": case_id,
            "kind": kind,
            "node": node,
            "at": at,
            "detail": json.dumps(_detail(detail), ensure_ascii=False, default=str),
        }

        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_LOG, params)

        await retrying("log a case event", work)

    async def sent_since(self, channel: str, user_id: str, since: datetime) -> int:
        params = {**self._scope, "channel": channel, "user_id": user_id, "since": since}

        async def work() -> int:
            async with self._engine.connect() as conn:
                return int((await conn.execute(_SENT_SINCE, params)).scalar_one())

        return await retrying("count messages sent to a person", work)

    async def set_pending(
        self, case_id: int, turn: int, channel: str, conversation_id: str, decision: dict[str, Any]
    ) -> bool:
        params = {
            **self._scope,
            "id": case_id,
            "turn": turn,
            "channel": channel,
            "conversation_id": conversation_id,
            "pending": json.dumps({"turn": turn, "decision": decision}, ensure_ascii=False),
        }

        async def work() -> bool:
            async with self._engine.begin() as conn:
                return (await conn.execute(_SET_PENDING, params)).one_or_none() is not None

        return await retrying("keep a case's decision", work)

    async def pending(self, case_id: int, turn: int) -> dict[str, Any] | None:
        params = {**self._scope, "id": case_id}

        async def work() -> dict[str, Any] | None:
            async with self._engine.connect() as conn:
                found: Any = (await conn.execute(_PENDING, params)).scalar_one_or_none()
            if not isinstance(found, dict):
                return None
            kept = cast(dict[str, Any], found)
            decision: Any = kept.get("decision")
            if kept.get("turn") != turn or not isinstance(decision, dict):
                return None
            return dict(cast(dict[str, Any], decision))

        return await retrying("read a case's decision", work)

    async def list(self, status: str | None = None, limit: int = LIST_LIMIT) -> list[CaseRecord]:
        return await self._many("list cases", _LIST, {"status": status, "limit": limit})

    async def events(self, case_id: int, limit: int = LIST_LIMIT) -> list[dict[str, Any]]:
        params = {**self._scope, "id": case_id, "limit": limit}

        async def work() -> list[dict[str, Any]]:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(_EVENTS, params)).all()
            return [
                {
                    "seq": r.seq,
                    "at": r.at.isoformat(),
                    "kind": r.kind,
                    "node": r.node,
                    "detail": dict(r.detail),
                }
                for r in reversed(rows)
            ]

        return await retrying("read a case's log", work)
