"""The scenario store on Postgres: the episode tables made by ``migrate-plugins``, repeats joined, search by words
and by vector (pgvector), who may reach whose, vectors made and episodes joined by meaning, and the cut
bookkeeping of the conversation store. Needs ``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is
dropped and migrated again); skipped otherwise.

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
from plugins.conversations.episode_store import PostgresEpisodeStore
from plugins.conversations.episodes import Draft, fingerprint_of
from plugins.conversations.models import NewMessage, Role, conversation_id
from plugins.conversations.scenario_models import Reach
from plugins.conversations.store import PostgresConversationStore
from plugins.conversations.words import query_terms
from tests.knowledge.fake_embedding import concept_vector

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[2]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
NOW = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)
SPACE = "0123456789abcdef"
Stores = tuple[PostgresEpisodeStore, PostgresEpisodeStore, PostgresConversationStore]


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


def _run(url: str, work: Callable[[Stores], Awaitable[None]]) -> None:
    async def main() -> None:
        engine = create_async_engine(url)
        try:
            await work(
                (
                    PostgresEpisodeStore(engine, tenant_id="clinic-a", agent="clinic"),
                    PostgresEpisodeStore(engine, tenant_id="clinic-b", agent="clinic"),
                    PostgresConversationStore(engine, tenant_id="clinic-a", agent="clinic"),
                )
            )
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _draft(ask: str, reaction: str = "Dạ em tư vấn gói phù hợp rồi báo giá chị nhé", seq: int = 1) -> Draft:
    return Draft(
        started_at=NOW,
        ended_at=NOW + timedelta(minutes=3),
        first_seq=seq,
        last_seq=seq + 1,
        transcript=(("customer", ask), ("staff", reaction)),
        ask=ask,
        fingerprint=fingerprint_of(ask),
    )


def _message(thread: str, role: Role, text: str, number: int, at: datetime) -> NewMessage:
    return NewMessage(
        conversation_id=conversation_id("zalo-a", thread),
        channel="zalo-a",
        external_id=thread,
        is_group=False,
        title_hint="",
        message_id=f"{thread}-{number}",
        sender_id=role,
        sender_name="",
        role=role,
        origin="own" if role == "staff" else "inbound",
        at=at,
        text=text,
    )


def test_an_episode_is_stored_once_and_the_same_question_counts_one_more_repeat(db_url: str) -> None:
    async def work(stores: Stores) -> None:
        mine, theirs, _ = stores
        first, created = await mine.add(
            _draft("Giá điều trị nám bao nhiêu ạ", seq=1),
            channel="zalo-a",
            plugin="zalo",
            conversation_id="cv-1",
        )
        again, recreated = await mine.add(
            _draft("Giá điều trị nám bao nhiêu ạ", seq=1),
            channel="zalo-a",
            plugin="zalo",
            conversation_id="cv-1",
        )
        joined, joined_new = await mine.add(
            _draft("GIÁ điều trị NÁM bao nhiêu ạ", "Dạ em gửi bảng giá cho chị nhé", seq=9),
            channel="zalo-a",
            plugin="zalo",
            conversation_id="cv-2",
        )
        elsewhere, elsewhere_new = await mine.add(
            _draft("Giá điều trị nám bao nhiêu ạ", seq=1),
            channel="zalo-b",
            plugin="zalo",
            conversation_id="cv-3",
        )

        assert (created, recreated, joined_new, elsewhere_new) == (True, False, False, True)
        assert again.id == first.id
        assert (joined.id, joined.repeats) == (first.id, 2)
        assert joined.transcript[-1] == ("staff", "Dạ em gửi bảng giá cho chị nhé")
        assert elsewhere.id != first.id
        assert await theirs.get(first.id) is None

    _run(db_url, work)


def test_search_by_words_needs_shared_terms_and_respects_the_reach(db_url: str) -> None:
    async def work(stores: Stores) -> None:
        mine, theirs, _ = stores
        for number, (channel, ask) in enumerate(
            [
                ("zalo-a", "Em muốn hủy lịch hẹn ngày mai"),
                ("zalo-b", "Cho hỏi giá niềng răng trọn gói"),
                ("other-a", "Cho hỏi giá niềng răng trọn gói thế nào"),
            ],
            start=100,
        ):
            await mine.add(
                _draft(ask, seq=number),
                channel=channel,
                plugin="other" if channel.startswith("other") else "zalo",
                conversation_id=f"cv-w{number}",
            )

        terms = query_terms("giá niềng răng bao nhiêu")
        in_zalo = await mine.search_words(terms, Reach(plugin="zalo"), 5)
        everywhere = await mine.search_words(terms, Reach(), 5)
        one_channel = await mine.search_words(terms, Reach(channel="zalo-a"), 5)

        assert [h.episode.channel for h in in_zalo] == ["zalo-b"]
        assert {h.episode.channel for h in everywhere} == {"zalo-b", "other-a"}
        assert one_channel == []
        assert await mine.search_words(query_terms("xe máy hỏng"), Reach(), 5) == []
        assert await theirs.search_words(terms, Reach(), 5) == []

    _run(db_url, work)


def test_vectors_are_made_for_the_episodes_that_lack_them_and_found_by_meaning(db_url: str) -> None:
    async def work(stores: Stores) -> None:
        mine, theirs, _ = stores
        await mine.add(
            _draft("Giá điều trị nám bao nhiêu tiền", seq=200),
            channel="zalo-a",
            plugin="zalo",
            conversation_id="cv-v1",
        )
        await mine.add(
            _draft("Em muốn hủy lịch hẹn và đổi lịch", seq=201),
            channel="zalo-a",
            plugin="zalo",
            conversation_id="cv-v2",
        )

        waiting = await mine.missing_vectors(SPACE, 100)
        counts_before = await mine.counts(SPACE)
        await mine.save_vectors(SPACE, [(i, concept_vector(ask)) for i, ask in waiting])
        counts_after = await mine.counts(SPACE)
        hits = await mine.search_vector(SPACE, concept_vector("da bị sạm nám"), Reach(plugin="zalo"), 3, 0.3)

        assert len(waiting) >= 2
        assert counts_before.without_vector >= 2
        assert counts_after.without_vector == 0
        assert hits
        assert hits[0].how == "meaning"
        assert "nám" in hits[0].episode.ask
        assert (
            await mine.search_vector(SPACE, concept_vector("da bị sạm nám"), Reach(plugin="zalo"), 3, 0.99)
            == []
        )
        assert await mine.search_vector("f" * 16, concept_vector("nám"), Reach(), 3, 0.0) == []
        assert await theirs.search_vector(SPACE, concept_vector("nám"), Reach(), 3, 0.0) == []

    _run(db_url, work)


def test_episodes_that_mean_the_same_are_joined_and_a_dissimilar_one_is_left(db_url: str) -> None:
    async def work(stores: Stores) -> None:
        mine, _, _ = stores
        first, _ = await mine.add(
            _draft("Bảo lưu gói liệu trình tạm dừng được không", seq=300),
            channel="zalo-m",
            plugin="zalo",
            conversation_id="cv-m1",
        )
        second, _ = await mine.add(
            _draft("Tôi muốn tạm dừng bảo lưu gói liệu trình", seq=301),
            channel="zalo-m",
            plugin="zalo",
            conversation_id="cv-m2",
        )
        far, _ = await mine.add(
            _draft("Thanh toán bằng thẻ hay chuyển khoản hóa đơn", seq=302),
            channel="zalo-m",
            plugin="zalo",
            conversation_id="cv-m3",
        )
        await mine.save_vectors(SPACE, [(e.id, concept_vector(e.ask)) for e in (first, second, far)])

        joined = await mine.merge_into_nearest(second.id, SPACE, 0.93)
        left = await mine.merge_into_nearest(far.id, SPACE, 0.93)

        assert joined == first.id
        assert left is None
        target = await mine.get(first.id)
        assert target is not None
        assert target.repeats == 2
        assert await mine.get(second.id) is None
        assert await mine.get(far.id) is not None

    _run(db_url, work)


def test_a_switched_off_episode_is_not_found_and_deleting_takes_its_vector(db_url: str) -> None:
    async def work(stores: Stores) -> None:
        mine, _, _ = stores
        episode, _ = await mine.add(
            _draft("Giá tiêm filler môi bao nhiêu", seq=400),
            channel="zalo-d",
            plugin="zalo",
            conversation_id="cv-d1",
        )
        await mine.save_vectors(SPACE, [(episode.id, concept_vector(episode.ask))])
        terms = query_terms("giá tiêm filler")
        assert await mine.search_words(terms, Reach(channel="zalo-d"), 5)

        assert await mine.set_enabled(episode.id, False) is True
        assert await mine.search_words(terms, Reach(channel="zalo-d"), 5) == []
        assert (
            await mine.search_vector(SPACE, concept_vector(episode.ask), Reach(channel="zalo-d"), 5, 0.0)
            == []
        )

        assert await mine.delete(episode.id) is True
        assert await mine.get(episode.id) is None
        assert await mine.delete(episode.id) is False

    _run(db_url, work)


def test_conversations_that_went_quiet_are_found_once_and_cut_messages_are_not_given_again(
    db_url: str,
) -> None:
    async def work(stores: Stores) -> None:
        _, _, conversations = stores
        await conversations.add(_message("q1", "customer", "Giá điều trị nám", 1, NOW))
        await conversations.add(
            _message("q1", "staff", "Dạ em báo giá chị nhé", 2, NOW + timedelta(minutes=1))
        )
        await conversations.add(_message("q2", "customer", "Hỏi chút", 1, NOW + timedelta(hours=5)))
        cid = conversation_id("zalo-a", "q1")
        busy = conversation_id("zalo-a", "q2")

        quiet = await conversations.to_cut(idle_before=NOW + timedelta(hours=1), limit=50)
        found = await conversations.uncut_messages([cid, busy], limit=100)
        await conversations.mark_cut({cid: max(m.seq for m in found[cid])})
        after = await conversations.to_cut(idle_before=NOW + timedelta(hours=1), limit=50)
        empty = await conversations.uncut_messages([cid], limit=100)
        none = await conversations.uncut_messages([], limit=100)

        assert cid in {c.id for c in quiet}
        assert busy not in {c.id for c in quiet}
        assert [m.text for m in found[cid]] == ["Giá điều trị nám", "Dạ em báo giá chị nhé"]
        assert cid not in {c.id for c in after}
        assert empty[cid] == []
        assert none == {}

    _run(db_url, work)
