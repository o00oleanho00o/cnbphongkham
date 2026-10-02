"""Test support for the knowledge-base tests that need a real Postgres (the ported tests of the stores, the
search, the ingest worker and the admin routes). NOT used by running code.

Replaces ``setupTestEnv`` / ``cleanupTestEnv`` of the original (a temporary data directory with a fresh
SQLite file per test file): here ONE throwaway Postgres with pgvector is reached through
``PEMA_TEST_DATABASE_URL`` (a superuser URL, see ``tests/test_database.py`` for how to start one). Every test
module that uses ``KbTestDatabase.create()`` DROPS every Pema schema first and re-runs the Alembic history, so
never point the variable at data you care about. Single tenant: the migration creates the ONE clinic of the
database; ``clinic_id`` is its id (``ensure_test_clinic``), there is no second clinic.

The two runtime roles are logged in with the passwords set in the environment before the migration:
``worker_url`` = ``agent_worker`` (what the ingest worker and the ``kb_search`` tool run as, no privilege on
``clinic.*``) and ``be_app`` (the API process).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.core.testing import ensure_test_clinic

API_DIR = Path(__file__).resolve().parents[2]
BE_PASSWORD = "be-app-test-secret"  # noqa: S105 - throwaway test database
WORKER_PASSWORD = "agent-worker-test-secret"  # noqa: S105 - throwaway test database


def database_url_for_tests() -> str | None:
    return os.environ.get("PEMA_TEST_DATABASE_URL")


class KbTestDatabase:
    def __init__(self, admin_url: str) -> None:
        self.admin_url = admin_url
        self.admin_engine: Engine = create_engine(admin_url)
        self.clinic_id: uuid.UUID = uuid.UUID(int=0)
        """Replaced by the id of the clinic the migration created (see ``create``)."""

    @classmethod
    def create(cls, admin_url: str) -> KbTestDatabase:
        os.environ["PEMA_MIGRATION_DATABASE_URL"] = admin_url
        os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
        os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
        self = cls(admin_url)
        with self.admin_engine.begin() as conn:
            for schema in ("clinic_agent", "agent", "clinic", "ctx"):
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))
        command.upgrade(Config(str(API_DIR / "alembic.ini")), "heads")
        with self.admin_engine.begin() as conn:
            self.clinic_id = ensure_test_clinic(conn)
        return self

    def role_url(self, role: str) -> str:
        password = BE_PASSWORD if role == "be_app" else WORKER_PASSWORD
        return (
            make_url(self.admin_url)
            .set(username=role, password=password)
            .render_as_string(hide_password=False)
        )

    @property
    def worker_url(self) -> str:
        return self.role_url("agent_worker")

    @property
    def be_url(self) -> str:
        return self.role_url("be_app")

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        with self.admin_engine.begin() as conn:
            conn.execute(text(sql), params or {})

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        with self.admin_engine.begin() as conn:
            return conn.execute(text(sql), params or {}).scalar()

    def clear_kb(self) -> None:
        """Start a test from an empty knowledge base: documents (chunks and bindings go with them through
        ``ON DELETE CASCADE``), extra agents, runtime settings."""
        with self.admin_engine.begin() as conn:
            conn.execute(text("DELETE FROM agent.kb_document"))
            conn.execute(text("DELETE FROM agent.agents"))

    def add_agent(
        self,
        agent_id: str,
        *,
        policy_profile: str = "staff_assistant",
    ) -> None:
        """``staff_assistant`` by default: the ported tests assume an agent that may read every source; the
        ``patient_channel`` gating has tests of its own."""
        self.execute(
            "INSERT INTO agent.agents (clinic_id, id, name, policy_profile) "
            "VALUES (:c, :id, :name, :p) ON CONFLICT DO NOTHING",
            {
                "c": self.clinic_id,
                "id": agent_id,
                "name": f"Agent {agent_id}",
                "p": policy_profile,
            },
        )

    def delete_agent(self, agent_id: str) -> None:
        self.execute("DELETE FROM agent.agents WHERE id = :id", {"id": agent_id})

    def dispose(self) -> None:
        self.admin_engine.dispose()


class KbHarness:
    """What one test works with: the Postgres admin helpers plus ONE ``ClinicDatabase`` (role
    ``agent_worker`` by default). Built per test because an async engine must live on the event loop of the
    test that uses it."""

    def __init__(self, kb_database: KbTestDatabase, db: ClinicDatabase) -> None:
        self.kb_database = kb_database
        self.db = db

    @property
    def clinic_id(self) -> uuid.UUID:
        return self.kb_database.clinic_id

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        async with self.db.session() as session:
            yield session
