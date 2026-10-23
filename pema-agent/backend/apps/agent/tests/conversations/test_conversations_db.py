"""The conversations store on Postgres: its tables made by ``migrate-plugins``, a message kept once, the counts that
follow it, search, who wrote in a channel, the roles given again, old messages deleted, and each tenant seeing only
its own. Needs ``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated again); skipped
otherwise.

The async part runs on a selector event loop: psycopg's async driver cannot use the Windows proactor loop.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import create_async_engine

from agent_app.plugins import discover
from agent_app.plugins.migrations import migrate_plugins
from agent_app.runtime import BUNDLED_PLUGINS
from plugins.conversations.models import NewMessage, Origin, Role, conversation_id
from plugins.conversations.store import PostgresConversationStore

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[2]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
NOW = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)
CHANNEL = "zalo-a"


@pytest.fixture(scope="module")
def db_url() -> str:
    url = os.environ.get("PEMA_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(sql("DROP SCHEMA IF EXISTS agent_rt CASCADE"))
        conn.execute(sql("DROP TABLE IF EXISTS public.alembic_version_agent_rt"))
    engine.dispose()
    previous = os.environ.get(MIGRATION_ENV)
    os.environ[MIGRATION_ENV] = url
    try:
        command.upgrade(Config(str(APP_DIR / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop(MIGRATION_ENV, None)
        else:
            os.environ[MIGRATION_ENV] = previous
    migrate_plugins(url, [discover([("bundled", BUNDLED_PLUGINS)]).plugins["conversations"]])
    return url


def _run(
    url: str, work: Callable[[PostgresConversationStore, PostgresConversationStore], Awaitable[None]]
) -> None:
    async def main() -> None:
        engine = create_async_engine(url)
        try:
            await work(
                PostgresConversationStore(engine, tenant_id="clinic-a", agent="clinic"),
                PostgresConversationStore(engine, tenant_id="clinic-b", agent="clinic"),
            )
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _said(
    text: str,
    *,
    thread: str = "t1",
    message_id: str = "m1",
    sender: str = "u1",
    name: str = "Lan",
    role: Role = "customer",
    origin: Origin = "inbound",
    at: datetime = NOW,
) -> NewMessage:
    return NewMessage(
        conversation_id=conversation_id(CHANNEL, thread),
        channel=CHANNEL,
        external_id=thread,
        is_group=False,
        title_hint=name if role == "customer" else "",
        message_id=message_id,
        sender_id=sender,
        sender_name=name,
        role=role,
        origin=origin,
        at=at,
        text=text,
    )


def test_a_message_is_kept_once_and_the_conversation_counts_it(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        assert await mine.add(_said("giá niềng răng?", thread="once")) is True
        assert await mine.add(_said("giá niềng răng?", thread="once")) is False
        assert (
            await mine.add(
                _said(
                    "dạ 2 triệu",
                    thread="once",
                    message_id="m2",
                    sender="me",
                    role="staff",
                    origin="own",
                    at=NOW + timedelta(minutes=1),
                )
            )
            is True
        )

        (found, total) = await mine.conversations(channel=CHANNEL, query="", limit=50, offset=0)
        once = next(c for c in found if c.external_id == "once")
        messages = await mine.messages(once.id, limit=10)

        assert total >= 1
        assert (once.message_count, once.title, once.first_at, once.last_at) == (
            2,
            "Lan",
            NOW,
            NOW + timedelta(minutes=1),
        )
        assert [(m.role, m.text) for m in messages] == [
            ("customer", "giá niềng răng?"),
            ("staff", "dạ 2 triệu"),
        ]
        assert await theirs.get(once.id) is None

    _run(db_url, work)


def test_search_finds_a_word_in_a_message_or_a_title_and_wildcards_are_plain_text(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        await mine.add(_said("Tôi muốn 100% hài lòng", thread="s1", name="Hùng"))
        await mine.add(_said("đặt lịch khám", thread="s2", name="Mai"))

        by_message, _ = await mine.conversations(channel=CHANNEL, query="hài lòng", limit=10, offset=0)
        by_title, _ = await mine.conversations(channel=CHANNEL, query="mai", limit=10, offset=0)
        percent, _ = await mine.conversations(channel=CHANNEL, query="%", limit=10, offset=0)
        underscore, _ = await mine.conversations(channel=CHANNEL, query="_", limit=10, offset=0)

        assert [c.external_id for c in by_message] == ["s1"]
        assert [c.external_id for c in by_title] == ["s2"]
        assert [c.external_id for c in percent] == ["s1"]
        assert underscore == []

    _run(db_url, work)


def test_people_and_relabel_follow_who_is_staff(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        await mine.add(_said("a", thread="p1", message_id="m1", sender="x1", name="Xuân"))
        await mine.add(_said("b", thread="p1", message_id="m2", sender="x1", name="Xuân"))
        await mine.add(_said("c", thread="p2", message_id="m3", sender="x2", name="Yến"))
        await mine.add(_said("d", thread="p1", message_id="m4", sender="me", role="staff", origin="own"))

        people = [
            (p.sender_id, p.messages, p.role)
            for p in await mine.people(CHANNEL)
            if p.sender_id in ("x1", "x2")
        ]
        changed = await mine.relabel(CHANNEL, ["x1"], "staff")
        after = {p.sender_id: p.role for p in await mine.people(CHANNEL)}

        assert people == [("x1", 2, "customer"), ("x2", 1, "customer")]
        assert changed == 2
        assert (after["x1"], after["x2"]) == ("staff", "customer")
        assert await mine.relabel(CHANNEL, [], "staff") == 0
        assert await theirs.people(CHANNEL) == []

    _run(db_url, work)


def test_leaving_a_chat_out_stops_new_messages_and_deleting_it_removes_its_messages(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        await mine.add(_said("một", thread="e1"))
        cid = conversation_id(CHANNEL, "e1")

        assert await mine.set_excluded(cid, True) is True
        assert await mine.add(_said("hai", thread="e1", message_id="m2")) is False
        assert [m.text for m in await mine.messages(cid, limit=10)] == ["một"]
        assert await theirs.set_excluded(cid, False) is False  # not theirs

        assert await mine.delete(cid) is True
        assert await mine.get(cid) is None
        assert await mine.messages(cid, limit=10) == []

    _run(db_url, work)


def test_deleting_many_chats_removes_their_messages_and_only_those_of_this_clinic(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        for thread in ("m1", "m2", "m3"):
            await mine.add(_said("xin chào", thread=thread, message_id=f"{thread}-a"))
        ids = [conversation_id(CHANNEL, thread) for thread in ("m1", "m2", "m3")]

        assert await theirs.delete_many(ids[:2]) == 0
        assert await mine.delete_many([ids[0], ids[1], "cv-" + "0" * 20]) == 2
        assert await mine.delete_many([]) == 0
        assert [await mine.get(i) is None for i in ids] == [True, True, False]
        assert await mine.messages(ids[0], limit=10) == []

    _run(db_url, work)


def test_old_messages_are_purged_and_the_counts_and_empty_chats_follow(db_url: str) -> None:
    async def work(mine: PostgresConversationStore, theirs: PostgresConversationStore) -> None:
        old = NOW - timedelta(days=400)
        await mine.add(_said("cũ", thread="r-old", message_id="m1", at=old))
        await mine.add(_said("cũ", thread="r-mixed", message_id="m2", at=old))
        await mine.add(_said("mới", thread="r-mixed", message_id="m3", at=NOW))
        await mine.add(_said("cũ", thread="r-left-out", message_id="m4", at=old))
        await mine.set_excluded(conversation_id(CHANNEL, "r-left-out"), True)
        await theirs.add(_said("cũ của người khác", thread="r-old", message_id="m1", at=old))

        gone = await mine.purge_before(NOW - timedelta(days=365))

        assert gone >= 3
        assert await mine.get(conversation_id(CHANNEL, "r-old")) is None
        left_out = await mine.get(conversation_id(CHANNEL, "r-left-out"))
        assert left_out is not None
        assert left_out.excluded
        mixed = await mine.get(conversation_id(CHANNEL, "r-mixed"))
        assert mixed is not None
        assert (mixed.message_count, mixed.first_at) == (1, NOW)
        assert await theirs.get(conversation_id(CHANNEL, "r-old")) is not None

    _run(db_url, work)
