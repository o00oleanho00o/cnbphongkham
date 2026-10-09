"""agent_rt: plugins an admin manages at runtime.

One row per (tenant, agent, plugin). A row overrides the profile's ``[plugins] enabled`` for that plugin;
``config`` holds the plain settings and ``secrets_enc`` the sensitive ones as one encrypted JSON object
(AES-256-GCM, ``AGENT_SECRET_ENCRYPTION_KEY``). ``install`` records where an installed plugin came from;
``last_error`` why it was switched off.

Revision ID: 0005_plugins
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_plugins"
down_revision = "0004_model_settings"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"


def upgrade() -> None:
    op.create_table(
        "agent_plugin",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secrets_enc", sa.Text(), nullable=True),
        sa.Column("install", postgresql.JSONB(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "name"),
        sa.CheckConstraint("name ~ '^[a-z0-9][a-z0-9_-]{0,63}$'", name="agent_plugin_name"),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name="agent_plugin_config_object"),
        sa.CheckConstraint("pg_column_size(config) <= 65536", name="agent_plugin_config_size"),
        sa.CheckConstraint(
            "last_error IS NULL OR char_length(last_error) <= 4000", name="agent_plugin_error_size"
        ),
        schema=SCHEMA,
    )
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.agent_plugin TO {ROLE}; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("agent_plugin", schema=SCHEMA)
