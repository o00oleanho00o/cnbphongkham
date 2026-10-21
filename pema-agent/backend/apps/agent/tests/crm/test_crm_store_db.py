"""The crm plugin's tables on Postgres: made by ``migrate-plugins``, the same STATE rules as the memory store
(highest version wins, the time-set clock moves only with the time, newest consent wins), and each tenant sees
only its own. Needs ``PEMA_TEST_DATABASE_URL`` (a throwaway database; the schema is dropped and migrated
again); skipped otherwise. Runs on a selector event loop: psycopg's async driver cannot use the Windows
proactor loop."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import create_async_engine

from agent_app.plugins import discover
from agent_app.plugins.migrations import migrate_plugins
from agent_app.runtime import BUNDLED_PLUGINS
from plugins.crm.store import PostgresReminderStore, Visit

pytestmark = pytest.mark.db

APP_DIR = Path(__file__).resolve().parents[2]
MIGRATION_ENV = "AGENT_MIGRATION_DATABASE_URL"
T0 = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)
AT = datetime(2026, 10, 22, 2, 30, tzinfo=UTC)


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
    migrate_plugins(url, [discover([("bundled", BUNDLED_PLUGINS)]).plugins["crm"]])
    return url


def _run(url: str, work: Callable[[PostgresReminderStore, PostgresReminderStore], Awaitable[None]]) -> None:
    async def main() -> None:
        engine = create_async_engine(url)
        try:
            await work(
                PostgresReminderStore(engine, tenant_id="clinic-a", agent="clinic"),
                PostgresReminderStore(engine, tenant_id="clinic-b", agent="clinic"),
            )
        finally:
            await engine.dispose()

    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


def _visit(**over: object) -> Visit:
    base = Visit(
        appointment_id=uuid4(),
        channel="zalo-acc1",
        external_id="u123",
        starts_at=AT,
        duration_min=30,
        status="booked",
        version=1,
        changed_at=T0,
        actor_type="agent",
        last_event_id=uuid4(),
    )
    return replace(base, **over)  # type: ignore[arg-type]


def test_the_highest_version_wins_and_the_clock_moves_with_the_time_only(db_url: str) -> None:
    async def work(store: PostgresReminderStore, other: PostgresReminderStore) -> None:
        first = _visit()
        later = T0 + timedelta(hours=1)
        assert await store.apply_visit(first)
        assert await store.apply_visit(replace(first, version=2, status="confirmed", changed_at=later))
        assert not await store.apply_visit(replace(first, version=2, status="cancelled"))
        assert not await store.apply_visit(replace(first, version=1, status="cancelled"))
        confirmed = await store.visit(first.appointment_id)
        assert confirmed is not None
        assert (confirmed.version, confirmed.status, confirmed.changed_at) == (2, "confirmed", T0)

        moved = AT + timedelta(hours=4)
        assert await store.apply_visit(replace(first, version=3, starts_at=moved, changed_at=later))
        kept = await store.visit(first.appointment_id)
        assert kept is not None
        assert (kept.starts_at, kept.changed_at) == (moved, later)

        assert await other.visit(first.appointment_id) is None

    _run(db_url, work)


def test_the_newest_consent_wins(db_url: str) -> None:
    async def work(store: PostgresReminderStore, other: PostgresReminderStore) -> None:
        assert await store.apply_consent("zalo-acc1", "u9", True, T0)
        assert await store.apply_consent("zalo-acc1", "u9", False, T0 + timedelta(minutes=5))
        assert not await store.apply_consent("zalo-acc1", "u9", True, T0 + timedelta(minutes=1))
        person = await store.person("zalo-acc1", "u9")
        assert person is not None
        assert person.messages_consent is False
        assert await other.person("zalo-acc1", "u9") is None

    _run(db_url, work)
