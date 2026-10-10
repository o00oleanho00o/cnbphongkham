"""What the agent did, for the dashboard: its chat sessions, the trace of each turn and the usage per day.

Read-only except deleting a session (the agent then starts that conversation from nothing). One query per
page, every statement parameterised, every list paged (a page asks for one row more to know if another
follows). Without a database (a run in memory) every list is empty.

The trace holds timings, tokens and outcomes only; the words of a conversation are in the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final

from sqlalchemy import text as sql

from agent_app.storage import AgentDatabase, retrying
from agentcore import Message, ToolUseBlock

PAGE_SIZE: Final = 30
MAX_PAGE: Final = 10_000
MAX_DAYS: Final = 90
SEARCH_CHARS: Final = 100

_SESSIONS = sql(
    "SELECT session_id, channel, user_id, message_count, (summary IS NOT NULL) AS compacted, "
    "created_at, updated_at FROM agent_rt.agent_session "
    "WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND (CAST(:channel AS text) IS NULL OR channel = :channel) "
    "AND (CAST(:pattern AS text) IS NULL OR user_id ILIKE :pattern ESCAPE '\\' "
    "OR session_id ILIKE :pattern ESCAPE '\\') "
    "ORDER BY updated_at DESC, session_id LIMIT :limit OFFSET :offset"
)
_SESSION = sql(
    "SELECT session_id, channel, user_id, message_count, summary, created_at, updated_at "
    "FROM agent_rt.agent_session WHERE tenant_id = :tenant_id AND agent = :agent AND session_id = :session_id"
)
_MESSAGES = sql(
    "SELECT message, created_at FROM agent_rt.agent_message "
    "WHERE tenant_id = :tenant_id AND session_id = :session_id ORDER BY seq"
)
_DELETE_SESSION = sql(
    "DELETE FROM agent_rt.agent_session "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND session_id = :session_id"
)
_TURNS = sql(
    "SELECT turn_id, session_id, channel, user_id, model, started_at, duration_ms, stop, steps, error_kind, "
    "input_tokens, output_tokens FROM agent_rt.agent_turn "
    "WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND (CAST(:channel AS text) IS NULL OR channel = :channel) "
    "AND (CAST(:session_id AS text) IS NULL OR session_id = :session_id) "
    "AND (NOT :errors_only OR stop <> 'completed') "
    "ORDER BY started_at DESC, turn_id LIMIT :limit OFFSET :offset"
)
_TURN = sql(
    "SELECT turn_id, session_id, channel, user_id, model, started_at, duration_ms, stop, steps, error_kind, "
    "compactions, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens "
    "FROM agent_rt.agent_turn "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND turn_id = CAST(:turn_id AS uuid)"
)
_EVENTS = sql(
    "SELECT kind, step, name, duration_ms, is_error, detail FROM agent_rt.agent_turn_event "
    "WHERE turn_id = CAST(:turn_id AS uuid) ORDER BY seq"
)
_USAGE = sql(
    "SELECT CAST((started_at AT TIME ZONE :tz) AS date) AS day, count(*) AS turns, "
    "count(*) FILTER (WHERE stop <> 'completed') AS failed, "
    "coalesce(sum(input_tokens), 0) AS input_tokens, coalesce(sum(output_tokens), 0) AS output_tokens "
    "FROM agent_rt.agent_turn WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND started_at >= CAST(CAST((now() AT TIME ZONE :tz) AS date) - CAST(:back AS integer) AS timestamp) "
    "AT TIME ZONE :tz GROUP BY 1 ORDER BY 1"
)
_TODAY = sql("SELECT CAST((now() AT TIME ZONE :tz) AS date) AS today")


def clamp_page(page: int) -> int:
    return max(0, min(page, MAX_PAGE))


def like_pattern(search: str) -> str | None:
    """``%text%`` with the characters LIKE treats specially escaped; None for an empty search."""
    text = search.strip()[:SEARCH_CHARS]
    if not text:
        return None
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True, slots=True)
class Page:
    items: list[dict[str, Any]]
    has_more: bool

    def to_json(self) -> dict[str, Any]:
        return {"items": self.items, "has_more": self.has_more}


class Activity:
    """Sessions, turns and usage of one agent for one tenant."""

    def __init__(self, db: AgentDatabase | None, *, agent: str, tenant_id: str, timezone: str) -> None:
        self._engine = None if db is None else db.engine
        self._agent = agent
        self._tenant_id = tenant_id
        self._timezone = timezone

    def _key(self) -> dict[str, Any]:
        return {"tenant_id": self._tenant_id, "agent": self._agent}

    async def sessions(self, *, channel: str | None, search: str, page: int) -> Page:
        params = {
            **self._key(),
            "channel": channel or None,
            "pattern": like_pattern(search),
            **_paging(page),
        }
        return await self._page("list sessions", _SESSIONS, params, _session_row)

    async def session(self, session_id: str) -> dict[str, Any] | None:
        if self._engine is None:
            return None
        engine = self._engine
        params = {**self._key(), "session_id": session_id}

        async def work() -> dict[str, Any] | None:
            async with engine.connect() as conn:
                row = (await conn.execute(_SESSION, params)).one_or_none()
                if row is None:
                    return None
                messages = await conn.execute(_MESSAGES, params)
                return {
                    **_session_row(row),
                    "summary": row.summary,
                    "messages": [_message_row(m.message, m.created_at) for m in messages],
                }

        return await retrying("load session", work)

    async def delete_session(self, session_id: str) -> bool:
        """True when the session existed; its messages go with it, its trace stays."""
        if self._engine is None:
            return False
        engine = self._engine
        params = {**self._key(), "session_id": session_id}

        async def work() -> bool:
            async with engine.begin() as conn:
                return (await conn.execute(_DELETE_SESSION, params)).rowcount > 0

        return await retrying("delete session", work)

    async def turns(
        self, *, channel: str | None, session_id: str | None, errors_only: bool, page: int
    ) -> Page:
        params = {
            **self._key(),
            "channel": channel or None,
            "session_id": session_id or None,
            "errors_only": errors_only,
            **_paging(page),
        }
        return await self._page("list turns", _TURNS, params, _turn_row)

    async def turn(self, turn_id: str) -> dict[str, Any] | None:
        if self._engine is None:
            return None
        engine = self._engine
        params = {"turn_id": turn_id}

        async def work() -> dict[str, Any] | None:
            async with engine.connect() as conn:
                row = (await conn.execute(_TURN, {**self._key(), **params})).one_or_none()
                if row is None:
                    return None
                events = await conn.execute(_EVENTS, params)
                return {
                    **_turn_row(row),
                    "compactions": row.compactions,
                    "cache_read_tokens": row.cache_read_tokens,
                    "cache_write_tokens": row.cache_write_tokens,
                    "reasoning_tokens": row.reasoning_tokens,
                    "events": [
                        {
                            "kind": e.kind,
                            "step": e.step,
                            "name": e.name,
                            "duration_ms": e.duration_ms,
                            "is_error": e.is_error,
                            "detail": e.detail,
                        }
                        for e in events
                    ],
                }

        return await retrying("load turn", work)

    async def usage(self, days: int) -> dict[str, Any]:
        """Turns, failed turns and tokens per day for the last ``days`` days (today included), days in the
        agent's time zone; days with no turn are filled with zeros so a chart can draw them as they are."""
        days = max(1, min(days, MAX_DAYS))
        if self._engine is None:
            return {"today": None, "days": []}
        engine = self._engine
        params = {**self._key(), "tz": self._timezone, "back": days - 1}

        async def work() -> dict[str, Any]:
            async with engine.connect() as conn:
                today = (await conn.execute(_TODAY, {"tz": self._timezone})).scalar_one()
                rows = {row.day: row for row in await conn.execute(_USAGE, params)}
            return {"today": today.isoformat(), "days": _filled(today, days, rows)}

        return await retrying("load usage", work)

    async def _page(self, what: str, statement: Any, params: dict[str, Any], row: Any) -> Page:
        if self._engine is None:
            return Page([], False)
        engine = self._engine

        async def work() -> Page:
            async with engine.connect() as conn:
                rows = [row(r) for r in await conn.execute(statement, params)]
            return Page(rows[:PAGE_SIZE], len(rows) > PAGE_SIZE)

        return await retrying(what, work)


def _paging(page: int) -> dict[str, int]:
    return {"limit": PAGE_SIZE + 1, "offset": clamp_page(page) * PAGE_SIZE}


def _iso(value: datetime) -> str:
    return value.isoformat()


def _session_row(row: Any) -> dict[str, Any]:
    row_dict: dict[str, Any] = {
        "session_id": row.session_id,
        "channel": row.channel,
        "user_id": row.user_id,
        "message_count": row.message_count,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if hasattr(row, "compacted"):
        row_dict["compacted"] = row.compacted
    return row_dict


def _message_row(raw: Any, created_at: datetime) -> dict[str, Any]:
    message = Message.model_validate(raw)
    return {
        "role": message.role,
        "text": message.text(),
        "tools": [block.name for block in message.blocks if isinstance(block, ToolUseBlock)],
        "at": _iso(created_at),
    }


def _turn_row(row: Any) -> dict[str, Any]:
    return {
        "turn_id": str(row.turn_id),
        "session_id": row.session_id,
        "channel": row.channel,
        "user_id": row.user_id,
        "model": row.model,
        "started_at": _iso(row.started_at),
        "duration_ms": row.duration_ms,
        "stop": row.stop,
        "steps": row.steps,
        "error_kind": row.error_kind,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
    }


def _filled(today: date, days: int, rows: dict[date, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for back in range(days - 1, -1, -1):
        day = date.fromordinal(today.toordinal() - back)
        row = rows.get(day)
        out.append(
            {
                "day": day.isoformat(),
                "turns": 0 if row is None else int(row.turns),
                "failed": 0 if row is None else int(row.failed),
                "input_tokens": 0 if row is None else int(row.input_tokens),
                "output_tokens": 0 if row is None else int(row.output_tokens),
            }
        )
    return out


__all__ = ["Activity", "Page", "clamp_page", "like_pattern"]
