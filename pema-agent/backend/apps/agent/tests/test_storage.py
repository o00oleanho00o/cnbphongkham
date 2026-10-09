"""Postgres storage of schema ``agent_rt``: notes, agent-written skills, sessions, the turn trace and the
runtime role. Needs ``PEMA_TEST_DATABASE_URL`` (a throwaway database where the user may create roles; the
schema is dropped and migrated again); skipped otherwise.

Each test runs its async part on a selector event loop: psycopg's async driver cannot use the Windows proactor
loop pytest-asyncio would give it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy import text as sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError

from agent_app.db_roles import RUNTIME_ROLE, bootstrap_role
from agent_app.storage import (
    AgentDatabase,
    PostgresMemoryBackend,
    PostgresSessionStore,
    PostgresSkillStore,
    PostgresTracer,
    SessionOwnerError,
)
from agentcore import (
    AssistantResult,
    CompactionRecord,
    LlmRequest,
    Message,
    ModelError,
    PromptBuilder,
    StoredPrompt,
    TextBlock,
    ThinkingBlock,
    ToolRegistry,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    run_turn,
)
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call
from agentcore.harness.tools.builtin import builtin_tools
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
        conn.execute(
            sql(
                "TRUNCATE agent_rt.agent_memory, agent_rt.agent_skill, agent_rt.agent_session, "
                "agent_rt.agent_message, agent_rt.agent_turn, agent_rt.agent_turn_event"
            )
        )
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


HISTORY = [
    Message.user("Xin chào, mấy giờ rồi?"),
    Message(
        role="assistant",
        blocks=[
            ThinkingBlock(text="cần giờ", provider="deepseek"),
            ToolUseBlock(id="c1", name="get_datetime", args={"timezone": "Asia/Ho_Chi_Minh"}),
        ],
        usage=Usage(input_tokens=10, output_tokens=3, cache_read_tokens=8),
    ),
    Message(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", name="get_datetime", content="14:00")]),
    Message(role="assistant", blocks=[TextBlock(text="Bây giờ là 14:00.")]),
]


def test_a_session_survives_a_new_process(admin: tuple[str, Engine]) -> None:
    async def write(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        await store.open_session("t", "s1", channel="cli", user_id="u1")
        for message in HISTORY:
            await store.append("t", "s1", message)
        await store.save_prompt("t", "s1", StoredPrompt(text="system", fingerprint="f1"))
        await store.save_compaction("t", "s1", CompactionRecord(summary="## Goal\ntime", first_kept=2))

    async def read(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        info = await store.open_session("t", "s1", channel="http", user_id="someone else")
        assert (info.channel, info.user_id, info.message_count) == ("cli", "u1", 4)
        assert await store.load("t", "s1") == HISTORY
        assert await store.load_prompt("t", "s1") == StoredPrompt(text="system", fingerprint="f1")
        assert await store.load_compaction("t", "s1") == CompactionRecord(
            summary="## Goal\ntime", first_kept=2
        )
        assert await store.load("other-tenant", "s1") == []
        assert await store.load_prompt("t", "new") is None

    _run(admin[0], write)
    _run(admin[0], read)


def test_the_prompt_can_be_frozen_before_the_first_message(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        await store.save_prompt("t", "s1", StoredPrompt(text="system", fingerprint="f1"))
        await store.append("t", "s1", Message.user("hi"))

        assert await store.load("t", "s1") == [Message.user("hi")]
        assert await store.load_compaction("t", "s1") is None

    _run(admin[0], check)


def test_a_nul_character_is_stored_as_a_replacement_character(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        await store.append("t", "s1", Message.user("a\x00b \\u0000 kept"))

        (message,) = await store.load("t", "s1")
        assert message.text() == "a\ufffdb \\u0000 kept"

    _run(admin[0], check)


def test_concurrent_appends_get_consecutive_numbers(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        await asyncio.gather(*(store.append("t", "s1", Message.user(str(i))) for i in range(20)))

        loaded = await store.load("t", "s1")
        assert sorted(int(m.text()) for m in loaded) == list(range(20))

    _run(admin[0], check)
    with admin[1].connect() as conn:
        seqs = conn.execute(sql("SELECT seq FROM agent_rt.agent_message ORDER BY seq")).scalars().all()
        count = conn.execute(sql("SELECT message_count FROM agent_rt.agent_session")).scalar()
    assert (list(seqs), count) == (list(range(1, 21)), 20)


def test_another_agents_session_is_refused_and_never_read(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        mine = PostgresSessionStore(db, agent="dev")
        theirs = PostgresSessionStore(db, agent="other")
        await mine.append("t", "s1", Message.user("private"))
        await mine.save_compaction("t", "s1", CompactionRecord(summary="x", first_kept=1))

        with pytest.raises(SessionOwnerError):
            await theirs.open_session("t", "s1", channel=None, user_id=None)
        with pytest.raises(SessionOwnerError):
            await theirs.append("t", "s1", Message.user("intruder"))
        with pytest.raises(SessionOwnerError):
            await theirs.save_prompt("t", "s1", StoredPrompt(text="x", fingerprint="y"))
        with pytest.raises(SessionOwnerError):
            await theirs.save_compaction("t", "s1", CompactionRecord(summary="y", first_kept=1))
        assert await theirs.load("t", "s1") == []
        assert await theirs.load_compaction("t", "s1") is None
        assert [m.text() for m in await mine.load("t", "s1")] == ["private"]

    _run(admin[0], check)


def test_recent_sessions_are_listed_newest_first(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        await store.append("t", "old", Message.user("1"))
        await store.append("t", "new", Message.user("1"))
        await store.append("t", "new", Message.user("2"))
        await PostgresSessionStore(db, agent="other").append("t", "theirs", Message.user("1"))

        listed = await store.list_sessions("t", limit=5)
        assert [(s.session_id, s.message_count) for s in listed] == [("new", 2), ("old", 1)]

    _run(admin[0], check)


NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)


def test_a_turn_trace_is_stored_and_read_back(admin: tuple[str, Engine]) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresSessionStore(db, agent="dev")
        tracer = PostgresTracer(db, agent="dev", model="m1")
        model = ScriptedModel(
            [
                calls(tool_call("get_datetime", {}, call_id="c1")),
                reply("done", input_tokens=9, output_tokens=2),
            ]
        )

        result = await run_turn(
            session_id="s1",
            user_text="time?",
            prompt=PromptBuilder.fixed("sys"),
            model=model,
            tools=builtin_tools(),
            store=store,
            tenant_id="t",
            user_id="u1",
            channel="cli",
            tracer=tracer,
            clock=lambda: NOW,
        )

        saved = await tracer.last("t", "s1")
        assert saved is not None
        assert saved.turn_id == result.turn_id
        assert (saved.stop, saved.steps, saved.started_at, saved.user_id) == ("completed", 2, NOW, "u1")
        assert (saved.usage.input_tokens, saved.usage.output_tokens) == (9, 2)
        assert [(e.kind, e.step, e.name, e.is_error) for e in saved.events] == [
            ("model_call", 1, "", False),
            ("tool_call", 1, "get_datetime", False),
            ("model_call", 2, "", False),
        ]
        assert saved.events[1].detail["call_id"] == "c1"
        assert await tracer.last("t", "other") is None
        assert await PostgresTracer(db, agent="other", model="m1").last("t", "s1") is None

    _run(admin[0], check)
    with admin[1].connect() as conn:
        model = conn.execute(sql("SELECT model FROM agent_rt.agent_turn")).scalar()
    assert model == "m1"


def test_a_failed_turn_is_traced_even_without_a_session_row(admin: tuple[str, Engine]) -> None:
    def down(request: LlmRequest) -> AssistantResult:
        raise ModelError("transient", "overloaded")

    async def check(db: AgentDatabase) -> None:
        tracer = PostgresTracer(db, agent="dev", model="m1")
        with pytest.raises(ModelError):
            await run_turn(
                session_id="s1",
                user_text="hi",
                prompt=PromptBuilder.fixed("sys"),
                model=ScriptedModel([down]),
                tools=ToolRegistry(),
                store=PostgresSessionStore(db, agent="dev"),
                tenant_id="t",
                tracer=tracer,
            )
        trace = await tracer.last("t", "s1")
        assert trace is not None
        assert (trace.stop, trace.error_kind, trace.steps) == ("error", "transient", 1)
        await tracer.record(trace)  # a retried write keeps one row

    _run(admin[0], check)
    with admin[1].connect() as conn:
        turns = conn.execute(sql("SELECT count(*) FROM agent_rt.agent_turn")).scalar()
    assert turns == 1


def _as_role(url: str, password: str) -> Engine:
    return create_engine(make_url(url).set(username=RUNTIME_ROLE, password=password))


def _check_runtime_rights(url: str, password: str) -> None:
    engine = _as_role(url, password)
    try:
        with engine.begin() as conn:
            conn.execute(
                sql(
                    "INSERT INTO agent_rt.agent_memory (tenant_id, agent, target, content, version) "
                    "VALUES ('t', 'dev', 'agent', 'note', 1)"
                )
            )
            conn.execute(sql("DELETE FROM agent_rt.agent_memory"))
            conn.execute(
                sql(
                    "INSERT INTO agent_rt.agent_turn (turn_id, tenant_id, session_id, agent, model, started_at, "
                    "duration_ms, stop, steps, compactions, input_tokens, output_tokens, cache_read_tokens, "
                    "cache_write_tokens, reasoning_tokens) VALUES (gen_random_uuid(), 't', 's', 'dev', 'm', "
                    "now(), 1, 'completed', 1, 0, 0, 0, 0, 0, 0)"
                )
            )
        for refused in (
            "CREATE TABLE agent_rt.sneaky (x int)",
            "UPDATE agent_rt.agent_turn SET steps = 2",
            "DELETE FROM agent_rt.agent_turn",
            "DROP TABLE agent_rt.agent_message",
        ):
            with (
                pytest.raises(ProgrammingError, match=r"permission denied|must be owner"),
                engine.begin() as conn,
            ):
                conn.execute(sql(refused))
    finally:
        engine.dispose()


def test_the_runtime_role_can_use_the_data_but_not_change_the_schema_or_the_trace(
    admin: tuple[str, Engine],
) -> None:
    url, engine = admin
    password = "test-only-password-0123"
    try:
        done = bootstrap_role(url, password)
        assert "granted SELECT, INSERT on agent_rt.agent_turn" in done
        _check_runtime_rights(url, password)

        _migrate(url, "0001_agent_rt", down=True)
        _migrate(url, "head")  # the migration grants on its own when the role exists
        _check_runtime_rights(url, password)
    finally:
        with engine.begin() as conn:
            if conn.execute(sql("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first():
                conn.execute(sql(f"DROP OWNED BY {RUNTIME_ROLE}"))
                conn.execute(sql(f"DROP ROLE {RUNTIME_ROLE}"))
