"""The durable inbound queue, conversations, session locks and the dispatcher on Postgres. Needs
``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated again); skipped otherwise.

Each test runs its async part on a selector event loop: psycopg's async driver cannot use the Windows proactor
loop.
"""

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
from sqlalchemy.engine import make_url

from agent_app.agent_settings import PostgresAgentSettingsStore, StoredAgentSettings
from agent_app.db_roles import RUNTIME_ROLE, bootstrap_role
from agent_app.dispatcher import DispatchSettings
from agent_app.follow_up import FollowUp, PostgresFollowUpStore
from agent_app.ingress import SessionBusyError, TurnReply
from agent_app.ingress_store import PostgresConversationStore, PostgresIngressStore, PostgresSessionLocks
from agent_app.model_entries import ModelEntry, PostgresModelEntryStore
from agent_app.model_settings import PostgresModelSettingsStore, StoredModelSettings
from agent_app.plugins.records import PostgresPluginRecords
from agent_app.plugins.state import PluginState, PostgresPluginStateStore
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
                "agent_rt.agent_model_settings, agent_rt.agent_model_entry, agent_rt.agent_settings, "
                "agent_rt.agent_follow_up, "
                "agent_rt.agent_plugin, "
                "agent_rt.agent_plugin_record"
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
    async def check(db: AgentDatabase) -> None:
        model = SlowEcho()
        runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=db)
        runtime.live.use_model(model)
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
    with engine.connect() as conn:  # roles belong to the whole cluster: never reset or drop a real one
        if conn.execute(sql("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first():
            pytest.skip(f"{RUNTIME_ROLE} exists on this server already; run this test on a server of its own")
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
                conn.execute(
                    sql(
                        "INSERT INTO agent_rt.agent_plugin (tenant_id, agent, name) "
                        "VALUES ('role-check', 'dev', 'p')"
                    )
                )
                conn.execute(
                    sql(
                        "INSERT INTO agent_rt.agent_plugin_record (tenant_id, agent, plugin, key, value) "
                        "VALUES ('role-check', 'dev', 'p', 'k', '1')"
                    )
                )
        finally:
            as_role.dispose()
    finally:
        with engine.begin() as conn:
            if conn.execute(sql("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first():
                conn.execute(sql(f"DROP OWNED BY {RUNTIME_ROLE}"))
                conn.execute(sql(f"DROP ROLE {RUNTIME_ROLE}"))


def test_plugin_state_is_stored_per_agent_and_every_change_moves_the_fingerprint(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresPluginStateStore(db, agent="dev")
        empty = await store.fingerprint("t")
        state = PluginState(
            "ping",
            enabled=False,
            config={"precision": 2, "note": "ở đây"},
            secrets_enc="sealed",
            install={"kind": "zip"},
            error="x",
        )

        await store.save("t", state)
        first = await store.fingerprint("t")
        await store.save("t", PluginState("ping", enabled=True))
        second = await store.fingerprint("t")

        assert len({empty, first, second}) == 3
        assert await store.list("t") == [PluginState("ping", enabled=True)]
        assert await PostgresPluginStateStore(db, agent="other").list("t") == []
        await store.save("t", state)
        assert await store.get("t", "ping") == state
        await store.delete("t", "ping")
        assert await store.get("t", "ping") is None
        assert await store.fingerprint("t") not in {first, second}

    _run(db_url, check)


def test_plugin_records_are_kept_per_tenant_agent_and_plugin(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        mine = PostgresPluginRecords(db, agent="dev", tenant_id="t").storage("chat")
        await mine.put("account:b", {"label": "Bé"})
        await mine.put("account:a", {"label": "A", "ids": [1, 2]})
        await mine.put("account:a", {"label": "A2"})
        await mine.put("contact%_", True)
        others = [
            PostgresPluginRecords(db, agent="dev", tenant_id="t").storage("other"),
            PostgresPluginRecords(db, agent="other", tenant_id="t").storage("chat"),
            PostgresPluginRecords(db, agent="dev", tenant_id="t2").storage("chat"),
        ]

        assert await mine.get("account:a") == {"label": "A2"}
        assert await mine.list("account:") == [("account:a", {"label": "A2"}), ("account:b", {"label": "Bé"})]
        assert await mine.list("contact%") == [("contact%_", True)]
        assert await mine.list("%") == []
        assert await mine.list(limit=1) == [("account:a", {"label": "A2"})]
        assert [await other.list() for other in others] == [[], [], []]
        assert (await mine.delete("account:a"), await mine.delete("account:a")) == (True, False)
        assert await mine.get("account:a") is None

    _run(db_url, check)


def test_a_change_through_one_process_reaches_another_through_postgres(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        profile = load_profile(DEV_PROFILE)
        one = build_runtime(profile, fake=True, env={}, db=db)
        two = build_runtime(profile, fake=True, env={}, db=db)
        await one.plugin_manager.start()
        await two.plugin_manager.start()

        await one.plugin_manager.disable("web")
        await two.plugin_manager.refresh(force=True)
        off = two.plugins.enabled()
        await one.plugin_manager.enable("web")
        await two.plugin_manager.refresh(force=True)

        assert "web" not in off
        assert "web" in two.plugins.enabled()

    _run(db_url, check)


def test_replies_are_claimed_in_order_retried_and_taken_over_on_postgres(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresIngressStore(db, agent="dev")
        first, _ = await store.accept("t", _inbound("d1", conversation="cd"), "s-d", deliver=True)
        second, _ = await store.accept("t", _inbound("d2", conversation="cd"), "s-d", deliver=True)
        plain, _ = await store.accept("t", _inbound("d3", conversation="other"), "s-x")
        not_over = await store.claim_delivery("t", first.id, stale_s=60)
        for record in (first, second):
            await store.claim(record.id)
            await store.finish(record.id, TurnReply("turn", "ok", "end", 1, Usage()))

        held = await store.claim_delivery("t", second.id, stale_s=60)
        due = await store.due_deliveries("t", ["http"], stale_s=60, limit=10)
        claimed = await store.claim_delivery("t", first.id, stale_s=60)
        busy = await store.claim_delivery("t", first.id, stale_s=60)
        taken = await store.claim_delivery("t", first.id, stale_s=0)
        await store.delivery_progress(first.id, 1)
        await store.retry_delivery(first.id, "busy", after_s=3600)
        waiting = await store.claim_delivery("t", first.id, stale_s=60)
        await store.retry_delivery(first.id, "busy", after_s=0)
        again = await store.claim_delivery("t", first.id, stale_s=60)
        await store.finish_delivery(first.id, "sent")
        after = await store.due_deliveries("t", ["http"], stale_s=60, limit=10)

        assert (first.delivery, plain.delivery) == ("pending", None)
        assert (not_over, held, busy, waiting) == (None, None, None, None)
        assert [r.id for r in due] == [first.id]
        assert claimed is not None
        assert (claimed.delivery, claimed.delivery_attempts) == ("sending", 1)
        assert taken is not None
        assert taken.delivery_attempts == 2
        assert again is not None
        assert (again.delivered_parts, again.delivery_error, again.delivery_attempts) == (1, "busy", 3)
        assert [r.id for r in after] == [second.id]
        assert await store.due_deliveries("t", ["zalo"], stale_s=60, limit=10) == []

    _run(db_url, check)


def test_collect_joins_waiting_messages_on_postgres(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=db)
        settings = DispatchSettings(queue_mode="collect", debounce_s=0.05, max_wait_s=0.5, poll_s=0.02)
        dispatcher = runtime.dispatcher(settings)
        records = [(await dispatcher.accept(_inbound(f"q{i}", f"part {i}", "cq")))[0] for i in range(3)]
        queued = await dispatcher.ingress.queued_in_session("default", records[0].session_id, 10)
        finished = [await dispatcher.wait(r.id, 5.0) for r in records]
        await dispatcher.close()
        runtime.close()

        assert [r.id for r in queued] == [r.id for r in records]
        assert {r.status for r in finished} == {"done"}
        assert {r.reply.text if r.reply else None for r in finished} == {"(echo) part 0\n\npart 1\n\npart 2"}

    _run(db_url, check)


def test_the_list_of_models_is_stored_per_agent_and_the_settings_remember_which_is_in_use(
    db_url: str,
) -> None:
    async def check(db: AgentDatabase) -> None:
        entries = PostgresModelEntryStore(db, agent="dev")
        first = ModelEntry(
            id="a" * 32, label="DeepSeek", provider="openai-compatible", model="m1", api_key_enc="s1"
        )
        second = ModelEntry(id="b" * 32, label="Claude", provider="anthropic", model="m2", reasoning="low")

        await entries.save("t", first)
        await entries.save("t", second)
        await entries.save("t", replace(first, model="m1b"))

        assert [e.label for e in await entries.list("t")] == ["DeepSeek", "Claude"]
        assert (await entries.get("t", first.id)) == replace(first, model="m1b")
        assert await PostgresModelEntryStore(db, agent="other").list("t") == []
        assert (await entries.delete("t", second.id), await entries.delete("t", second.id)) == (True, False)

        settings = PostgresModelSettingsStore(db, agent="dev")
        await settings.save("t", StoredModelSettings(model="m1b", entry_id=first.id))
        loaded = await settings.get("t")
        assert loaded is not None
        assert loaded.entry_id == first.id

    _run(db_url, check)


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


def test_agent_settings_are_stored_per_agent_and_a_clear_never_lowers_the_version(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresAgentSettingsStore(db, agent="dev")
        assert (await store.get("t"), await store.version("t")) == (None, 0)

        stored = StoredAgentSettings(
            timezone="Asia/Ho_Chi_Minh",
            persona="Xin chào {{clinic}}",
            memory_enabled=False,
            memory_agent_chars=500,
            follow_up_enabled=True,
            follow_up_channels=("zalo-a1", "zalo-b2"),
            variables={"clinic": "Pema"},
            tools={"web_fetch": True, "kb_search": False},
            updated_by="an@admin",
        )
        saved = await store.save("t", stored)
        loaded = await store.get("t")
        cleared = await store.save("t", StoredAgentSettings())

        assert saved == replace(stored, version=1)
        assert loaded == saved
        assert await PostgresAgentSettingsStore(db, agent="other").get("t") is None
        assert cleared.version == 2
        again = await store.get("t")
        assert again is not None
        assert (again.empty, again.version) == (True, 2)

    _run(db_url, check)


def test_the_database_refuses_agent_settings_outside_their_limits(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresAgentSettingsStore(db, agent="dev")
        for bad in (
            StoredAgentSettings(memory_agent_chars=5),
            StoredAgentSettings(failure_reply="x" * 1001),
            StoredAgentSettings(timezone=""),
        ):
            with pytest.raises(Exception, match="agent_settings"):
                await store.save("t", bad)
        assert await store.get("t") is None

    _run(db_url, check)


def _row(**kw: object) -> FollowUp:
    return replace(FollowUp(channel="zalo-a1", conversation_id="c1", user_id="u1", session_id="s1"), **kw)  # type: ignore[arg-type]


def test_a_follow_up_is_stored_per_agent_and_the_database_refuses_what_is_not_a_state(db_url: str) -> None:
    async def check(db: AgentDatabase) -> None:
        store = PostgresFollowUpStore(db, agent="dev")
        now = datetime.now(UTC).replace(microsecond=0)
        assert await store.get("t", "zalo-a1", "c1") is None

        row = _row(
            state="hesitant",
            reason="hỏi giá rồi im",
            next_at=now + timedelta(hours=3),
            paused_until=now + timedelta(days=7),
            unanswered=1,
            last_sent_at=now - timedelta(hours=30),
            reviewed_through=42,
        )
        await store.save("t", row)
        loaded = await store.get("t", "zalo-a1", "c1")
        await store.save("t", replace(row, state="done", next_at=None, stopped=True))
        again = await store.get("t", "zalo-a1", "c1")

        assert loaded is not None
        assert replace(loaded, updated_at=None) == row
        assert again is not None
        assert (again.state, again.next_at, again.stopped, again.reviewed_through) == ("done", None, True, 42)
        assert await PostgresFollowUpStore(db, agent="other").get("t", "zalo-a1", "c1") is None
        assert [r.conversation_id for r in await store.list("t")] == ["c1"]
        for bad in (_row(state="angry"), _row(reason="x" * 501), _row(unanswered=-1)):  # type: ignore[arg-type]
            with pytest.raises(Exception, match="agent_follow_up"):
                await store.save("t", bad)

    _run(db_url, check)


_INSERT = sql(
    "INSERT INTO agent_rt.agent_ingress (tenant_id, agent, channel, external_id, conversation_id, user_id, "
    "session_id, text, metadata, status, reply, received_at, delivery, delivery_at) "
    "VALUES ('t', 'dev', :channel, :external_id, :conversation_id, 'u1', :session_id, :text, "
    "CAST(:metadata AS jsonb), :status, CAST(:reply AS jsonb), :at, :delivery, :delivery_at) RETURNING id"
)


def test_a_quiet_conversation_is_one_whose_last_reply_went_out_and_was_not_answered(db_url: str) -> None:
    """Only one-to-one chats of the chosen channels; the last message decides; what the customer wrote since the
    last judgement comes along; the loop's own messages are not the customer's."""

    async def check(db: AgentDatabase) -> None:
        now = datetime.now(UTC)
        reply = '{"turn_id": "x", "text": "ok", "stop": "end", "steps": 1, "usage": {}}'

        async def add(
            conv: str,
            text: str,
            *,
            channel: str = "zalo-a1",
            ago: float = 3.0,
            group: bool = False,
            done: bool = True,
            external: str | None = None,
        ) -> int:
            async with db.engine.begin() as conn:
                found = await conn.execute(
                    _INSERT,
                    {
                        "channel": channel,
                        "external_id": external or f"{conv}-{text}",
                        "conversation_id": conv,
                        "session_id": f"s-{conv}",
                        "text": text,
                        "metadata": '{"thread_type": "group"}' if group else '{"thread_type": "user"}',
                        "status": "done" if done else "queued",
                        "reply": reply if done else None,
                        "at": now - timedelta(hours=ago + 0.1),
                        "delivery": "sent" if done else "pending",
                        "delivery_at": now - timedelta(hours=ago) if done else None,
                    },
                )
                return found.scalar_one()

        await add("answered-long-ago", "hello", ago=3)
        await add("recent", "hello", ago=0.5)
        await add("group", "hello", group=True)
        await add("other-channel", "hello", channel="zalo-zzz")
        await add("customer-wrote-last", "first", ago=5)
        await add("customer-wrote-last", "again", done=False, ago=0.2)
        await add("too-old", "hello", ago=72)
        reviewed = await add("reviewed", "hello", ago=4)
        newer = await add("reviewed", "second question", ago=3)
        await add("loops-own-message", "price?", ago=26)
        await add("loops-own-message", "[instruction]", ago=3, external="followup:1:1")

        store = PostgresFollowUpStore(db, agent="dev")
        await store.save("t", _row(conversation_id="reviewed", state="done", reviewed_through=reviewed))
        found = await store.quiet("t", ["zalo-a1"], now - timedelta(hours=2), now - timedelta(hours=26), 10)

        by_conv = {q.conversation_id: q for q in found}
        assert set(by_conv) == {"answered-long-ago", "reviewed", "loops-own-message"}, sorted(by_conv)
        assert by_conv["loops-own-message"].customer_texts == (
            "price?",
        )  # the loop's own message is not the customer's
        assert by_conv["answered-long-ago"].customer_texts == ("hello",)
        assert (by_conv["reviewed"].customer_texts, by_conv["reviewed"].last_id) == (
            ("second question",),
            newer,
        )
        assert by_conv["answered-long-ago"].session_id == "s-answered-long-ago"
        limited = await store.quiet("t", ["zalo-a1"], now - timedelta(hours=2), now - timedelta(hours=26), 1)
        assert len(limited) == 1

        widened = await store.quiet(
            "t", ["zalo-a1"], now - timedelta(hours=2), now - timedelta(hours=100), 10
        )
        assert "too-old" in {q.conversation_id for q in widened}
        assert await store.quiet("t", [], now, now - timedelta(days=1), 10) == []

    _run(db_url, check)
