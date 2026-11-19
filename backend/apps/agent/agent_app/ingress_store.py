"""Postgres versions of the inbound queue, conversations and per-session run locks (schema ``agent_rt``).

The run lock is a Postgres advisory lock held on its own autocommit connection for the whole turn: it spans
processes, and Postgres drops it when the holding connection dies, so a crashed process never leaves a session
locked.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, Sequence
from typing import Any, Final, cast

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_app.ingress import (
    MAX_DELIVERY_ERROR,
    DeliveryOutcome,
    IngressRecord,
    IngressStatus,
    SessionBusyError,
    TurnReply,
)
from agent_app.storage import AgentDatabase, retrying
from agentcore.channels import InboundMessage

LOCK_POLL_S: Final = 0.2

# Rows are read by column name, so ``*`` is enough.
_ACCEPT = sql(
    "INSERT INTO agent_rt.agent_ingress (tenant_id, agent, channel, external_id, conversation_id, user_id, "
    "session_id, text, metadata, delivery) VALUES (:tenant_id, :agent, :channel, :external_id, "
    ":conversation_id, :user_id, :session_id, :text, CAST(:metadata AS jsonb), :delivery) "
    "ON CONFLICT DO NOTHING RETURNING *"
)
_BY_EXTERNAL = sql(
    "SELECT * FROM agent_rt.agent_ingress "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND channel = :channel AND external_id = :external_id"
)
_GET = sql(
    "SELECT * FROM agent_rt.agent_ingress WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_NEXT_QUEUED = sql(
    "SELECT * FROM agent_rt.agent_ingress "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent AND status = 'queued' "
    "ORDER BY id LIMIT 1"
)
_QUEUED_IN_SESSION = sql(
    "SELECT * FROM agent_rt.agent_ingress "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id AND agent = :agent AND status = 'queued' "
    "ORDER BY id LIMIT :limit"
)
_CLAIM = sql(
    "UPDATE agent_rt.agent_ingress SET status = 'processing', attempts = attempts + 1, started_at = now() "
    "WHERE id = :id AND status = 'queued' RETURNING *"
)
_FINISH = sql(
    "UPDATE agent_rt.agent_ingress SET status = 'done', reply = CAST(:reply AS jsonb), error_kind = NULL, "
    "finished_at = now() WHERE id = :id"
)
_FAIL = sql(
    "UPDATE agent_rt.agent_ingress SET status = 'failed', error_kind = :error_kind, finished_at = now() "
    "WHERE id = :id"
)
_PROCESSING = sql(
    "SELECT * FROM agent_rt.agent_ingress WHERE agent = :agent AND status = 'processing' ORDER BY id"
)
_REQUEUE = sql(
    "UPDATE agent_rt.agent_ingress SET "
    "status = CASE WHEN attempts >= :max_attempts THEN 'dead' ELSE 'queued' END, "
    "error_kind = CASE WHEN attempts >= :max_attempts THEN 'interrupted' ELSE NULL END, "
    "finished_at = CASE WHEN attempts >= :max_attempts THEN now() ELSE NULL END "
    "WHERE id = :id AND status = 'processing' RETURNING status"
)
_QUEUED_SESSIONS = sql(
    "SELECT DISTINCT tenant_id, session_id FROM agent_rt.agent_ingress "
    "WHERE agent = :agent AND status = 'queued' ORDER BY tenant_id, session_id"
)
# Due: the turn is over and the reply waits for its time, or a crashed process left it sending. Held back:
# an earlier reply of the same session is not out yet (replies leave in the order the messages came).
_DUE_DELIVERIES = sql(
    "SELECT i.* FROM agent_rt.agent_ingress AS i WHERE i.tenant_id = :tenant_id AND i.agent = :agent "
    "AND i.channel = ANY(:channels) AND i.status IN ('done', 'failed', 'dead') AND ("
    "(i.delivery = 'pending' AND (i.delivery_after IS NULL OR i.delivery_after <= now())) OR "
    "(i.delivery = 'sending' AND i.delivery_at < now() - make_interval(secs => :stale_s))) "
    "AND NOT EXISTS (SELECT 1 FROM agent_rt.agent_ingress e WHERE e.agent = i.agent "
    "AND e.tenant_id = i.tenant_id AND e.session_id = i.session_id AND e.id < i.id "
    "AND e.delivery IN ('pending', 'sending')) ORDER BY i.id LIMIT :limit"
)
_CLAIM_DELIVERY = sql(
    "UPDATE agent_rt.agent_ingress AS i SET delivery = 'sending', "
    "delivery_attempts = i.delivery_attempts + 1, delivery_at = now() "
    "WHERE i.tenant_id = :tenant_id AND i.agent = :agent AND i.id = :id "
    "AND i.status IN ('done', 'failed', 'dead') AND ("
    "(i.delivery = 'pending' AND (i.delivery_after IS NULL OR i.delivery_after <= now())) OR "
    "(i.delivery = 'sending' AND i.delivery_at < now() - make_interval(secs => :stale_s))) "
    "AND NOT EXISTS (SELECT 1 FROM agent_rt.agent_ingress e WHERE e.agent = i.agent "
    "AND e.tenant_id = i.tenant_id AND e.session_id = i.session_id AND e.id < i.id "
    "AND e.delivery IN ('pending', 'sending')) RETURNING i.*"
)
_DELIVERY_PROGRESS = sql(
    "UPDATE agent_rt.agent_ingress SET delivered_parts = :parts, delivery_at = now() WHERE id = :id"
)
_RETRY_DELIVERY = sql(
    "UPDATE agent_rt.agent_ingress SET delivery = 'pending', delivery_error = :error, "
    "delivery_after = now() + make_interval(secs => :after_s) WHERE id = :id"
)
_FINISH_DELIVERY = sql(
    "UPDATE agent_rt.agent_ingress SET delivery = :outcome, delivery_error = :error, delivery_after = NULL, "
    "delivery_at = now() WHERE id = :id"
)
_EPOCH = sql(
    "SELECT epoch FROM agent_rt.agent_conversation WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND channel = :channel AND conversation_id = :conversation_id"
)
_RESET = sql(
    "INSERT INTO agent_rt.agent_conversation (tenant_id, agent, channel, conversation_id, epoch) "
    "VALUES (:tenant_id, :agent, :channel, :conversation_id, 1) "
    "ON CONFLICT (tenant_id, agent, channel, conversation_id) DO UPDATE SET "
    "epoch = agent_rt.agent_conversation.epoch + 1, updated_at = now() RETURNING epoch"
)
_TRY_LOCK = sql("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))")
_UNLOCK = sql("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")


def _record(row: Any) -> IngressRecord:
    reply = cast(dict[str, Any] | None, row.reply)
    return IngressRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        channel=row.channel,
        external_id=row.external_id,
        conversation_id=row.conversation_id,
        user_id=row.user_id,
        session_id=row.session_id,
        text=row.text,
        status=row.status,
        attempts=row.attempts,
        error_kind=row.error_kind,
        reply=None if reply is None else TurnReply.from_json(reply),
        metadata=cast(dict[str, str], row.metadata),
        delivery=row.delivery,
        delivery_attempts=row.delivery_attempts,
        delivered_parts=row.delivered_parts,
        delivery_error=row.delivery_error,
    )


class PostgresIngressStore:
    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    async def _one(self, what: str, statement: Any, params: dict[str, Any]) -> IngressRecord | None:
        async def work() -> IngressRecord | None:
            async with self._engine.begin() as conn:
                row = (await conn.execute(statement, params)).one_or_none()
            return None if row is None else _record(row)

        return await retrying(what, work)

    async def _write(self, what: str, statement: Any, params: dict[str, Any]) -> None:
        async def work() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(statement, params)

        await retrying(what, work)

    async def accept(
        self, tenant_id: str, inbound: InboundMessage, session_id: str, *, deliver: bool = False
    ) -> tuple[IngressRecord, bool]:
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            "channel": inbound.channel,
            "external_id": inbound.message_id,
            "conversation_id": inbound.conversation_id,
            "user_id": inbound.user_id,
            "session_id": session_id,
            "text": inbound.text,
            "metadata": json.dumps(dict(inbound.metadata), ensure_ascii=False),
            "delivery": "pending" if deliver else None,
        }

        async def work() -> tuple[IngressRecord, bool]:
            async with self._engine.begin() as conn:
                row = (await conn.execute(_ACCEPT, params)).one_or_none()
                if row is not None:
                    return _record(row), True
                return _record((await conn.execute(_BY_EXTERNAL, params)).one()), False

        return await retrying("accept message", work)

    async def get(self, tenant_id: str, ingress_id: int) -> IngressRecord | None:
        params = {"tenant_id": tenant_id, "agent": self._agent, "id": ingress_id}
        return await self._one("get message", _GET, params)

    async def next_queued(self, tenant_id: str, session_id: str) -> IngressRecord | None:
        params = {"tenant_id": tenant_id, "session_id": session_id, "agent": self._agent}
        return await self._one("next message", _NEXT_QUEUED, params)

    async def claim(self, ingress_id: int) -> IngressRecord | None:
        return await self._one("claim message", _CLAIM, {"id": ingress_id})

    async def queued_in_session(self, tenant_id: str, session_id: str, limit: int) -> list[IngressRecord]:
        params = {"tenant_id": tenant_id, "session_id": session_id, "agent": self._agent, "limit": limit}

        async def work() -> list[IngressRecord]:
            async with self._engine.connect() as conn:
                return [_record(row) for row in await conn.execute(_QUEUED_IN_SESSION, params)]

        return await retrying("list queued messages", work)

    async def finish(self, ingress_id: int, reply: TurnReply) -> None:
        params = {"id": ingress_id, "reply": json.dumps(reply.to_json(), ensure_ascii=False)}
        await self._write("finish message", _FINISH, params)

    async def fail(self, ingress_id: int, error_kind: str) -> None:
        await self._write("fail message", _FAIL, {"id": ingress_id, "error_kind": error_kind})

    async def processing(self) -> list[IngressRecord]:
        async def work() -> list[IngressRecord]:
            async with self._engine.connect() as conn:
                return [_record(row) for row in await conn.execute(_PROCESSING, {"agent": self._agent})]

        return await retrying("list processing", work)

    async def requeue(self, ingress_id: int, *, max_attempts: int) -> IngressStatus | None:
        async def work() -> IngressStatus | None:
            async with self._engine.begin() as conn:
                status = (
                    await conn.execute(_REQUEUE, {"id": ingress_id, "max_attempts": max_attempts})
                ).scalar_one_or_none()
            return cast(IngressStatus | None, status)

        return await retrying("requeue message", work)

    async def queued_sessions(self) -> list[tuple[str, str]]:
        async def work() -> list[tuple[str, str]]:
            async with self._engine.connect() as conn:
                rows = await conn.execute(_QUEUED_SESSIONS, {"agent": self._agent})
                return [(row.tenant_id, row.session_id) for row in rows]

        return await retrying("list queued sessions", work)

    async def due_deliveries(
        self, tenant_id: str, channels: Sequence[str], *, stale_s: float, limit: int
    ) -> list[IngressRecord]:
        if not channels:
            return []
        params = {
            "tenant_id": tenant_id,
            "agent": self._agent,
            "channels": list(channels),
            "stale_s": stale_s,
            "limit": limit,
        }

        async def work() -> list[IngressRecord]:
            async with self._engine.connect() as conn:
                return [_record(row) for row in await conn.execute(_DUE_DELIVERIES, params)]

        return await retrying("list due deliveries", work)

    async def claim_delivery(
        self, tenant_id: str, ingress_id: int, *, stale_s: float
    ) -> IngressRecord | None:
        params = {"tenant_id": tenant_id, "agent": self._agent, "id": ingress_id, "stale_s": stale_s}
        return await self._one("claim delivery", _CLAIM_DELIVERY, params)

    async def delivery_progress(self, ingress_id: int, parts: int) -> None:
        await self._write("delivery progress", _DELIVERY_PROGRESS, {"id": ingress_id, "parts": parts})

    async def retry_delivery(self, ingress_id: int, error: str, *, after_s: float) -> None:
        params = {"id": ingress_id, "error": error[:MAX_DELIVERY_ERROR], "after_s": after_s}
        await self._write("retry delivery", _RETRY_DELIVERY, params)

    async def finish_delivery(
        self, ingress_id: int, outcome: DeliveryOutcome, error: str | None = None
    ) -> None:
        params = {
            "id": ingress_id,
            "outcome": outcome,
            "error": None if error is None else error[:MAX_DELIVERY_ERROR],
        }
        await self._write("finish delivery", _FINISH_DELIVERY, params)


class PostgresConversationStore:
    def __init__(self, db: AgentDatabase, *, agent: str) -> None:
        self._engine = db.engine
        self._agent = agent

    def _params(self, tenant_id: str, channel: str, conversation_id: str) -> dict[str, str]:
        return {
            "tenant_id": tenant_id,
            "agent": self._agent,
            "channel": channel,
            "conversation_id": conversation_id,
        }

    async def epoch(self, tenant_id: str, channel: str, conversation_id: str) -> int:
        async def work() -> int:
            async with self._engine.connect() as conn:
                found = await conn.execute(_EPOCH, self._params(tenant_id, channel, conversation_id))
                return found.scalar_one_or_none() or 0

        return await retrying("conversation epoch", work)

    async def reset(self, tenant_id: str, channel: str, conversation_id: str) -> int:
        async def work() -> int:
            async with self._engine.begin() as conn:
                found = await conn.execute(_RESET, self._params(tenant_id, channel, conversation_id))
                return found.scalar_one()

        return await retrying("reset conversation", work)


class PostgresSessionLocks:
    def __init__(self, db: AgentDatabase) -> None:
        self._engine: AsyncEngine = db.engine

    @contextlib.asynccontextmanager
    async def hold(self, tenant_id: str, session_id: str, *, timeout_s: float | None) -> AsyncGenerator[None]:
        key = {"key": f"agent-session:{tenant_id}:{session_id}"}
        async with self._engine.connect() as raw:
            conn = await raw.execution_options(isolation_level="AUTOCOMMIT")
            await _acquire(conn, key, session_id, timeout_s)
            try:
                yield
            finally:
                try:
                    await conn.execute(_UNLOCK, key)
                except Exception:  # a broken connection releases the lock itself; never pool it again
                    await raw.invalidate()
                    raise


async def _acquire(
    conn: AsyncConnection, key: dict[str, str], session_id: str, timeout_s: float | None
) -> None:
    loop = asyncio.get_running_loop()
    deadline = None if timeout_s is None else loop.time() + timeout_s
    while not (await conn.execute(_TRY_LOCK, key)).scalar_one():
        if deadline is not None and loop.time() >= deadline:
            raise SessionBusyError(session_id)
        await asyncio.sleep(LOCK_POLL_S)
