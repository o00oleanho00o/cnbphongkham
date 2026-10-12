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
from plugins.knowledge.models import Source
from plugins.knowledge.store import PostgresKnowledgeStore
from plugins.knowledge.text import chunk, content_hash, query_terms

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
            await mine.add_source(source, make_chunks(source_id, chunk(body, code), []))
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
