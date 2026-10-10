"""agent_rt: the list of models an admin keeps ready, and which of them is in use.

One row per (tenant, agent, id): a label, the provider, model, address and its own API key (encrypted like the
settings' one). ``agent_model_settings.entry_id`` names the entry whose fields were copied into the settings row;
it is NULL once the settings were changed by hand.

Revision ID: 0011_model_entries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_model_entries"
down_revision = "0010_plugin_records"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"


def upgrade() -> None:
    op.create_table(
        "agent_model_entry",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("dialect", sa.Text(), nullable=True),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "id"),
        sa.CheckConstraint("id ~ '^[0-9a-f]{32}$'", name="agent_model_entry_id"),
        sa.CheckConstraint("char_length(label) BETWEEN 1 AND 100", name="agent_model_entry_label"),
        sa.CheckConstraint(
            "provider IN ('openai-compatible', 'anthropic')", name="agent_model_entry_provider"
        ),
        sa.CheckConstraint(
            "reasoning IS NULL OR reasoning IN ('off', 'low', 'medium', 'high')",
            name="agent_model_entry_reasoning",
        ),
        sa.CheckConstraint(
            "dialect IS NULL OR dialect IN ('deepseek', 'openai')", name="agent_model_entry_dialect"
        ),
        sa.CheckConstraint("char_length(model) BETWEEN 1 AND 200", name="agent_model_entry_model"),
        sa.CheckConstraint(
            "base_url IS NULL OR base_url ~ '^https?://' AND char_length(base_url) <= 500",
            name="agent_model_entry_base_url",
        ),
        schema=SCHEMA,
    )
    op.add_column("agent_model_settings", sa.Column("entry_id", sa.Text(), nullable=True), schema=SCHEMA)
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.agent_model_entry TO {ROLE}; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_column("agent_model_settings", "entry_id", schema=SCHEMA)
    op.drop_table("agent_model_entry", schema=SCHEMA)
