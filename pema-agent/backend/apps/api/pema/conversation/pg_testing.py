"""Test support for the Postgres-backed stores of package D2 (not a port: zalo-agent tests opened a SQLite
file in a temp dir with ``setupTestEnv``; here every test file gets a THROWAWAY database with the real
Alembic history applied, so RLS, foreign keys and grants are exercised exactly as in production).

Why a separate database and not the schemas of ``tests/test_database.py``: that module drops and re-creates
the schemas of the database named in ``PEMA_TEST_DATABASE_URL``. This helper creates its own database
(``pema_d2_<random>``) on the same server, so both can run in one pytest session. Roles (``be_app``,
``agent_worker``) are cluster-wide and are created by migration 0001 when missing.

Per test: a fresh clinic id, so rows of two tests never meet and no cleanup is needed (RLS keeps them apart,
which is itself part of what the tests prove).

Nothing here is imported by production code. pytest fixtures live in the ``conftest.py`` files of the test
directories; they only call this module.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pema.core.db import ClinicDatabase

API_DIR = Path(__file__).resolve().parents[2]
BE_PASSWORD = "be-app-test-secret"  # noqa: S105 - synthetic, throwaway test database
WORKER_PASSWORD = "agent-worker-test-secret"  # noqa: S105 - synthetic, throwaway test database
DEFAULT_AGENT_ID = "tro-ly-mac-dinh"


@dataclass
class PgTestServer:
    """One throwaway database on the server of ``PEMA_TEST_DATABASE_URL`` (superuser URL)."""

    admin_url: str
    db_name: str
    admin_engine: Engine

    @classmethod
    def create(cls, admin_url: str) -> PgTestServer:
        db_name = f"pema_d2_{uuid.uuid4().hex[:10]}"
        maintenance = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with maintenance.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        maintenance.dispose()

        url = make_url(admin_url).set(database=db_name).render_as_string(hide_password=False)
        previous = {
            name: os.environ.get(name)
            for name in ("PEMA_MIGRATION_DATABASE_URL", "PEMA_BE_APP_PASSWORD", "PEMA_AGENT_WORKER_PASSWORD")
        }
        os.environ["PEMA_MIGRATION_DATABASE_URL"] = url
        os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
        os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
        try:
            command.upgrade(Config(str(API_DIR / "alembic.ini")), "heads")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        return cls(admin_url=admin_url, db_name=db_name, admin_engine=create_engine(url))

    def role_url(self, role: str, password: str) -> str:
        return (
            make_url(self.admin_url)
            .set(database=self.db_name, username=role, password=password)
            .render_as_string(hide_password=False)
        )

    def drop(self) -> None:
        self.admin_engine.dispose()
        maintenance = create_engine(self.admin_url, isolation_level="AUTOCOMMIT")
        with maintenance.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{self.db_name}" WITH (FORCE)'))
        maintenance.dispose()


@dataclass
class ClinicEnv:
    """A fresh clinic with its own database handles. ``db`` is the API role, ``worker_db`` the worker role."""

    server: PgTestServer
    clinic_id: UUID
    db: ClinicDatabase
    worker_db: ClinicDatabase
    extra_clinics: list[UUID] = field(default_factory=list[UUID])

    @classmethod
    def create(
        cls,
        server: PgTestServer,
        account_ids: tuple[str, ...] = ("acc-1", "acc-2"),
        *,
        default_agent: bool = True,
    ) -> ClinicEnv:
        env = cls(
            server=server,
            clinic_id=uuid.uuid4(),
            db=ClinicDatabase(server.role_url("be_app", BE_PASSWORD), pool_size=3),
            worker_db=ClinicDatabase(server.role_url("agent_worker", WORKER_PASSWORD), pool_size=2),
        )
        env.add_clinic(env.clinic_id, account_ids, default_agent=default_agent)
        return env

    def add_clinic(
        self, clinic_id: UUID, account_ids: tuple[str, ...] = (), *, default_agent: bool = True
    ) -> UUID:
        """Insert a clinic, its default agent (unless ``default_agent`` is False, then no account either)
        and the given accounts (as superuser, bypassing RLS)."""
        slug = f"c-{clinic_id.hex[:12]}"
        with self.server.admin_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'Synthetic clinic')"),
                {"id": clinic_id, "slug": slug},
            )
            if default_agent:
                conn.execute(
                    text(
                        "INSERT INTO agent.agents (clinic_id, id, name, is_default, policy_profile) "
                        "VALUES (:c, :id, 'Trợ lý mặc định', true, 'patient_channel')"
                    ),
                    {"c": clinic_id, "id": DEFAULT_AGENT_ID},
                )
            for account_id in account_ids if default_agent else ():
                conn.execute(
                    text(
                        "INSERT INTO agent.accounts (clinic_id, id, label, agent_id) "
                        "VALUES (:c, :id, :label, :agent)"
                    ),
                    {"c": clinic_id, "id": account_id, "label": account_id, "agent": DEFAULT_AGENT_ID},
                )
        if clinic_id != self.clinic_id:
            self.extra_clinics.append(clinic_id)
        return clinic_id

    def add_accounts(self, *account_ids: str) -> None:
        with self.server.admin_engine.begin() as conn:
            for account_id in account_ids:
                conn.execute(
                    text(
                        "INSERT INTO agent.accounts (clinic_id, id, label, agent_id) "
                        "VALUES (:c, :id, :label, :agent)"
                    ),
                    {"c": self.clinic_id, "id": account_id, "label": account_id, "agent": DEFAULT_AGENT_ID},
                )

    async def fetch(self, sql: str, **params: Any) -> list[Mapping[str, Any]]:
        """Run a SELECT in the clinic context (RLS applies) and return rows as mappings."""
        async with self.db.session(self.clinic_id) as session:
            result = await session.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]

    async def scalar(self, sql: str, **params: Any) -> Any:
        async with self.db.session(self.clinic_id) as session:
            return (await session.execute(text(sql), params)).scalar()

    async def execute(self, sql: str, **params: Any) -> None:
        async with self.db.session(self.clinic_id) as session:
            await session.execute(text(sql), params)

    async def dispose(self) -> None:
        await self.db.dispose()
        await self.worker_db.dispose()
