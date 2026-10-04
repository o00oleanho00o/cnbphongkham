# ported from: src/agent/agent-trace-store.ts
"""Trace of every step of an agent turn (table ``agent.usage_steps``), linked to ``agent.usage``.

Placed in ``conversation/`` because it owns the ``agent.usage_steps`` table (PORT-MAP).

Why a table and not only a log: logs drift away and make it hard to join the steps of one turn. Why our own
database and not an external trace service: the trace holds the VERBATIM messages of real people; pushing it
to a SaaS pushes their conversations out of the machine. That is a privacy decision, not a technical one.
For a clinic it is a legal one: patient text never leaves the infrastructure. The dashboard already has room
to read it. (Access to it is the ``admin.usage`` permission, staff only.)

This table grows faster than any other. In production ``pema.retention`` prunes it (the ``trace_steps``
rule of the worker's agent scope); ``prune_old_traces`` is kept for its ported tests and for a one-off call.

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres; the JSON columns are ``jsonb`` (no
``JSON.parse`` guard needed for the list columns, a corrupt value cannot exist); the per-step INSERT loop of
``saveTurnTrace`` is ONE executemany; ``agent.usage_steps`` has a foreign key to ``agent.usage`` with
``ON DELETE CASCADE`` (the original deleted steps by hand because SQLite had none), so saving a trace for a
turn id that does not exist is an error instead of an orphan row. ``GROUP BY t.id`` of the all-threads list
becomes two scalar subqueries (Postgres refuses a bare ``th.display_name`` in a grouped query).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.sql_util import affected_rows
from pema.core.db import ClinicDatabase
from pema_contracts.admin_agent import TraceTurnRow
from pema_contracts.agent_turn import StepTrace
from pema_contracts.conversation import TraceStepRow

_INSERT = text(
    """
    INSERT INTO agent.usage_steps
      (clinic_id, turn_id, step_number, attempt, text, reasoning, tool_calls, tool_results, tool_errors,
       finish_reason, warnings, input_tokens, output_tokens)
    VALUES
      (:clinic_id, :turn_id, :step_number, :attempt, :text, :reasoning, CAST(:tool_calls AS jsonb),
       CAST(:tool_results AS jsonb), CAST(:tool_errors AS jsonb), :finish_reason, CAST(:warnings AS jsonb),
       :input_tokens, :output_tokens)
    """
)

_SELECT = text(
    """
    SELECT step_number, attempt, text, reasoning, tool_calls, tool_results, tool_errors,
           finish_reason, warnings, input_tokens, output_tokens
    FROM agent.usage_steps WHERE clinic_id = :clinic_id AND turn_id = :turn_id
    ORDER BY attempt ASC, step_number ASC, id ASC
    """
)

_RECENT_TURNS = text(
    """
    SELECT t.id, t.total_tokens, t.steps, t.created_at, (SELECT COUNT(*) FROM agent.usage_steps s WHERE
    s.clinic_id = t.clinic_id AND s.turn_id = t.id) AS step_count FROM agent.usage t WHERE t.clinic_id =
    :clinic_id AND t.account_id = :account_id AND t.thread_id = :thread_id ORDER BY t.id DESC LIMIT :limit
    """
)

# Bản có CON TRỎ cho nút "Xem thêm": chỉ lấy lượt CŨ HƠN ``id`` đã cho. A separate statement instead of
# ``(:before IS NULL OR t.id < :before)``: an always-true condition like that keeps the planner from using the
# index on ``id`` for the most frequent path just to merge two statements into one.
_RECENT_TURNS_BEFORE = text(
    """
    SELECT t.id, t.total_tokens, t.steps, t.created_at, (SELECT COUNT(*) FROM agent.usage_steps s WHERE
    s.clinic_id = t.clinic_id AND s.turn_id = t.id) AS step_count FROM agent.usage t WHERE t.clinic_id =
    :clinic_id AND t.account_id = :account_id AND t.thread_id = :thread_id AND t.id < :before_id ORDER BY
    t.id DESC LIMIT :limit
    """
)

# Lượt của MỌI thread cho trang Trace ở sidebar. "Has a step" (INNER JOIN in the original) and not LEFT: only
# turns that HAVE a trace are listed. A turn without a trace on the list opens empty, which is worse than not
# showing it. The thread name is a scalar subquery (a thread may not have a display name yet).
_RECENT_ALL = text(
    """
    SELECT t.id, t.account_id, t.thread_id, t.total_tokens, t.steps, t.created_at, COALESCE(NULLIF((SELECT
    th.display_name FROM agent.threads th WHERE th.clinic_id = t.clinic_id AND th.account_id = t.account_id
    AND th.thread_id = t.thread_id), ''), t.thread_id) AS display_name, (SELECT COUNT(*) FROM
    agent.usage_steps s WHERE s.clinic_id = t.clinic_id AND s.turn_id = t.id) AS step_count FROM agent.usage
    t WHERE t.clinic_id = :clinic_id AND EXISTS (SELECT 1 FROM agent.usage_steps s WHERE s.clinic_id =
    t.clinic_id AND s.turn_id = t.id) ORDER BY t.id DESC LIMIT :limit
    """
)

# Bản có CON TRỎ - xem lý do tách câu ở ``_RECENT_TURNS_BEFORE``.
_RECENT_ALL_BEFORE = text(
    """
    SELECT t.id, t.account_id, t.thread_id, t.total_tokens, t.steps, t.created_at, COALESCE(NULLIF((SELECT
    th.display_name FROM agent.threads th WHERE th.clinic_id = t.clinic_id AND th.account_id = t.account_id
    AND th.thread_id = t.thread_id), ''), t.thread_id) AS display_name, (SELECT COUNT(*) FROM
    agent.usage_steps s WHERE s.clinic_id = t.clinic_id AND s.turn_id = t.id) AS step_count FROM agent.usage
    t WHERE t.clinic_id = :clinic_id AND t.id < :before_id AND EXISTS (SELECT 1 FROM agent.usage_steps s
    WHERE s.clinic_id = t.clinic_id AND s.turn_id = t.id) ORDER BY t.id DESC LIMIT :limit
    """
)

_PRUNE = text("DELETE FROM agent.usage_steps WHERE clinic_id = :clinic_id AND created_at < :cutoff")


@dataclass(frozen=True)
class TurnSummary:
    id: int
    total_tokens: int
    steps: int
    step_count: int
    created_at: datetime


@dataclass(frozen=True)
class TurnAcrossThreads(TurnSummary):
    account_id: str = ""
    thread_id: str = ""
    display_name: str = ""
    """Tên thread, rơi về ``thread_id`` khi thread chưa kịp có tên."""


def _step_params(clinic_id: UUID, turn_id: int, step: StepTrace) -> dict[str, Any]:
    return {
        "clinic_id": clinic_id,
        "turn_id": turn_id,
        "step_number": step.step_number,
        "attempt": step.attempt,
        "text": step.text,
        "reasoning": step.reasoning,
        "tool_calls": json.dumps(step.tool_calls),
        "tool_results": json.dumps(step.tool_results),
        "tool_errors": json.dumps(step.tool_errors),
        "finish_reason": step.finish_reason,
        "warnings": json.dumps(step.warnings),
        "input_tokens": step.input_tokens,
        "output_tokens": step.output_tokens,
    }


def _json_list(raw: object) -> list[Any]:
    """JSON hỏng trong DB không được làm chết trang dashboard (a ``jsonb`` column cannot hold corrupt
    JSON, but a value of the wrong shape is still tolerated)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return list(raw) if isinstance(raw, list) else []  # pyright: ignore[reportUnknownArgumentType]


class AgentTraceStore:
    """Save and read the trace of agent turns."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def save_turn_trace(self, clinic_id: UUID, turn_id: int, steps: list[StepTrace]) -> None:
        """INSERT of the whole trace of a turn (``saveTurnTrace``); a turn without steps writes nothing."""
        if not steps:
            return
        async with self._db.session(clinic_id) as session:
            await self.save_turn_trace_in(session, clinic_id, turn_id, steps)

    @staticmethod
    async def save_turn_trace_in(
        session: AsyncSession, clinic_id: UUID, turn_id: int, steps: list[StepTrace]
    ) -> None:
        await session.execute(_INSERT, [_step_params(clinic_id, turn_id, s) for s in steps])

    async def get_turn_trace(self, clinic_id: UUID, turn_id: int) -> list[StepTrace]:
        async with self._db.session(clinic_id) as session:
            rows = (
                (await session.execute(_SELECT, {"clinic_id": clinic_id, "turn_id": turn_id}))
                .mappings()
                .all()
            )
        return [
            StepTrace(
                step_number=r["step_number"],
                attempt=r["attempt"],
                text=r["text"],
                reasoning=r["reasoning"],
                tool_calls=_json_list(r["tool_calls"]),
                tool_results=_json_list(r["tool_results"]),
                # Dòng ghi TRƯỚC khi có cột này đọc ra chuỗi mặc định '[]' - không phải null.
                tool_errors=_json_list(r["tool_errors"]),
                finish_reason=r["finish_reason"],
                warnings=[str(w) for w in _json_list(r["warnings"])],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
            )
            for r in rows
        ]

    async def get_recent_turns(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int, before_id: int | None = None
    ) -> list[TurnSummary]:
        """Các lượt gần đây của 1 thread - danh sách cho dashboard bấm vào xem trace. ``before_id`` = chỉ lấy
        lượt cũ hơn id đó (nút "Xem thêm")."""
        params: dict[str, Any] = {
            "clinic_id": clinic_id,
            "account_id": account_id,
            "thread_id": thread_id,
            "limit": limit,
        }
        async with self._db.session(clinic_id) as session:
            if before_id is None:
                rows = (await session.execute(_RECENT_TURNS, params)).mappings().all()
            else:
                rows = (
                    (await session.execute(_RECENT_TURNS_BEFORE, {**params, "before_id": before_id}))
                    .mappings()
                    .all()
                )
        return [
            TurnSummary(
                id=r["id"],
                total_tokens=r["total_tokens"],
                steps=r["steps"],
                step_count=r["step_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get_recent_turns_all_threads(
        self, clinic_id: UUID, limit: int, before_id: int | None = None
    ) -> list[TurnAcrossThreads]:
        """Lượt gần đây của mọi thread - nguồn cho trang Trace ở sidebar."""
        params: dict[str, Any] = {"clinic_id": clinic_id, "limit": limit}
        async with self._db.session(clinic_id) as session:
            if before_id is None:
                rows = (await session.execute(_RECENT_ALL, params)).mappings().all()
            else:
                rows = (
                    (await session.execute(_RECENT_ALL_BEFORE, {**params, "before_id": before_id}))
                    .mappings()
                    .all()
                )
        return [
            TurnAcrossThreads(
                id=r["id"],
                total_tokens=r["total_tokens"],
                steps=r["steps"],
                step_count=r["step_count"],
                created_at=r["created_at"],
                account_id=r["account_id"],
                thread_id=r["thread_id"],
                display_name=r["display_name"],
            )
            for r in rows
        ]

    async def prune_old_traces(
        self, clinic_id: UUID, retention_days: int | None = None, now: datetime | None = None
    ) -> int:
        """Xóa trace cũ hơn N ngày (default ``AGENT_TRACE_RETENTION_DAYS``). Trả về số dòng đã xóa."""
        days = retention_days if retention_days is not None else get_tuning_int("AGENT_TRACE_RETENTION_DAYS")
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        async with self._db.session(clinic_id) as session:
            result = await session.execute(_PRUNE, {"clinic_id": clinic_id, "cutoff": cutoff})
            return affected_rows(result)


_READER_TURNS = text(
    """
    SELECT t.id, t.account_id, t.thread_id, t.source, t.input_tokens, t.output_tokens, t.total_tokens,
           t.steps, t.created_at,
           NULLIF((SELECT th.display_name FROM agent.threads th WHERE th.clinic_id = t.clinic_id
                   AND th.account_id = t.account_id AND th.thread_id = t.thread_id), '') AS thread_name
    FROM agent.usage t
    WHERE t.clinic_id = :clinic_id
      AND (CAST(:before AS bigint) IS NULL OR t.id < CAST(:before AS bigint))
      AND (CAST(:account_id AS text) IS NULL OR t.account_id = CAST(:account_id AS text))
      AND (CAST(:thread_id AS text) IS NULL OR t.thread_id = CAST(:thread_id AS text))
    ORDER BY t.id DESC LIMIT :limit
    """
)

_READER_STEPS = text(
    """
    SELECT id, turn_id, created_at, step_number, attempt, text, reasoning, tool_calls, tool_results,
           tool_errors, finish_reason, warnings, input_tokens, output_tokens
    FROM agent.usage_steps WHERE clinic_id = :clinic_id AND turn_id = :turn_id
    ORDER BY attempt ASC, step_number ASC, id ASC
    """
)


class PgTraceReader:
    """The read side of the admin ``/traces`` routes (``TraceReader`` of ``routers/admin_usage``): turns
    newest first with a cursor, and the steps of one turn, in the shapes of the API contract. Staff-only data
    (``admin.usage``): the steps hold the verbatim messages."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def list_recent_turns(
        self,
        clinic_id: UUID,
        *,
        before: int | None,
        limit: int,
        account_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[TraceTurnRow]:
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        _READER_TURNS,
                        {
                            "clinic_id": clinic_id,
                            "before": before,
                            "account_id": account_id,
                            "thread_id": thread_id,
                            "limit": limit,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [
            TraceTurnRow(
                id=r["id"],
                account_id=r["account_id"],
                thread_id=r["thread_id"],
                source="schedule" if r["source"] == "schedule" else "message",
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                total_tokens=r["total_tokens"],
                steps=r["steps"],
                created_at=r["created_at"],
                thread_name=r["thread_name"],
            )
            for r in rows
        ]

    async def get_turn_steps(self, clinic_id: UUID, turn_id: int) -> list[TraceStepRow]:
        async with self._db.session(clinic_id) as session:
            rows = (
                (await session.execute(_READER_STEPS, {"clinic_id": clinic_id, "turn_id": turn_id}))
                .mappings()
                .all()
            )
        return [
            TraceStepRow(
                id=r["id"],
                turn_id=r["turn_id"],
                created_at=r["created_at"],
                step_number=r["step_number"],
                attempt=r["attempt"],
                text=r["text"],
                reasoning=r["reasoning"],
                tool_calls=_json_list(r["tool_calls"]),
                tool_results=_json_list(r["tool_results"]),
                tool_errors=_json_list(r["tool_errors"]),
                finish_reason=r["finish_reason"],
                warnings=[str(w) for w in _json_list(r["warnings"])],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
            )
            for r in rows
        ]
