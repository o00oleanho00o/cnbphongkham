"""agent_rt: the data plugins keep for themselves (``ctx.storage``).

One row per (tenant, agent, plugin, key) with a JSON value. A plugin reads and writes only its own rows; they
stay when it is disabled.

Revision ID: 0010_plugin_records
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_plugin_records"
down_revision = "0009_inbox"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"


def upgrade() -> None:
    op.create_table(
        "agent_plugin_record",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("plugin", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "plugin", "key"),
        sa.CheckConstraint("plugin ~ '^[a-z0-9][a-z0-9_-]{0,63}$'", name="agent_plugin_record_plugin"),
        sa.CheckConstraint("char_length(key) BETWEEN 1 AND 300", name="agent_plugin_record_key"),
        sa.CheckConstraint("pg_column_size(value) <= 262144", name="agent_plugin_record_size"),
        schema=SCHEMA,
    )
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.agent_plugin_record TO {ROLE}; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("agent_plugin_record", schema=SCHEMA)
