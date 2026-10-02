"""De-duplication of webhook updates on Postgres (``agent.channel_update_seen``).

Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a THROWAWAY database, as for ``tests/test_database.py``
(this fixture drops every Pema schema first and re-runs the alembic history)::

    docker run -d --name pema-pg-c1 -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema -p 127.0.0.1::5432 \\
        pgvector/pgvector:pg17
    PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:<port>/pema uv run pytest -m db

The store runs as the ``be_app`` role like in production (single tenant: one clinic, no row level security).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pema.channels.zalo_bot.webhook import PostgresUpdateDedupe
from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against", allow_module_level=True)

API_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    assert ADMIN_URL is not None
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def clinic_a(admin_engine: Engine) -> uuid.UUID:
    """The one clinic of the database."""
    with admin_engine.begin() as conn:
        return ensure_test_clinic(conn)


@pytest.fixture
async def dedupe(clinic_a: uuid.UUID) -> AsyncIterator[PostgresUpdateDedupe]:
    assert ADMIN_URL is not None
    url = (
        make_url(ADMIN_URL).set(username="be_app", password=BE_PASSWORD).render_as_string(hide_password=False)
    )
    db = ClinicDatabase(url)
    yield PostgresUpdateDedupe(db)
    await db.dispose()


async def test_lan_dau_la_moi_lan_hai_la_trung(dedupe: PostgresUpdateDedupe, clinic_a: uuid.UUID) -> None:
    """lần đầu thấy update là mới, lần hai là trùng"""
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-1") is True
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-1") is False


async def test_khoa_la_account_update_id_khong_lan_nhau(
    dedupe: PostgresUpdateDedupe, clinic_a: uuid.UUID
) -> None:
    """cùng update_id nhưng khác account thì KHÔNG phải bản trùng"""
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-2") is True
    assert await dedupe.first_seen(clinic_a, "acc-2", "upd-2") is True


async def test_hai_giao_hang_dong_thoi_dung_mot_ben_thang(
    dedupe: PostgresUpdateDedupe, clinic_a: uuid.UUID
) -> None:
    """INSERT ... ON CONFLICT DO NOTHING RETURNING là 'ai tới trước thắng' nguyên tử"""
    results = await asyncio.gather(*(dedupe.first_seen(clinic_a, "acc-1", "upd-race") for _ in range(8)))
    assert sorted(results) == [False] * 7 + [True]


async def test_forget_cho_phep_xu_ly_lai_khi_lan_dau_that_bai(
    dedupe: PostgresUpdateDedupe, clinic_a: uuid.UUID
) -> None:
    """gỡ dấu thì lần gửi lại được xử lý (nhánh xử lý thất bại của webhook)"""
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-retry") is True
    await dedupe.forget(clinic_a, "acc-1", "upd-retry")
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-retry") is True


async def test_purge_xoa_dau_cu_hon_han(
    dedupe: PostgresUpdateDedupe, clinic_a: uuid.UUID, admin_engine: Engine
) -> None:
    """purge xóa dấu cũ hơn hạn"""
    await dedupe.first_seen(clinic_a, "acc-1", "upd-old")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE agent.channel_update_seen SET seen_at = now() - interval '30 days'"))

    removed = await dedupe.purge(clinic_a, timedelta(days=7))

    assert removed >= 1
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-old") is True, "đã purge thì coi như chưa thấy"
