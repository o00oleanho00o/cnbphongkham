"""De-duplication of webhook updates on Postgres (``agent.channel_update_seen``).

Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a THROWAWAY database, as for ``tests/test_database.py``
(this fixture drops every Pema schema first and re-runs the alembic history)::

    docker run -d --name pema-pg-c1 -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema -p 127.0.0.1::5432 \\
        pgvector/pgvector:pg17
    PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:<port>/pema uv run pytest -m db

The store runs as the ``be_app`` role, so row level security applies like in production.
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
def clinics(admin_engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    a, b = uuid.uuid4(), uuid.uuid4()
    with admin_engine.begin() as conn:
        for clinic_id, slug in ((a, "dedupe-a"), (b, "dedupe-b")):
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": clinic_id, "slug": slug, "name": f"Synthetic {slug}"},
            )
    return a, b


@pytest.fixture
async def dedupe(clinics: tuple[uuid.UUID, uuid.UUID]) -> AsyncIterator[PostgresUpdateDedupe]:
    assert ADMIN_URL is not None
    url = (
        make_url(ADMIN_URL).set(username="be_app", password=BE_PASSWORD).render_as_string(hide_password=False)
    )
    db = ClinicDatabase(url)
    yield PostgresUpdateDedupe(db)
    await db.dispose()


async def test_lan_dau_la_moi_lan_hai_la_trung(
    dedupe: PostgresUpdateDedupe, clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """lần đầu thấy update là mới, lần hai là trùng"""
    clinic_a, _ = clinics
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-1") is True
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-1") is False


async def test_khoa_la_clinic_account_update_id_khong_lan_nhau(
    dedupe: PostgresUpdateDedupe, clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """cùng update_id nhưng khác account hoặc khác clinic thì KHÔNG phải bản trùng"""
    clinic_a, clinic_b = clinics
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-2") is True
    assert await dedupe.first_seen(clinic_a, "acc-2", "upd-2") is True
    assert await dedupe.first_seen(clinic_b, "acc-1", "upd-2") is True


async def test_hai_giao_hang_dong_thoi_dung_mot_ben_thang(
    dedupe: PostgresUpdateDedupe, clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """INSERT ... ON CONFLICT DO NOTHING RETURNING là 'ai tới trước thắng' nguyên tử"""
    clinic_a, _ = clinics
    results = await asyncio.gather(*(dedupe.first_seen(clinic_a, "acc-1", "upd-race") for _ in range(8)))
    assert sorted(results) == [False] * 7 + [True]


async def test_forget_cho_phep_xu_ly_lai_khi_lan_dau_that_bai(
    dedupe: PostgresUpdateDedupe, clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """gỡ dấu thì lần gửi lại được xử lý (nhánh xử lý thất bại của webhook)"""
    clinic_a, _ = clinics
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-retry") is True
    await dedupe.forget(clinic_a, "acc-1", "upd-retry")
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-retry") is True


async def test_purge_xoa_dau_cu_va_chi_trong_clinic_cua_no(
    dedupe: PostgresUpdateDedupe, clinics: tuple[uuid.UUID, uuid.UUID], admin_engine: Engine
) -> None:
    """purge xóa dấu cũ hơn hạn, chỉ trong clinic được hỏi (RLS)"""
    clinic_a, clinic_b = clinics
    await dedupe.first_seen(clinic_a, "acc-1", "upd-old")
    await dedupe.first_seen(clinic_b, "acc-1", "upd-old")
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE agent.channel_update_seen SET seen_at = now() - interval '30 days'"))

    removed = await dedupe.purge(clinic_a, timedelta(days=7))

    assert removed >= 1
    assert await dedupe.first_seen(clinic_a, "acc-1", "upd-old") is True, "đã purge thì coi như chưa thấy"
    assert await dedupe.first_seen(clinic_b, "acc-1", "upd-old") is False, "clinic khác không bị đụng tới"
