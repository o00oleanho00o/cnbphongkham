"""The knowledge store on Postgres: its tables made by ``migrate-plugins``, a document added and found by
keyword in its tenant's store only, the version in force on the day asked. Needs ``PEMA_TEST_DATABASE_URL`` (a
throwaway database; the schema is dropped and migrated again); skipped otherwise.

The async part runs on a selector event loop: psycopg's async driver cannot use the Windows proactor loop.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
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
from plugins.knowledge.ingest import make_chunks
from plugins.knowledge.models import Chunk, Hit, Source
from plugins.knowledge.store import InMemoryKnowledgeStore, PostgresKnowledgeStore
from plugins.knowledge.text import chunk, content_hash, embed_text_of, query_terms, text_hash

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[2]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"


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
    migrate_plugins(url, [discover([("bundled", BUNDLED_PLUGINS)]).plugins["knowledge"]])
    return url


def _run(url: str, work: Callable[[PostgresKnowledgeStore, PostgresKnowledgeStore], Awaitable[None]]) -> None:
    async def main() -> None:
        engine = create_async_engine(url)
        try:
            await work(
                PostgresKnowledgeStore(engine, tenant_id="clinic-a", agent="clinic"),
                PostgresKnowledgeStore(engine, tenant_id="clinic-b", agent="clinic"),
            )
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _source(source_id: str, code: str, body: str, start: date, end: date | None = None) -> Source:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    return Source(
        id=source_id,
        title=code,
        doc_code=code,
        kind="file",
        format="md",
        size=len(body),
        audience="patient",
        lifecycle="active",
        content_hash=content_hash(body),
        created_by="test",
        markdown=body,
        effective_from=start,
        effective_to=end,
        created_at=now,
        updated_at=now,
    )


NEW = "## Điều trị nám\nMột buổi laser điều trị nám có giá 4.000.000 đồng tại phòng khám."
OLD = "## Điều trị nám\nMột buổi laser điều trị nám có giá 3.500.000 đồng theo bảng giá cũ."


def test_a_document_is_found_in_its_tenants_store_on_the_day_asked(db_url: str) -> None:
    async def work(mine: PostgresKnowledgeStore, theirs: PostgresKnowledgeStore) -> None:
        for source_id, code, body, start, end in (
            ("src-00000000000a", "D07", NEW, date(2026, 10, 1), None),
            ("src-00000000000b", "D07-V1", OLD, date(2026, 1, 1), date(2026, 9, 30)),
        ):
            source = _source(source_id, code, body, start, end)
            await mine.add_source(source, make_chunks(source_id, code, chunk(body, code), []))
        question = query_terms("trị nám một buổi giá bao nhiêu")

        today = await mine.search(question, date(2026, 10, 12), 5)
        before = await mine.search(question, date(2026, 9, 15), 5)
        elsewhere = await theirs.search(question, date(2026, 10, 12), 5)

        assert [hit.doc_code for hit in today] == ["D07"]
        assert [hit.doc_code for hit in before] == ["D07-V1"]
        assert elsewhere == []
        read = await mine.in_force("D07-V1", date(2026, 9, 15))
        assert read is not None
        assert read.id == "src-00000000000b"
        assert await mine.in_force("D07-V1", date(2026, 10, 12)) is None

    _run(db_url, work)


def test_postgres_and_memory_score_keyword_search_the_same(db_url: str) -> None:
    long_body = "## Nám\nNám nám nám nám. " + "Phòng khám làm việc mỗi ngày trong tuần. " * 30
    corpus = (
        (
            "src-00000000bm01",
            "D01",
            "## Giá\nLaser nám giá 4.000.000 đồng một buổi, laser nám hiệu quả.",
            None,
        ),
        ("src-00000000bm02", "D02", long_body, None),
        (
            "src-00000000bm03",
            "D03",
            "## Hori\nLaser hori chỉ làm ở Hà Nội, không làm ở chi nhánh khác.",
            None,
        ),
        ("src-00000000bm04", "D04", "## Giá cũ\nLaser nám giá 3.500.000 đồng.", date(2026, 9, 30)),
    )

    def ordered(hits: list[Hit]) -> list[tuple[str, float]]:
        return sorted(((h.chunk.id, round(h.score, 6)) for h in hits), key=lambda x: (-x[1], x[0]))

    async def main() -> None:
        engine = create_async_engine(db_url)
        try:
            # a tenant of its own: the other tests of this module leave their sources in "clinic-a"
            mine = PostgresKnowledgeStore(engine, tenant_id="bm25-parity", agent="clinic")
            memory = InMemoryKnowledgeStore()
            for source_id, code, body, end in corpus:
                source = _source(source_id, code, body, date(2026, 1, 1), end)
                made = make_chunks(source_id, code, chunk(body, code), [])
                await mine.add_source(source, made)
                await memory.add_source(source, made)
            for question in (
                "laser nám giá bao nhiêu",
                "nám",
                "hori hà nội",
                "phòng khám làm việc",
                "xe máy",
            ):
                wanted = query_terms(question)
                on_postgres = await mine.search(wanted, date(2026, 10, 12), 20)
                in_memory = await memory.search(wanted, date(2026, 10, 12), 20)

                assert ordered(on_postgres) == ordered(in_memory), question
                assert all(h.doc_code != "D04" for h in on_postgres), question
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def test_section_chunks_come_back_in_document_order_for_the_exact_section_only(db_url: str) -> None:
    title = "Giảm 100% _đặc biệt"
    odd = (
        f"# {title}\n\n### A\n\n{'a' * 70}\n\n### B\n\n{'b' * 70}\n\n# {title} hôm nay\n\n### C\n\n{'c' * 70}"
    )
    plain = f"# Khác\n\n### A\n\n{'d' * 70}"

    async def main() -> None:
        engine = create_async_engine(db_url)
        try:
            mine = PostgresKnowledgeStore(engine, tenant_id="section", agent="clinic")
            memory = InMemoryKnowledgeStore()
            for source_id, body in (("src-00000000se01", odd), ("src-00000000se02", plain)):
                source = _source(source_id, source_id[-4:], body, date(2026, 1, 1))
                made = make_chunks(source_id, source.title, chunk(body, source.title), [])
                await mine.add_source(source, made)
                await memory.add_source(source, made)
            wanted = [("src-00000000se01", title), ("src-00000000se02", "Khác")]

            on_postgres = await mine.section_chunks(wanted)
            in_memory = await memory.section_chunks(wanted)

            assert [c.id for c in on_postgres] == [c.id for c in in_memory]
            assert [c.body[0] for c in on_postgres] == ["a", "b", "d"]
            assert await mine.section_chunks([]) == []
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def test_the_bm25_migration_counts_chunks_as_python_does(db_url: str) -> None:
    backfill = (APP_DIR / "plugins/knowledge/migrations/0003_bm25.sql").read_text(encoding="utf-8")
    backfill = backfill[backfill.index("UPDATE kb_chunk") :]
    body = "## Giá\nLaser nám giá 4.000.000 đồng một buổi, laser nám hiệu quả, nám nám."
    read = sql("SELECT id, terms_len, term_counts FROM agent_rt.kb_chunk WHERE tenant_id = 'bm25-backfill'")

    async def main() -> None:
        engine = create_async_engine(db_url)
        try:
            store = PostgresKnowledgeStore(engine, tenant_id="bm25-backfill", agent="clinic")
            source = _source("src-00000000bm10", "D10", body, date(2026, 1, 1))
            await store.add_source(source, make_chunks(source.id, "D10", chunk(body, "D10"), []))
            async with engine.begin() as conn:
                written = (await conn.execute(read)).all()
                await conn.execute(sql("SET LOCAL search_path TO agent_rt"))
                await conn.execute(sql(backfill))
                recounted = (await conn.execute(read)).all()

            assert written
            assert written == recounted
            assert written[0].term_counts["nam"] == 4
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def test_the_table_of_contents_holds_each_code_once_in_force_on_the_day(db_url: str) -> None:
    async def work(_mine: PostgresKnowledgeStore, store: PostgresKnowledgeStore) -> None:
        # the second tenant's store: no other test adds documents to it
        for source_id, code, title, start, end in (
            ("src-0000000000c1", "D05", "Chăm sóc cũ", date(2026, 1, 1), date(2026, 9, 30)),
            ("src-0000000000c2", "D05", "Chăm sóc sau điều trị", date(2026, 10, 1), None),
            ("src-0000000000c3", "D12", "Đặt lịch", date(2026, 1, 1), None),
            ("src-0000000000c4", "D30", "Khuyến mại năm sau", date(2099, 1, 1), None),
        ):
            source = _source(source_id, code, NEW, start, end)
            source.title = title
            await store.add_source(source, [])

        today = await store.catalog(date(2026, 10, 12), 10)
        first = await store.catalog(date(2026, 10, 12), 1)

        assert [(e.code, e.title) for e in today] == [("D05", "Chăm sóc sau điều trị"), ("D12", "Đặt lịch")]
        assert [e.code for e in first] == ["D05"]

    _run(db_url, work)


SPACE = "0123456789abcdef"
OTHER = "fedcba9876543210"


def _unit(*values: float) -> list[float]:
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


def test_vectors_are_found_by_cosine_in_force_on_the_day_asked(db_url: str) -> None:
    async def work(mine: PostgresKnowledgeStore, theirs: PostgresKnowledgeStore) -> None:
        (new_chunk,) = await _stored(mine, "src-0000000000a1", "V-NEW", NEW, date(2026, 10, 1))
        (old_chunk,) = await _stored(
            mine, "src-0000000000a2", "V-OLD", OLD, date(2026, 1, 1), date(2026, 9, 30)
        )
        await mine.save_vectors(
            SPACE, [(new_chunk.embed_hash, _unit(1, 0, 0, 0)), (old_chunk.embed_hash, _unit(1, 1, 0, 0))]
        )

        today = await mine.vector_search(SPACE, _unit(1, 0, 0, 0), date(2026, 10, 12), 5, 0.0)
        before = await mine.vector_search(SPACE, _unit(1, 0, 0, 0), date(2026, 9, 15), 5, 0.0)
        floor = await mine.vector_search(SPACE, _unit(1, 0, 0, 0), date(2026, 9, 15), 5, 0.9)
        elsewhere = await theirs.vector_search(SPACE, _unit(1, 0, 0, 0), date(2026, 10, 12), 5, 0.0)
        other_space = await mine.vector_search(OTHER, _unit(1, 0, 0, 0), date(2026, 10, 12), 5, 0.0)

        assert [hit.doc_code for hit in today] == ["V-NEW"]
        assert today[0].score == pytest.approx(1.0)
        assert today[0].chunk.embedded
        assert [hit.doc_code for hit in before] == ["V-OLD"]
        assert before[0].score == pytest.approx(2**-0.5)
        assert floor == []
        assert elsewhere == []
        assert other_space == []

    _run(db_url, work)


async def _stored(
    store: PostgresKnowledgeStore, source_id: str, code: str, body: str, start: date, end: date | None = None
) -> list[Chunk]:
    source = _source(source_id, code, body, start, end)
    chunks = make_chunks(source_id, code, chunk(body, code), [])
    await store.add_source(source, chunks)
    return chunks


def test_missing_vectors_lists_each_text_once_and_saving_is_idempotent(db_url: str) -> None:
    async def work(mine: PostgresKnowledgeStore, theirs: PostgresKnowledgeStore) -> None:
        chunks = await _stored(mine, "src-0000000000b1", "V-MISS", NEW, date(2026, 10, 1))
        before = await mine.missing_vectors("1111111111111111", 10)
        count = await mine.missing_count("1111111111111111")

        await mine.save_vectors("1111111111111111", [(chunks[0].embed_hash, _unit(1, 0, 0, 0))])
        await mine.save_vectors("1111111111111111", [(chunks[0].embed_hash, _unit(0, 1, 0, 0))])

        assert (chunks[0].embed_hash, chunks[0].embed_text) in before
        assert count == len(await _all_missing(mine, "2222222222222222"))
        assert (chunks[0].embed_hash, chunks[0].embed_text) not in await mine.missing_vectors(
            "1111111111111111", 50
        )
        assert await mine.missing_count("1111111111111111") == count - 1
        assert await theirs.missing_count("1111111111111111") == 0

    _run(db_url, work)


async def _all_missing(store: PostgresKnowledgeStore, space: str) -> list[tuple[str, str]]:
    return await store.missing_vectors(space, 1000)


def test_chunks_report_whether_they_have_a_vector_and_counts_follow(db_url: str) -> None:
    async def work(mine: PostgresKnowledgeStore, theirs: PostgresKnowledgeStore) -> None:
        chunks = await _stored(mine, "src-0000000000c1", "V-REP", NEW, date(2026, 10, 1))
        await mine.save_vectors(SPACE, [(chunks[0].embed_hash, _unit(1, 0, 0, 0))])

        with_space, _ = await mine.chunks("src-0000000000c1", "", 1, 10, SPACE)
        without, _ = await mine.chunks("src-0000000000c1", "", 1, 10, None)

        assert with_space[0].embedded
        assert not without[0].embedded
        assert (await mine.vector_counts(SPACE))["src-0000000000c1"] == 1
        assert "src-0000000000c1" not in await mine.vector_counts(OTHER)

    _run(db_url, work)


def test_clearing_and_dropping_stale_vectors(db_url: str) -> None:
    async def work(mine: PostgresKnowledgeStore, theirs: PostgresKnowledgeStore) -> None:
        chunks = await _stored(mine, "src-0000000000d1", "V-DROP", NEW, date(2026, 10, 1))
        gone = "f" * 64
        await mine.save_vectors(
            "3333333333333333", [(chunks[0].embed_hash, _unit(1, 0, 0, 0)), (gone, _unit(0, 1, 0, 0))]
        )
        await mine.save_vectors("4444444444444444", [(chunks[0].embed_hash, _unit(1, 0, 0, 0))])

        dropped = await mine.drop_stale_vectors("3333333333333333")
        cleared = await mine.clear_vectors("3333333333333333")

        assert dropped >= 2  # the other space's vector and the text no chunk has
        assert cleared == 1  # what was left in the space
        assert await mine.drop_stale_vectors("3333333333333333") == 0

    _run(db_url, work)


def test_the_migration_builds_the_same_embed_text_as_python(db_url: str) -> None:
    title, path, body = "Bảng giá", "Điều trị nám > Buổi lẻ", "Một buổi 4.000.000 đồng."
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            row = conn.execute(
                sql(
                    "SELECT s || E'\n' || p || E'\n\n' || b AS embed_text, "
                    "encode(sha256(convert_to(s || E'\n' || p || E'\n\n' || b, 'UTF8')), 'hex') AS embed_hash "
                    "FROM (SELECT CAST(:s AS text) AS s, CAST(:p AS text) AS p, CAST(:b AS text) AS b) v"
                ),
                {"s": title, "p": path, "b": body},
            ).one()
    finally:
        engine.dispose()

    assert row.embed_text == embed_text_of(title, path, body)
    assert row.embed_hash == text_hash(embed_text_of(title, path, body))
