"""Postgres storage of notes and agent-written skills (schema ``agent_rt``). Needs ``PEMA_TEST_DATABASE_URL``
(a throwaway database; the schema is dropped and migrated again); skipped otherwise.

Each test runs its async part on a selector event loop: psycopg's async driver cannot use the Windows proactor
loop pytest-asyncio would give it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import text as sql
from sqlalchemy.exc import IntegrityError

from agent_app.storage import AgentDatabase, PostgresMemoryBackend, PostgresSkillStore
from agentcore.memory import MemoryKey, MemoryService, StoredNotes
from agentcore.skills import SkillLibrary

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[1]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
AGENT = MemoryKey("t", "dev", "agent")
USER = MemoryKey("t", "dev", "user", "u1")


def _migrate(url: str, revision: str, *, down: bool = False) -> None:
    previous = os.environ.get(MIGRATION_ENV)
    os.environ[MIGRATION_ENV] = url
    try:
        config = Config(str(APP_DIR / "alembic.ini"))
        if down:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        if previous is None:
            os.environ.pop(MIGRATION_ENV, None)
        else:
            os.environ[MIGRATION_ENV] = previous


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[str, Engine]]:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(sql("DROP SCHEMA IF EXISTS agent_rt CASCADE"))
        conn.execute(sql("DROP TABLE IF EXISTS public.alembic_version_agent_rt"))
    _migrate(url, "head")
    yield url, engine
    engine.dispose()


@pytest.fixture
def admin(migrated: tuple[str, Engine]) -> tuple[str, Engine]:
    with migrated[1].begin() as conn:
        conn.execute(sql("TRUNCATE agent_rt.agent_memory, agent_rt.agent_skill"))
    return migrated


def _run(url: str, check: Callable[[AgentDatabase], Awaitable[None]]) -> None:
    async def main() -> None:
        database = AgentDatabase(url)
        try:
            await check(database)
        finally:
            await database.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def test_notes_are_written_only_over_the_version_that_was_read(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        backend = PostgresMemoryBackend(db)
        assert await backend.load(AGENT) == StoredNotes()
        assert await backend.save(AGENT, "first", 0)
        assert not await backend.save(AGENT, "lost race", 0)
        assert await backend.save(AGENT, "second", 1)
        assert not await backend.save(AGENT, "stale", 1)
        assert await backend.load(AGENT) == StoredNotes(text="second", version=2)

    _run(admin[0], check)


def test_the_memory_service_keeps_tenants_and_users_apart_in_postgres(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        service = MemoryService(PostgresMemoryBackend(db))
        await service.add(USER, "prefers mornings")
        await service.add(MemoryKey("t", "dev", "user", "u2"), "prefers evenings")
        await service.add(MemoryKey("other", "dev", "agent"), "other tenant")
        await service.replace(USER, "mornings", "prefers early mornings")

        snapshot = await service.snapshot("t", "dev", "u1")
        assert (snapshot.agent_notes, snapshot.user_notes) == ((), ("prefers early mornings",))

    _run(admin[0], check)


def test_the_database_refuses_a_user_id_on_agent_notes(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        with pytest.raises(IntegrityError):
            await PostgresMemoryBackend(db).save(MemoryKey("t", "dev", "agent", "u1"), "x", 0)

    _run(admin[0], check)


def test_agent_skills_are_stored_listed_and_overwritten(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSkillStore(db)
        library = SkillLibrary(store)
        await library.write("t", "dev", name="reply-style", description="How to reply.", body="Be brief.")
        await library.write("t", "dev", name="a-first", description="First.", body="One.")
        patched = await library.patch("t", "dev", name="reply-style", old_text="brief", new_text="kind")

        assert [s.name for s in await store.list("t", "dev")] == ["a-first", "reply-style"]
        assert await store.get("t", "dev", "reply-style") == patched
        assert await store.list("other", "dev") == []

    _run(admin[0], check)
    with admin[1].connect() as conn:
        version = conn.execute(
            sql("SELECT version FROM agent_rt.agent_skill WHERE name = 'reply-style'")
        ).scalar()
    assert version == 2


def test_the_database_refuses_a_skill_the_core_would_refuse(admin: tuple[str, Engine]) -> None:
    with pytest.raises(IntegrityError), admin[1].begin() as conn:
        conn.execute(
            sql(
                "INSERT INTO agent_rt.agent_skill (tenant_id, agent, name, description, body) "
                "VALUES ('t', 'dev', 'Bad Name', 'd', 'b')"
            )
        )


def test_the_migration_goes_down_and_up_again(admin: tuple[str, Engine]) -> None:
    url, engine = admin

    _migrate(url, "base", down=True)
    with engine.connect() as conn:
        gone = conn.execute(sql("SELECT to_regnamespace('agent_rt') IS NULL")).scalar()
    _migrate(url, "head")

    assert gone
