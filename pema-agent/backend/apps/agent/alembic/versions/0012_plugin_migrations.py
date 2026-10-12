"""agent_rt: which migration files of each plugin have run.

A plugin that keeps tables of its own declares ``[migrations]`` in its ``plugin.toml`` (a folder of
``NNNN_name.sql`` files and the prefix its tables carry). ``agent db migrate-plugins`` runs the files that have
not run yet as the owner role and records them here, with a checksum so an edited file is noticed. The runtime
role only reads this table (a plugin checks that its tables are there).

Revision ID: 0012_plugin_migrations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_plugin_migrations"
down_revision = "0011_model_entries"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"


def upgrade() -> None:
    op.create_table(
        "agent_plugin_migration",
        sa.Column("plugin", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("table_prefix", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("plugin", "version"),
        sa.CheckConstraint("version > 0", name="agent_plugin_migration_version"),
        sa.CheckConstraint("table_prefix ~ '^[a-z][a-z0-9]*_$'", name="agent_plugin_migration_prefix"),
        schema=SCHEMA,
    )
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"GRANT SELECT ON {SCHEMA}.agent_plugin_migration TO {ROLE}; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("agent_plugin_migration", schema=SCHEMA)
