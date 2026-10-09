"""agent_rt: the agent's model settings, changed at runtime by an admin.

One row per (tenant, agent). Each field left NULL falls back to the environment, then to the profile. The API
key is stored encrypted (AES-256-GCM, ``AGENT_SECRET_ENCRYPTION_KEY``), never in plain text. ``version`` grows
with every change so a running service notices it.

Revision ID: 0004_model_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_model_settings"
down_revision = "0003_ingress"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"


def upgrade() -> None:
    op.create_table(
        "agent_model_settings",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("dialect", sa.Text(), nullable=True),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent"),
        sa.CheckConstraint(
            "provider IS NULL OR provider IN ('openai-compatible', 'anthropic')", name="agent_model_provider"
        ),
        sa.CheckConstraint(
            "reasoning IS NULL OR reasoning IN ('off', 'low', 'medium', 'high')", name="agent_model_reasoning"
        ),
        sa.CheckConstraint(
            "dialect IS NULL OR dialect IN ('deepseek', 'openai')", name="agent_model_dialect"
        ),
        sa.CheckConstraint(
            "model IS NULL OR char_length(model) BETWEEN 1 AND 200", name="agent_model_name_size"
        ),
        sa.CheckConstraint(
            "base_url IS NULL OR base_url ~ '^https?://' AND char_length(base_url) <= 500",
            name="agent_model_base_url",
        ),
        sa.CheckConstraint("version >= 1", name="agent_model_version"),
        schema=SCHEMA,
    )
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.agent_model_settings TO {ROLE}; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("agent_model_settings", schema=SCHEMA)
