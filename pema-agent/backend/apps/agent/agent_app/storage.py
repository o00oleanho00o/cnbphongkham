"""Postgres storage of schema ``agent_rt``: the agent's notes and its own skills, sessions with their
messages, and the turn trace. Every statement is parameterised; the schema comes from ``apps/agent/alembic``.

A dropped connection is retried once, and only where a retry is harmless: reads, upserts, appends carrying a
unique id, and the notes' version-checked write, whose unknown outcome is settled by reading it back.

On Windows the async psycopg driver needs a selector event loop (see ``agent_app.cli``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import uuid4

from sqlalchemy import text as sql
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from agentcore import CompactionRecord, Message, StoredPrompt, TraceEvent, TurnTrace, Usage
from agentcore.memory import MemoryKey, StoredNotes
from agentcore.skills import Skill

RETRY_DELAY_S: Final = 0.2

logger = logging.getLogger(__name__)

# Fail fast on a dead connection; keepalives stop port proxies dropping idle ones (seen on Docker Desktop).
CONNECT_ARGS: Final = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 20,
    "keepalives_interval": 5,
    "keepalives_count": 3,
}


class AgentDatabase:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, pool_pre_ping=True, pool_size=5, connect_args=dict(CONNECT_ARGS)
        )

    async def dispose(self) -> None:
        await self.engine.dispose()


def is_connection_error(err: BaseException) -> bool:
    if isinstance(err, OperationalError | InterfaceError):
        return True
    return isinstance(err, DBAPIError) and err.connection_invalidated


async def retrying[T](what: str, work: Callable[[], Awaitable[T]]) -> T:
    """Runs ``work`` again once after a connection error; ``work`` must be safe to repeat."""
    try:
        return await work()
    except DBAPIError as err:
        if not is_connection_error(err):
            raise
        logger.warning("%s: connection error (%s); retrying once", what, type(err.orig).__name__)
    await asyncio.sleep(RETRY_DELAY_S)
    return await work()


_LOAD_NOTES = sql(
    "SELECT content, version FROM agent_rt.agent_memory "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND target = :target AND user_id = :user_id"
)
_INSERT_NOTES = sql(
    "INSERT INTO agent_rt.agent_memory (tenant_id, agent, target, user_id, content, version) "
    "VALUES (:tenant_id, :agent, :target, :user_id, :content, 1) ON CONFLICT DO NOTHING"
)
_UPDATE_NOTES = sql(
    "UPDATE agent_rt.agent_memory SET content = :content, version = version + 1, updated_at = now() "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND target = :target AND user_id = :user_id "
    "AND version = :version"
)


def _key_params(key: MemoryKey) -> dict[str, str]:
    return {"tenant_id": key.tenant_id, "agent": key.agent, "target": key.target, "user_id": key.user_id}


class PostgresMemoryBackend:
    def __init__(self, db: AgentDatabase) -> None:
        self._engine = db.engine

    async def load(self, key: MemoryKey) -> StoredNotes:
        async def work() -> StoredNotes:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_LOAD_NOTES, _key_params(key))).one_or_none()
            return StoredNotes() if row is None else StoredNotes(text=row.content, version=row.version)

        return await retrying("load notes", work)

    async def save(self, key: MemoryKey, text: str, expected_version: int) -> bool:
        params = {**_key_params(key), "content": text, "version": expected_version}
        statement = _INSERT_NOTES if expected_version == 0 else _UPDATE_NOTES
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(statement, params)
            return result.rowcount == 1
        except DBAPIError as err:
            if not is_connection_error(err):
                raise
            logger.warning("save notes: connection error (%s); reading back", type(err.orig).__name__)
        # The write may or may not have committed: it did if the stored text is ours at the next version.
        # Otherwise the service reads again and retries its edit.
        await asyncio.sleep(RETRY_DELAY_S)
        stored = await self.load(key)
        return stored == StoredNotes(text=text, version=expected_version + 1)


_LIST_SKILLS = sql(
    "SELECT name, description, body FROM agent_rt.agent_skill "
    "WHERE tenant_id = :tenant_id AND agent = :agent ORDER BY name"
)
_GET_SKILL = sql(
    "SELECT name, description, body FROM agent_rt.agent_skill "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND name = :name"
)
_PUT_SKILL = sql(
    "INSERT INTO agent_rt.agent_skill (tenant_id, agent, name, description, body) "
    "VALUES (:tenant_id, :agent, :name, :description, :body) "
    "ON CONFLICT (tenant_id, agent, name) DO UPDATE SET description = EXCLUDED.description, "
    "body = EXCLUDED.body, version = agent_rt.agent_skill.version + 1, updated_at = now()"
)


class PostgresSkillStore:
    def __init__(self, db: AgentDatabase) -> None:
        self._engine = db.engine

    async def list(self, tenant_id: str, agent: str) -> list[Skill]:
        async def work() -> list[Skill]:
            async with self._engine.connect() as conn:
                rows = await conn.execute(_LIST_SKILLS, {"tenant_id": tenant_id, "agent": agent})
                return [Skill(name=r.name, description=r.description, body=r.body) for r in rows]

        return await retrying("list skills", work)

    async def get(self, tenant_id: str, agent: str, name: str) -> Skill | None:
        async def work() -> Skill | None:
            params = {"tenant_id": tenant_id, "agent": agent, "name": name}
            async with self._engine.connect() as conn:
                row = (await conn.execute(_GET_SKILL, params)).one_or_none()
            return None if row is None else Skill(name=row.name, description=row.description, body=row.body)

        return await retrying("get skill", work)

    async def put(self, tenant_id: str, agent: str, skill: Skill) -> None:
        params = {
            "tenant_id": tenant_id,
            "agent": agent,
            "name": skill.name,
            "description": skill.description,
            "body": skill.body,
        }

        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(_PUT_SKILL, params)

        await retrying("put skill", work)


class SessionOwnerError(ValueError):
    """The session id belongs to another agent."""


@dataclass(frozen=True, slots=True)
class SessionInfo:
    session_id: str
    agent: str
    channel: str | None
    user_id: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime


_OPEN_SESSION = sql(
    "INSERT INTO agent_rt.agent_session (tenant_id, session_id, agent, channel, user_id) "
    "VALUES (:tenant_id, :session_id, :agent, :channel, :user_id) ON CONFLICT DO NOTHING"
)
_GET_SESSION = sql(
    "SELECT session_id, agent, channel, user_id, message_count, created_at, updated_at "
    "FROM agent_rt.agent_session WHERE tenant_id = :tenant_id AND session_id = :session_id"
)
_RECENT_SESSIONS = sql(
    "SELECT session_id, agent, channel, user_id, message_count, created_at, updated_at "
    "FROM agent_rt.agent_session WHERE tenant_id = :tenant_id AND agent = :agent "
    "ORDER BY updated_at DESC LIMIT :limit"
)
_LOAD_MESSAGES = sql(
    "SELECT m.message FROM agent_rt.agent_message m JOIN agent_rt.agent_session s "
    "USING (tenant_id, session_id) "
    "WHERE m.tenant_id = :tenant_id AND m.session_id = :session_id AND s.agent = :agent ORDER BY m.seq"
)
_MESSAGE_SAVED = sql("SELECT 1 FROM agent_rt.agent_message WHERE uid = :uid")
# The upsert locks the session row, so concurrent appends to one session get consecutive numbers.
_NEXT_SEQ = sql(
    "INSERT INTO agent_rt.agent_session (tenant_id, session_id, agent, message_count) "
    "VALUES (:tenant_id, :session_id, :agent, 1) "
    "ON CONFLICT (tenant_id, session_id) DO UPDATE SET "
    "message_count = agent_rt.agent_session.message_count + 1, updated_at = now() "
    "WHERE agent_rt.agent_session.agent = EXCLUDED.agent RETURNING message_count"
)
_INSERT_MESSAGE = sql(
    "INSERT INTO agent_rt.agent_message (tenant_id, session_id, seq, uid, message) "
    "VALUES (:tenant_id, :session_id, :seq, :uid, CAST(:message AS jsonb))"
)
_LOAD_PROMPT = sql(
    "SELECT prompt_text, prompt_fingerprint FROM agent_rt.agent_session "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent"
)
_SAVE_PROMPT = sql(
    "INSERT INTO agent_rt.agent_session (tenant_id, session_id, agent, prompt_text, prompt_fingerprint) "
    "VALUES (:tenant_id, :session_id, :agent, :text, :fingerprint) "
    "ON CONFLICT (tenant_id, session_id) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, "
    "prompt_fingerprint = EXCLUDED.prompt_fingerprint, updated_at = now() "
    "WHERE agent_rt.agent_session.agent = EXCLUDED.agent RETURNING 1"
)
_LOAD_COMPACTION = sql(
    "SELECT summary, first_kept FROM agent_rt.agent_session "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent"
)
_SAVE_COMPACTION = sql(
    "UPDATE agent_rt.agent_session SET summary = :summary, first_kept = :first_kept, updated_at = now() "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent"
)


class PostgresSessionStore:
    """Sessions of one agent; a session id another agent uses is refused, never read."""

    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    def _key(self, tenant_id: str, session_id: str) -> dict[str, str]:
        return {"tenant_id": tenant_id, "session_id": session_id, "agent": self._agent}

    async def open_session(
        self, tenant_id: str, session_id: str, *, channel: str | None, user_id: str | None
    ) -> SessionInfo:
        """Creates the session or finds it; channel and user are kept from its creation."""

        async def work() -> SessionInfo:
            params = {**self._key(tenant_id, session_id), "channel": channel, "user_id": user_id}
            async with self._engine.begin() as conn:
                await conn.execute(_OPEN_SESSION, params)
                row = (await conn.execute(_GET_SESSION, params)).one()
            return _session_info(row)

        info = await retrying("open session", work)
        if info.agent != self._agent:
            raise SessionOwnerError(f"session {session_id} belongs to agent {info.agent}")
        return info

    async def list_sessions(self, tenant_id: str, *, limit: int = 10) -> list[SessionInfo]:
        async def work() -> list[SessionInfo]:
            params = {"tenant_id": tenant_id, "agent": self._agent, "limit": limit}
            async with self._engine.connect() as conn:
                return [_session_info(row) for row in await conn.execute(_RECENT_SESSIONS, params)]

        return await retrying("list sessions", work)

    async def load(self, tenant_id: str, session_id: str) -> list[Message]:
        async def work() -> list[Message]:
            async with self._engine.connect() as conn:
                rows = await conn.execute(_LOAD_MESSAGES, self._key(tenant_id, session_id))
                return [Message.model_validate(row.message) for row in rows]

        return await retrying("load messages", work)

    async def append(self, tenant_id: str, session_id: str, message: Message) -> None:
        key = self._key(tenant_id, session_id)
        uid = str(uuid4())
        document = _jsonb_text(message)

        async def work() -> None:
            async with self._engine.begin() as conn:
                if (await conn.execute(_MESSAGE_SAVED, {"uid": uid})).first() is not None:
                    return  # the first attempt committed before its connection dropped
                seq = (await conn.execute(_NEXT_SEQ, key)).scalar_one_or_none()
                if seq is None:
                    raise SessionOwnerError(f"session {session_id} belongs to another agent")
                await conn.execute(_INSERT_MESSAGE, {**key, "seq": seq, "uid": uid, "message": document})

        await retrying("append message", work)

    async def load_prompt(self, tenant_id: str, session_id: str) -> StoredPrompt | None:
        async def work() -> StoredPrompt | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_LOAD_PROMPT, self._key(tenant_id, session_id))).one_or_none()
            if row is None or row.prompt_text is None:
                return None
            return StoredPrompt(text=row.prompt_text, fingerprint=row.prompt_fingerprint)

        return await retrying("load prompt", work)

    async def save_prompt(self, tenant_id: str, session_id: str, prompt: StoredPrompt) -> None:
        params = {**self._key(tenant_id, session_id), "text": prompt.text, "fingerprint": prompt.fingerprint}

        async def work() -> None:
            async with self._engine.begin() as conn:
                if (await conn.execute(_SAVE_PROMPT, params)).first() is None:
                    raise SessionOwnerError(f"session {session_id} belongs to another agent")

        await retrying("save prompt", work)

    async def load_compaction(self, tenant_id: str, session_id: str) -> CompactionRecord | None:
        async def work() -> CompactionRecord | None:
            async with self._engine.connect() as conn:
                row = (await conn.execute(_LOAD_COMPACTION, self._key(tenant_id, session_id))).one_or_none()
            if row is None or row.summary is None:
                return None
            return CompactionRecord(summary=row.summary, first_kept=row.first_kept)

        return await retrying("load compaction", work)

    async def save_compaction(self, tenant_id: str, session_id: str, record: CompactionRecord) -> None:
        params = {
            **self._key(tenant_id, session_id),
            "summary": record.summary,
            "first_kept": record.first_kept,
        }

        async def work() -> None:
            async with self._engine.begin() as conn:
                if (await conn.execute(_SAVE_COMPACTION, params)).rowcount != 1:
                    raise SessionOwnerError(f"session {session_id} is not a session of this agent")

        await retrying("save compaction", work)


def _session_info(row: Any) -> SessionInfo:
    return SessionInfo(
        session_id=row.session_id,
        agent=row.agent,
        channel=row.channel,
        user_id=row.user_id,
        message_count=row.message_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _jsonb_text(message: Message) -> str:
    """Postgres jsonb cannot hold the NUL character; it becomes U+FFFD (tool output may contain it)."""
    data = message.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False)
    return text if "\\u0000" not in text else json.dumps(_without_nul(data), ensure_ascii=False)


def _without_nul(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "\ufffd")
    if isinstance(value, dict):
        return {k: _without_nul(v) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [_without_nul(v) for v in cast(list[Any], value)]
    return value


_INSERT_TURN = sql(
    "INSERT INTO agent_rt.agent_turn (turn_id, tenant_id, session_id, agent, model, channel, user_id, "
    "started_at, duration_ms, stop, steps, error_kind, compactions, input_tokens, output_tokens, "
    "cache_read_tokens, cache_write_tokens, reasoning_tokens) VALUES (:turn_id, :tenant_id, :session_id, "
    ":agent, :model, :channel, :user_id, :started_at, :duration_ms, :stop, :steps, :error_kind, "
    ":compactions, :input_tokens, :output_tokens, :cache_read_tokens, :cache_write_tokens, "
    ":reasoning_tokens) ON CONFLICT (turn_id) DO NOTHING"
)
_INSERT_EVENT = sql(
    "INSERT INTO agent_rt.agent_turn_event (turn_id, seq, kind, step, name, duration_ms, is_error, detail) "
    "VALUES (:turn_id, :seq, :kind, :step, :name, :duration_ms, :is_error, CAST(:detail AS jsonb))"
)
_LAST_TURN = sql(
    "SELECT turn_id, tenant_id, session_id, channel, user_id, started_at, duration_ms, stop, steps, "
    "error_kind, compactions, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
    "reasoning_tokens FROM agent_rt.agent_turn "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent "
    "ORDER BY started_at DESC LIMIT 1"
)
_TURN_EVENTS = sql(
    "SELECT kind, step, name, duration_ms, is_error, detail FROM agent_rt.agent_turn_event "
    "WHERE turn_id = :turn_id ORDER BY seq"
)


class PostgresTracer:
    """One transaction per turn; a turn written twice (a retry) is kept once."""

    def __init__(self, db: AgentDatabase, *, agent: str, model: str | Callable[[], str]) -> None:
        """``model`` names the model of each traced turn; a callable is asked at each turn, because an admin
        can change the model while the service runs."""
        self._engine = db.engine
        self._agent = agent
        self._model = model

    async def record(self, trace: TurnTrace) -> None:
        turn = {
            "turn_id": trace.turn_id,
            "tenant_id": trace.tenant_id,
            "session_id": trace.session_id,
            "agent": self._agent,
            "model": self._model if isinstance(self._model, str) else self._model(),
            "channel": trace.channel,
            "user_id": trace.user_id,
            "started_at": trace.started_at,
            "duration_ms": _ms(trace.duration_s),
            "stop": trace.stop,
            "steps": trace.steps,
            "error_kind": trace.error_kind,
            "compactions": trace.compactions,
            **trace.usage.model_dump(),
        }
        events = [
            {
                "turn_id": trace.turn_id,
                "seq": seq,
                "kind": event.kind,
                "step": event.step,
                "name": event.name,
                "duration_ms": _ms(event.duration_s),
                "is_error": event.is_error,
                "detail": json.dumps(dict(event.detail), ensure_ascii=False),
            }
            for seq, event in enumerate(trace.events, start=1)
        ]

        async def work() -> None:
            async with self._engine.begin() as conn:
                if (await conn.execute(_INSERT_TURN, turn)).rowcount == 0:
                    return
                if events:
                    await conn.execute(_INSERT_EVENT, events)

        await retrying("record trace", work)

    async def last(self, tenant_id: str, session_id: str) -> TurnTrace | None:
        async def work() -> TurnTrace | None:
            params = {"tenant_id": tenant_id, "session_id": session_id, "agent": self._agent}
            async with self._engine.connect() as conn:
                row = (await conn.execute(_LAST_TURN, params)).one_or_none()
                if row is None:
                    return None
                return _turn_trace(row, await _events(conn, row.turn_id))

        return await retrying("load trace", work)


async def _events(conn: AsyncConnection, turn_id: object) -> tuple[TraceEvent, ...]:
    rows = await conn.execute(_TURN_EVENTS, {"turn_id": turn_id})
    return tuple(
        TraceEvent(
            kind=row.kind,
            step=row.step,
            duration_s=row.duration_ms / 1000,
            name=row.name,
            is_error=row.is_error,
            detail=row.detail,
        )
        for row in rows
    )


def _turn_trace(row: Any, events: tuple[TraceEvent, ...]) -> TurnTrace:
    return TurnTrace(
        turn_id=str(row.turn_id),
        tenant_id=row.tenant_id,
        session_id=row.session_id,
        user_id=row.user_id,
        channel=row.channel,
        started_at=row.started_at,
        duration_s=row.duration_ms / 1000,
        stop=row.stop,
        steps=row.steps,
        usage=Usage(
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_read_tokens=row.cache_read_tokens,
            cache_write_tokens=row.cache_write_tokens,
            reasoning_tokens=row.reasoning_tokens,
        ),
        compactions=row.compactions,
        error_kind=row.error_kind,
        events=events,
    )


def _ms(seconds: float) -> int:
    return round(seconds * 1000)
