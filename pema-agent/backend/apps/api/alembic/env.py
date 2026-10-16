"""Alembic environment for schemas ``ctx`` and ``clinic`` (one revision chain from ``0001_baseline``).

Runs as a migration/owner role (``PEMA_MIGRATION_DATABASE_URL``), never as ``be_app``. The version table
lives in ``public`` and the runtime role is granted no access to it. A change is a new revision on top of the
baseline; never edit one that has run.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

DEFAULT_URL = "postgresql+psycopg://postgres@localhost:5432/pema"
VERSION_TABLE = "alembic_version_pema"

config = context.config


def _url() -> str:
    return os.environ.get("PEMA_MIGRATION_DATABASE_URL", DEFAULT_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table=VERSION_TABLE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
