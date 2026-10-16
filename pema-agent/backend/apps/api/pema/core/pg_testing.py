"""A throwaway Postgres database with the real Alembic history applied, so foreign keys and grants are
exercised exactly as in production.

Why a separate database and not the schemas of ``tests/test_database.py``: that module drops and re-creates
the schemas of the database named in ``PEMA_TEST_DATABASE_URL``. This helper creates its own database
(``pema_d2_<random>``) on the same server, so both can run in one pytest session. The role ``be_app`` is
cluster-wide and is created by the baseline when missing.

Single tenant: the migrated database already holds its ONE clinic (``clinic.clinic`` accepts no second
row). Per test: ``ensure_test_clinic`` (the same clinic id every time) and ``truncate_installation_data``
(every table of ``clinic.*`` except the clinic row), so rows of two tests never meet.

Nothing here is imported by production code. pytest fixtures live in the ``conftest.py`` files of the test
directories; they only call this module.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

API_DIR = Path(__file__).resolve().parents[2]
BE_PASSWORD = "be-app-test-secret"  # noqa: S105 - synthetic, throwaway test database


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
            name: os.environ.get(name) for name in ("PEMA_MIGRATION_DATABASE_URL", "PEMA_BE_APP_PASSWORD")
        }
        os.environ["PEMA_MIGRATION_DATABASE_URL"] = url
        os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
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
