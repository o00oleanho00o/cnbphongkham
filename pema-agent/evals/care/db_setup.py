"""The throwaway database of the DB-backed measurements. New module (not a port).

A copy of what ``pema.api.clinic_testing`` does for the tests (migrate to ``heads``, one synthetic clinic, the
demo patients), without pytest, so ``run_eval`` can use it. It DROPS every Pema schema of the database it is
given: only ever point it at a database made for this (``PEMA_EVAL_CARE_DATABASE_URL``, falling back to the
``PEMA_TEST_DATABASE_URL`` of the test suite, which has the same promise).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import pema
from pema.clinic.actions.seed_demo import SeedResult, seed_demo
from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic, truncate_installation_data

ENV_URLS = ("PEMA_EVAL_CARE_DATABASE_URL", "PEMA_TEST_DATABASE_URL")
BE_PASSWORD = "be-app-eval-secret"  # noqa: S105  - throwaway database only
WORKER_PASSWORD = "agent-worker-eval-secret"  # noqa: S105
ACCOUNT_PASSWORD = "demo-account-eval-secret"  # noqa: S105
API_INI = Path(pema.__file__).resolve().parents[1] / "alembic.ini"
HEAD_TABLE = "alembic_version_pema"


def database_url_from_env() -> str | None:
    for name in ENV_URLS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _role_url(admin: str, role: str, password: str) -> str:
    return make_url(admin).set(username=role, password=password).render_as_string(hide_password=False)


def migrate_fresh(admin: str) -> None:
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = admin
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(admin)
    try:
        with engine.begin() as conn:
            for schema in ("clinic_agent", "agent", "clinic", "ctx"):
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"DROP TABLE IF EXISTS public.{HEAD_TABLE}"))
        command.upgrade(Config(str(API_INI)), "heads")
    finally:
        engine.dispose()


@asynccontextmanager
async def seeded_database(admin: str) -> AsyncGenerator[tuple[ClinicDatabase, SeedResult]]:
    """Migrate ``admin`` from scratch, seed the demo clinic, and yield an app-role connection to it."""
    migrate_fresh(admin)
    engine = create_engine(admin)
    try:
        with engine.begin() as conn:
            ensure_test_clinic(conn)
            truncate_installation_data(conn)
    finally:
        engine.dispose()
    database = ClinicDatabase(_role_url(admin, "be_app", BE_PASSWORD), pool_size=3)
    try:
        yield database, await seed_demo(database, password=ACCOUNT_PASSWORD)
    finally:
        await database.dispose()
