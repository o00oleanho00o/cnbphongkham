"""The durable inbound queue, conversations, session locks and the dispatcher on Postgres. Needs
``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated again); skipped otherwise.

Each test runs its async part on a selector event loop: psycopg's async driver cannot use the Windows proactor
loop.
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
from sqlalchemy.engine import make_url

from agent_app.db_roles import RUNTIME_ROLE, bootstrap_role
from agent_app.dispatcher import DispatchSettings
from agent_app.ingress import SessionBusyError, TurnReply
from agent_app.ingress_store import PostgresConversationStore, PostgresIngressStore, PostgresSessionLocks
from agent_app.model_settings import PostgresModelSettingsStore, StoredModelSettings
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime
from agent_app.storage import AgentDatabase
from agentcore import AssistantResult, LlmRequest, Message, StreamSink, TextBlock, Usage
from agentcore.channels import InboundMessage

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[1]
DEV_PROFILE = APP_DIR / "agents" / "dev"
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"


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
            sql(
                "TRUNCATE agent_rt.agent_ingress, agent_rt.agent_conversation, agent_rt.agent_session, "
                "agent_rt.agent_message, agent_rt.agent_turn, agent_rt.agent_turn_event, agent_rt.agent_memory, "
                "agent_rt.agent_model_settings"
            )
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


def _inbound(message_id: str, text: str = "hi", conversation: str = "c1") -> InboundMessage:
    return InboundMessage("http", conversation, "u1", message_id, text, {"source": "test"})


def test_a_message_is_stored_once_and_claimed_by_one_run(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresIngressStore(db, agent="dev")
        first, created = await store.accept("t", _inbound("m1"), "dev:http:c1:0")
        again, created_again = await store.accept("t", _inbound("m1", "changed"), "dev:http:c1:0")
        assert (created, created_again) == (True, False)
        assert again == first
        assert (first.status, first.metadata) == ("queued", {"source": "test"})
        assert await store.get("other-tenant", first.id) is None
        assert await PostgresIngressStore(db, agent="other").get("t", first.id) is None

        claimed = await store.claim(first.id)
        assert claimed is not None
        assert (claimed.status, claimed.attempts) == ("processing", 1)
        assert await store.claim(first.id) is None
        reply = TurnReply("turn-1", "xin chào", "completed", 1, Usage(input_tokens=3, output_tokens=2))
        await store.finish(first.id, reply)
        done = await store.get("t", first.id)
        assert done is not None
        assert (done.status, done.reply) == ("done", reply)

    _run(db_url, check)


def test_the_queue_runs_oldest_first_and_gives_up_on_a_message_that_keeps_crashing(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresIngressStore(db, agent="dev")
        a, _ = await store.accept("t", _inbound("a"), "s1")
        b, _ = await store.accept("t", _inbound("b"), "s1")
        await store.accept("t", _inbound("c", conversation="c2"), "s2")
        assert await store.queued_sessions() == [("t", "s1"), ("t", "s2")]
        oldest = await store.next_queued("t", "s1")
        assert oldest is not None
        assert oldest.id == a.id

        await store.claim(a.id)
        assert [r.id for r in await store.processing()] == [a.id]
        assert await store.requeue(a.id, max_attempts=2) == "queued"
        await store.claim(a.id)
        assert await store.requeue(a.id, max_attempts=2) == "dead"
        assert await store.requeue(a.id, max_attempts=2) is None
        dead = await store.get("t", a.id)
        assert dead is not None
        assert (dead.status, dead.error_kind, dead.attempts) == ("dead", "interrupted", 2)
        await store.claim(b.id)
        await store.fail(b.id, "rate_limit")
        failed = await store.get("t", b.id)
        assert failed is not None
        assert (failed.status, failed.error_kind) == ("failed", "rate_limit")

    _run(db_url, check)


def test_starting_a_conversation_over_bumps_its_epoch(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        conversations = PostgresConversationStore(db, agent="dev")
        assert await conversations.epoch("t", "http", "c1") == 0
        assert await conversations.reset("t", "http", "c1") == 1
        assert await conversations.reset("t", "http", "c1") == 2
        assert await conversations.epoch("t", "http", "c1") == 2
        assert await conversations.epoch("t", "zalo", "c1") == 0
        assert await PostgresConversationStore(db, agent="other").epoch("t", "http", "c1") == 0

    _run(db_url, check)


def test_a_session_lock_is_held_across_connections(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        locks = PostgresSessionLocks(db)
        async with locks.hold("t", "s1", timeout_s=None):
            with pytest.raises(SessionBusyError):
                async with locks.hold("t", "s1", timeout_s=0):
                    pass
            with pytest.raises(SessionBusyError):
                async with locks.hold("t", "s1", timeout_s=0.3):
                    pass
            async with locks.hold("t", "s2", timeout_s=0):
                pass
        async with locks.hold("t", "s1", timeout_s=0):
            pass

    _run(db_url, check)


class SlowEcho:
    """Echoes after a short pause and records how many runs overlap."""

    def __init__(self) -> None:
        self.running = 0
        self.peak = 0

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.running += 1
        self.peak = max(self.peak, self.running)
        await asyncio.sleep(0.05)
        self.running -= 1
        text = (
            next(m for m in reversed(request.messages) if m.role == "user").text().split("<agent-context>")[0]
        )
        message = Message(role="assistant", blocks=[TextBlock(text=f"echo:{text.strip()}")], usage=Usage())
        return AssistantResult(message=message, stop_reason="end")


def test_the_dispatcher_runs_one_conversation_in_order_and_stores_everything(db_url: str) -> None:
    from dataclasses import replace

    async def check(db: AgentDatabase) -> None:
        model = SlowEcho()
        runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=db)
        runtime = replace(runtime, agent=replace(runtime.agent, model=model))
        dispatcher = runtime.dispatcher(DispatchSettings(poll_s=0.02))
        records = [(await dispatcher.accept(_inbound(f"m{i}", f"tin {i}")))[0] for i in range(3)]
        finished = [await dispatcher.wait(r.id, 5.0) for r in records]
        await dispatcher.close()

        assert [r.status for r in finished] == ["done", "done", "done"]
        assert [r.reply.text for r in finished if r.reply] == ["echo:tin 0", "echo:tin 1", "echo:tin 2"]
        assert model.peak == 1
        history = await runtime.store.load("default", "dev:http:c1:0")
        assert [m.text() for m in history] == [
            "tin 0",
            "echo:tin 0",
            "tin 1",
            "echo:tin 1",
            "tin 2",
            "echo:tin 2",
        ]

    _run(db_url, check)


def test_the_runtime_role_can_queue_messages(migrated: tuple[str, Engine]) -> None:
    url, engine = migrated
    password = "test-only-password-4567"
    try:
        done = bootstrap_role(url, password)
        assert "granted SELECT, INSERT, UPDATE, DELETE on agent_rt.agent_ingress" in done
        as_role = create_engine(make_url(url).set(username=RUNTIME_ROLE, password=password))
        try:
            with as_role.begin() as conn:
                conn.execute(
                    sql(
                        "INSERT INTO agent_rt.agent_ingress (tenant_id, agent, channel, external_id, "
                        "conversation_id, user_id, session_id, text) "
                        "VALUES ('t', 'dev', 'http', 'role-check', 'c', 'u', 's', 'hi')"
                    )
                )
                conn.execute(
                    sql(
                        "INSERT INTO agent_rt.agent_conversation (tenant_id, agent, channel, conversation_id) "
                        "VALUES ('t', 'dev', 'http', 'role-check')"
                    )
                )
                conn.execute(
                    sql(
                        "INSERT INTO agent_rt.agent_model_settings (tenant_id, agent, model) "
                        "VALUES ('role-check', 'dev', 'm')"
                    )
                )
        finally:
            as_role.dispose()
    finally:
        with engine.begin() as conn:
            if conn.execute(sql("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first():
                conn.execute(sql(f"DROP OWNED BY {RUNTIME_ROLE}"))
                conn.execute(sql(f"DROP ROLE {RUNTIME_ROLE}"))


def test_model_settings_are_stored_per_agent_and_a_clear_never_lowers_the_version(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresModelSettingsStore(db, agent="dev")
        assert (await store.get("t"), await store.version("t")) == (None, 0)

        saved = await store.save(
            "t", StoredModelSettings(provider="anthropic", model="m1", reasoning="low", api_key_enc="sealed")
        )
        cleared = await store.save("t", StoredModelSettings())

        assert saved.version == 1
        assert await PostgresModelSettingsStore(db, agent="other").get("t") is None
        assert cleared.version == 2
        loaded = await store.get("t")
        assert loaded == StoredModelSettings(version=2)
        assert loaded is not None
        assert loaded.empty

    _run(db_url, check)
