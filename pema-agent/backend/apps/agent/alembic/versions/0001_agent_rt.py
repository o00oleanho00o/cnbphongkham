"""agent_rt schema: the agent's notes and its own skills.

``agent_memory`` keeps one Markdown text per (tenant, agent, target, user): notes separated by a ``§`` line,
written with a version check (compare-and-swap) so concurrent sessions never lose a note. ``agent_skill`` keeps
the skills the agent wrote itself; bundled skills stay in the agent folder and never reach this table. The caps
mirror the ones the core enforces, so a bug there cannot store more.

Revision ID: 0001_agent_rt
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_agent_rt"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "agent_memory",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "target", "user_id"),
        sa.CheckConstraint("target IN ('agent', 'user')", name="agent_memory_target"),
        sa.CheckConstraint("(target = 'agent') = (user_id = '')", name="agent_memory_user_only_for_user"),
        sa.CheckConstraint("char_length(content) <= 20000", name="agent_memory_content_size"),
        sa.CheckConstraint("version >= 1", name="agent_memory_version"),
        schema=SCHEMA,
    )
    op.create_table(
        "agent_skill",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "name"),
        sa.CheckConstraint("name ~ '^[a-z0-9][a-z0-9._-]{0,63}$'", name="agent_skill_name"),
        sa.CheckConstraint(
            "char_length(description) BETWEEN 1 AND 1024", name="agent_skill_description_size"
        ),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 20000", name="agent_skill_body_size"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("agent_skill", schema=SCHEMA)
    op.drop_table("agent_memory", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
