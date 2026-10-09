"""Alembic environment for schema ``agent_rt``: what the general agent writes itself (notes, its own skills).

Separate from the clinic migrations in ``apps/api`` (own version table), so the agent can live in the same
Postgres or in its own. Runs as an owner role (``AGENT_MIGRATION_DATABASE_URL``).
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

DEFAULT_URL = "postgresql+psycopg://postgres@localhost:5432/pema"
VERSION_TABLE = "alembic_version_agent_rt"

config = context.config


def _url() -> str:
    return os.environ.get("AGENT_MIGRATION_DATABASE_URL", DEFAULT_URL)


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
