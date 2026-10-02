# ported from: none (new: the Postgres store that replaces the SQLite statements of runtime-*-settings.ts)
"""``SqlRuntimeSettingsStore`` against a clean Postgres (pgvector image) through the ``be_app`` role (single tenant: one clinic,
no row level security). Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a THROWAWAY database (see
``tests/test_database.py``); without it every test here is skipped. The fixture drops every Pema schema first and
re-runs the alembic history: never point it at data you care about, and do not run it in parallel with
``test_database.py`` on the same database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pema.config.runtime_settings_store import (
    RuntimeSettingsSnapshot,
    SqlRuntimeSettingsStore,
)
from pema.config.runtime_tuning_settings import (
    get_tuning,
    install_tuning_provider,
    reset_tuning_provider,
    set_tuning,
)
from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against", allow_module_level=True)

API_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
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
def clinic(admin_engine: Engine) -> uuid.UUID:
    """The one clinic of the database."""
    with admin_engine.begin() as conn:
        return ensure_test_clinic(conn)


@pytest.fixture
async def store(clinic: uuid.UUID) -> AsyncIterator[SqlRuntimeSettingsStore]:
    assert ADMIN_URL is not None
    url = make_url(ADMIN_URL).set(drivername="postgresql+psycopg", username="be_app", password=BE_PASSWORD)
    db = ClinicDatabase(url.render_as_string(hide_password=False))
    yield SqlRuntimeSettingsStore(db)
    await db.dispose()


async def test_set_then_load_all_round_trips_and_upserts(
    store: SqlRuntimeSettingsStore, clinic: uuid.UUID
) -> None:
    """ghi rồi đọc lại đúng; ghi lần hai cùng key là cập nhật chứ không nhân đôi"""
    a = clinic
    await store.set(a, "llm_model", "m-1")
    await store.set(a, "llm_model", "m-2")
    assert (await store.load_all(a))["llm_model"] == "m-2"


async def test_delete_and_delete_many(store: SqlRuntimeSettingsStore, clinic: uuid.UUID) -> None:
    """delete / delete_many chỉ xóa đúng các key được nêu"""
    a = clinic
    for key in ("d1", "d2", "d3", "d4"):
        await store.set(a, key, key)
    await store.delete(a, "d1")
    await store.delete_many(a, ["d2", "d3", "never-existed"])
    await store.delete_many(a, [])
    assert not {"d1", "d2", "d3"} & set(await store.load_all(a))
    assert (await store.load_all(a))["d4"] == "d4"


async def test_synchronous_reads_after_a_refresh_use_the_database(
    store: SqlRuntimeSettingsStore, clinic: uuid.UUID
) -> None:
    """đọc đồng bộ sau refresh thấy giá trị trong Postgres (tuning qua snapshot)"""
    a = clinic
    writer = RuntimeSettingsSnapshot(store)
    reader = RuntimeSettingsSnapshot(store)
    install_tuning_provider(reader)
    try:
        await set_tuning(a, "LLM_MAX_STEPS", 7, snapshot=writer)
        await reader.refresh(a)
        assert get_tuning("LLM_MAX_STEPS") == 7
    finally:
        reset_tuning_provider()
