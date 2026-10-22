"""The case store on Postgres (migration ``0004_cases``): opening is idempotent per live (kind, key), only due
cases come back, a save on a stale version is refused, the log counts what each person was sent, and the two
settings round-trip. Needs ``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated
again); skipped otherwise. Runs on a selector loop: psycopg's async driver cannot use the Windows proactor."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import text as sql
from sqlalchemy.exc import IntegrityError

from agent_app.cases import PostgresCaseStore
from agentcore.cases import CaseRecord

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[1]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
NOW = datetime(2026, 10, 22, 3, 0, tzinfo=UTC)


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
        conn.execute(sql("TRUNCATE agent_rt.agent_case CASCADE"))
    return migrated[0]


def _run(url: str, check: Callable[[PostgresCaseStore], Awaitable[None]]) -> None:
    from agent_app.storage import AgentDatabase

    async def main() -> None:
        database = AgentDatabase(url)
        try:
            await check(PostgresCaseStore(database, tenant_id="t", agent="dev"))
        finally:
            await database.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _case(key: str = "c1", user: str = "u1", **kw: object) -> CaseRecord:
    base = CaseRecord(
        id=0,
        kind="follow_up",
        key=key,
        channel="zalo-a",
        conversation_id=key,
        user_id=user,
        session_id="s1",
        goal="the customer books or says no",
        status="open",
        node="judge",
        state={"unanswered": 0},
        deadline=NOW + timedelta(days=14),
        created_at=NOW,
        updated_at=NOW,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def test_opening_is_idempotent_while_the_case_is_live(db_url: str) -> None:
    async def check(store: PostgresCaseStore) -> None:
        first, created = await store.open("demo", _case())
        again, created_again = await store.open("demo", _case())
        assert (created, created_again, again.id) == (True, False, first.id)
        closed = await store.save(replace(first, status="done", end_reason="booked", closed_at=NOW))
        assert closed is not None
        third, created_third = await store.open("demo", _case())
        assert created_third
        assert third.id != first.id

    _run(db_url, check)


def test_only_open_and_due_cases_come_back_and_a_stale_save_is_refused(db_url: str) -> None:
    async def check(store: PostgresCaseStore) -> None:
        opened, _ = await store.open("demo", _case("a"))
        later, _ = await store.open("demo", _case("b"))
        waiting = await store.save(
            replace(later, status="waiting", wait_for="clock", wake_at=NOW + timedelta(hours=1))
        )
        assert waiting is not None
        assert [c.key for c in await store.due(NOW, 10)] == ["a"]
        assert {c.key for c in await store.due(NOW + timedelta(hours=1), 10)} == {"a", "b"}

        saved = await store.save(replace(opened, state={"unanswered": 1}))
        assert saved is not None
        assert saved.version == opened.version + 1
        assert await store.save(replace(opened, goal="stale")) is None
        current = await store.get(opened.id)
        assert current is not None
        assert current.state == {"unanswered": 1}

    _run(db_url, check)


def test_the_log_counts_what_each_person_was_sent(db_url: str) -> None:
    async def check(store: PostgresCaseStore) -> None:
        mine, _ = await store.open("demo", _case("a", "u1"))
        other, _ = await store.open("demo", _case("b", "u2"))
        await store.log(mine.id, "sent", "write", {"note": ""}, NOW - timedelta(days=1))
        await store.log(mine.id, "sent", "write", {"note": ""}, NOW)
        await store.log(mine.id, "decision", "write", {"long": "x" * 5000}, NOW)
        await store.log(other.id, "sent", "write", {}, NOW)
        assert await store.sent_since("zalo-a", "u1", NOW - timedelta(hours=1)) == 1
        events = await store.events(mine.id)
        assert [e["kind"] for e in events] == ["sent", "sent", "decision"]
        assert "cut" in events[-1]["detail"]
        assert [c.key for c in await store.waiting_in_chat("zalo-a", "a")] == []

    _run(db_url, check)


def test_the_settings_of_cases_have_their_columns(migrated: tuple[str, Engine]) -> None:
    with migrated[1].begin() as conn:
        conn.execute(
            sql(
                "INSERT INTO agent_rt.agent_settings (tenant_id, agent, cases_enabled, proactive_per_person_per_day) "
                "VALUES ('t', 'cases-test', true, 3)"
            )
        )
        with pytest.raises(IntegrityError, match="agent_settings_proactive_cap"), conn.begin_nested():
            conn.execute(
                sql(
                    "UPDATE agent_rt.agent_settings SET proactive_per_person_per_day = 21 "
                    "WHERE agent = 'cases-test'"
                )
            )
        conn.execute(sql("DELETE FROM agent_rt.agent_settings WHERE agent = 'cases-test'"))


def test_a_decision_is_kept_for_its_turn_and_chat_without_touching_the_version(db_url: str) -> None:
    async def check(store: PostgresCaseStore) -> None:
        case, _ = await store.open("demo", _case())
        decision = {"done": "booked", "note": "booked"}
        assert await store.set_pending(case.id, 0, "zalo-a", "c1", decision)
        assert not await store.set_pending(case.id, 1, "zalo-a", "c1", decision)  # not that turn
        assert not await store.set_pending(case.id, 0, "zalo-a", "c9", decision)  # not that chat
        assert await store.pending(case.id, 0) == decision
        assert await store.pending(case.id, 1) is None
        current = await store.get(case.id)
        assert current is not None
        assert current.version == case.version
        saved = await store.save(replace(case, turns=1))
        assert saved is not None
        assert not await store.set_pending(case.id, 0, "zalo-a", "c1", decision)  # moved on

    _run(db_url, check)
