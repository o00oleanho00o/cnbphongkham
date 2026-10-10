"""The dashboard's view of what the agent did (sessions, turn traces, usage) on Postgres. Needs
``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated again); skipped otherwise.

Each test runs its async part on a selector event loop: psycopg's async driver cannot use the Windows proactor
loop.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import text as sql

from agent_app.activity import PAGE_SIZE, Activity
from agent_app.storage import AgentDatabase, PostgresSessionStore, PostgresTracer
from agentcore import Message, TextBlock, ToolUseBlock, TraceEvent, TurnTrace, Usage

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[1]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
TENANT = "t"


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[str, Engine]]:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(sql("DROP SCHEMA IF EXISTS agent_rt CASCADE"))
        conn.execute(sql("DROP TABLE IF EXISTS public.alembic_version_agent_rt"))
    previous = os.environ.get(MIGRATION_ENV)
    os.environ[MIGRATION_ENV] = url
    try:
        command.upgrade(Config(str(APP_DIR / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop(MIGRATION_ENV, None)
        else:
            os.environ[MIGRATION_ENV] = previous
    yield url, engine
    engine.dispose()


@pytest.fixture
def db_url(migrated: tuple[str, Engine]) -> str:
    with migrated[1].begin() as conn:
        conn.execute(
            sql("TRUNCATE agent_rt.agent_session, agent_rt.agent_message, agent_rt.agent_turn CASCADE")
        )
    return migrated[0]


def _run(url: str, check: Callable[[AgentDatabase], Awaitable[None]]) -> None:
    async def main() -> None:
        database = AgentDatabase(url)
        try:
            await check(database)
        finally:
            await database.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _activity(db: AgentDatabase, agent: str = "dev") -> Activity:
    return Activity(db, agent=agent, tenant_id=TENANT, timezone="Asia/Ho_Chi_Minh")


async def _chat(db: AgentDatabase, session_id: str, channel: str, user: str, *, agent: str = "dev") -> None:
    store = PostgresSessionStore(db, agent=agent)
    await store.open_session(TENANT, session_id, channel=channel, user_id=user)
    await store.append(TENANT, session_id, Message.user("Cho tôi hỏi giá laser"))
    tool = ToolUseBlock(id="call-1", name="kb_search", args={"q": "laser"})
    await store.append(
        TENANT, session_id, Message(role="assistant", blocks=[TextBlock(text="Dạ vâng"), tool])
    )


def _trace(
    turn_id: str,
    session_id: str,
    channel: str,
    *,
    started: datetime,
    stop: str = "completed",
    tokens: tuple[int, int] = (10, 5),
) -> TurnTrace:
    event = TraceEvent("tool_call", 1, 0.25, name="kb_search", is_error=stop == "error", detail={"size": 12})
    return TurnTrace(
        turn_id=turn_id,
        tenant_id=TENANT,
        session_id=session_id,
        user_id="u1",
        channel=channel,
        started_at=started,
        duration_s=1.5,
        stop=stop,  # type: ignore[arg-type]  # a literal in the type, a plain str here
        steps=2,
        usage=Usage(input_tokens=tokens[0], output_tokens=tokens[1]),
        compactions=0,
        error_kind="rate_limit" if stop == "error" else None,
        events=(event,),
    )


def test_sessions_are_listed_newest_first_filtered_by_channel_and_searched_by_user(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        await _chat(db, "dev:zalo-a:u1:0", "zalo-a", "u1")
        await _chat(db, "dev:http:u2:0", "http", "u2")
        await _chat(db, "other:zalo-a:u1:0", "zalo-a", "u1", agent="other")
        activity = _activity(db)

        everything = await activity.sessions(channel=None, search="", page=0)
        zalo_only = await activity.sessions(channel="zalo-a", search="", page=0)
        by_user = await activity.sessions(channel=None, search="u2", page=0)

        assert [s["session_id"] for s in everything.items] == ["dev:http:u2:0", "dev:zalo-a:u1:0"]
        assert [s["session_id"] for s in zalo_only.items] == ["dev:zalo-a:u1:0"]
        assert [s["session_id"] for s in by_user.items] == ["dev:http:u2:0"]
        assert everything.items[0]["message_count"] == 2
        assert everything.has_more is False

    _run(db_url, check)


def test_a_search_with_percent_and_underscore_matches_them_literally(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        await _chat(db, "dev:zalo-a:ab:0", "zalo-a", "ab")
        await _chat(db, "dev:zalo-a:a_b:0", "zalo-a", "a_b")
        activity = _activity(db)

        literal = await activity.sessions(channel=None, search="a_b", page=0)
        wildcard = await activity.sessions(channel=None, search="%", page=0)

        assert [s["user_id"] for s in literal.items] == ["a_b"]
        assert wildcard.items == []

    _run(db_url, check)


def test_a_page_says_whether_another_follows(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        for number in range(PAGE_SIZE + 1):
            await _chat(db, f"dev:http:c{number:03d}:0", "http", f"c{number:03d}")
        activity = _activity(db)

        first = await activity.sessions(channel=None, search="", page=0)
        second = await activity.sessions(channel=None, search="", page=1)

        assert (len(first.items), first.has_more) == (PAGE_SIZE, True)
        assert (len(second.items), second.has_more) == (1, False)

    _run(db_url, check)


def test_a_session_shows_its_messages_and_tools_and_belongs_to_its_agent(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        await _chat(db, "dev:zalo-a:u1:0", "zalo-a", "u1")
        shown = await _activity(db).session("dev:zalo-a:u1:0")
        other_agent = await _activity(db, "other").session("dev:zalo-a:u1:0")

        assert shown is not None
        assert [(m["role"], m["text"], m["tools"]) for m in shown["messages"]] == [
            ("user", "Cho tôi hỏi giá laser", []),
            ("assistant", "Dạ vâng", ["kb_search"]),
        ]
        assert other_agent is None
        assert await _activity(db).session("missing") is None

    _run(db_url, check)


def test_deleting_a_session_removes_its_messages_but_not_its_trace(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        await _chat(db, "dev:zalo-a:u1:0", "zalo-a", "u1")
        tracer = PostgresTracer(db, agent="dev", model="m")
        await tracer.record(
            _trace("00000000-0000-4000-8000-000000000001", "dev:zalo-a:u1:0", "zalo-a", started=_now())
        )
        activity = _activity(db)

        wrong_agent = await _activity(db, "other").delete_session("dev:zalo-a:u1:0")
        deleted = await activity.delete_session("dev:zalo-a:u1:0")
        again = await activity.delete_session("dev:zalo-a:u1:0")

        assert (wrong_agent, deleted, again) == (False, True, False)
        assert await activity.session("dev:zalo-a:u1:0") is None
        assert (
            len((await activity.turns(channel=None, session_id=None, errors_only=False, page=0)).items) == 1
        )

    _run(db_url, check)


def _now() -> datetime:
    return datetime.now(UTC)


def test_turns_filter_by_channel_session_and_failures_and_show_their_steps(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        tracer = PostgresTracer(db, agent="dev", model="deepseek-v4-pro")
        base = _now()
        await tracer.record(_trace("00000000-0000-4000-8000-000000000001", "s1", "zalo-a", started=base))
        await tracer.record(
            _trace(
                "00000000-0000-4000-8000-000000000002",
                "s2",
                "http",
                started=base + timedelta(seconds=1),
                stop="error",
            )
        )
        activity = _activity(db)

        everything = await activity.turns(channel=None, session_id=None, errors_only=False, page=0)
        zalo = await activity.turns(channel="zalo-a", session_id=None, errors_only=False, page=0)
        failed = await activity.turns(channel=None, session_id=None, errors_only=True, page=0)
        of_session = await activity.turns(channel=None, session_id="s1", errors_only=False, page=0)
        detail = await activity.turn("00000000-0000-4000-8000-000000000002")

        assert [t["session_id"] for t in everything.items] == ["s2", "s1"]
        assert [t["session_id"] for t in zalo.items] == ["s1"]
        assert [t["error_kind"] for t in failed.items] == ["rate_limit"]
        assert [t["session_id"] for t in of_session.items] == ["s1"]
        assert detail is not None
        assert (detail["model"], detail["steps"], detail["input_tokens"]) == ("deepseek-v4-pro", 2, 10)
        assert [(e["kind"], e["name"], e["duration_ms"], e["is_error"]) for e in detail["events"]] == [
            ("tool_call", "kb_search", 250, True)
        ]
        assert await _activity(db, "other").turn("00000000-0000-4000-8000-000000000002") is None

    _run(db_url, check)


def test_usage_counts_each_day_and_fills_the_days_without_turns(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        tracer = PostgresTracer(db, agent="dev", model="m")
        now = _now()
        await tracer.record(
            _trace("00000000-0000-4000-8000-000000000001", "s1", "zalo-a", started=now, tokens=(100, 40))
        )
        await tracer.record(
            _trace(
                "00000000-0000-4000-8000-000000000002",
                "s1",
                "zalo-a",
                started=now,
                stop="error",
                tokens=(7, 0),
            )
        )
        await tracer.record(
            _trace(
                "00000000-0000-4000-8000-000000000003",
                "s1",
                "zalo-a",
                started=now - timedelta(days=3),
                tokens=(1, 1),
            )
        )

        usage = await _activity(db).usage(7)

        assert len(usage["days"]) == 7
        today = usage["days"][-1]
        assert (today["day"], today["turns"], today["failed"]) == (usage["today"], 2, 1)
        assert (today["input_tokens"], today["output_tokens"]) == (107, 40)
        assert [d["turns"] for d in usage["days"]] == [0, 0, 0, 1, 0, 0, 2]

    _run(db_url, check)
