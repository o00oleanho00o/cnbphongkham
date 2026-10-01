"""Fixtures of the C2 database tests (marker ``db``; skipped without ``PEMA_TEST_DATABASE_URL``).

Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a THROWAWAY database (the fixture drops every Pema schema and
re-runs the Alembic history, exactly like ``tests/test_database.py``), for example the container of the package::

    docker run -d --name pema-pg-c2 -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema -p 127.0.0.1::5432 \\
        pgvector/pgvector:pg17
    PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:<port>/pema uv run pytest -m db

Engines are created per test inside the test's event loop (pytest-asyncio gives every test its own loop, and a
pooled async connection must not outlive the loop that opened it).
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

from pema.core.db import ClinicDatabase

API_DIR = Path(__file__).resolve().parents[3]
API_INI = API_DIR / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    if not ADMIN_URL:
        pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against")
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    _reset(engine)
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def clinic_ids(admin_engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """Two synthetic clinics, each with a default agent and a personal-account row ``zp-1``."""
    first, second = uuid.uuid4(), uuid.uuid4()
    with admin_engine.begin() as conn:
        for clinic_id, slug in ((first, "c2-clinic-a"), (second, "c2-clinic-b")):
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": clinic_id, "slug": slug, "name": f"Synthetic {slug}"},
            )
            conn.execute(
                text("INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, 'default', 'Default')"),
                {"c": clinic_id},
            )
            conn.execute(
                text(
                    "INSERT INTO agent.accounts (clinic_id, id, label, channel, agent_id) "
                    "VALUES (:c, 'zp-1', 'Personal', 'zalo_personal', 'default')"
                ),
                {"c": clinic_id},
            )
    return first, second


def _role_url(role: str, password: str) -> str:
    assert ADMIN_URL is not None
    return make_url(ADMIN_URL).set(username=role, password=password).render_as_string(hide_password=False)


@pytest.fixture
async def be_db(admin_engine: Engine) -> AsyncIterator[ClinicDatabase]:
    """``ClinicDatabase`` as role ``be_app`` (the API process)."""
    db = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
async def worker_db(admin_engine: Engine) -> AsyncIterator[ClinicDatabase]:
    """``ClinicDatabase`` as role ``agent_worker`` (turns and scheduler: nothing on ``clinic.*``)."""
    db = ClinicDatabase(_role_url("agent_worker", WORKER_PASSWORD))
    try:
        yield db
    finally:
        await db.dispose()
