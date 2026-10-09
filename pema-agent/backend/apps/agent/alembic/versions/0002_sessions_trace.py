"""agent_rt: sessions, their messages and the turn trace; grants for the runtime role.

``agent_session`` holds one row per conversation: who it is with, the frozen system prompt and the latest
compaction. ``agent_message`` keeps every message in order (``seq`` from 1); ``uid`` makes a retried append
harmless. ``agent_turn`` / ``agent_turn_event`` trace each turn with metadata only (timings, tokens, outcomes),
never message content; they have no foreign key to the session, so a turn that failed before its first message
is still traced, and are append-only for the runtime role.

The runtime role ``agent_rt_app`` (``agent db bootstrap-role``) gets data rights only, and only if it exists
when this runs.

Revision ID: 0002_sessions_trace
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_sessions_trace"
down_revision = "0001_agent_rt"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"
DATA_TABLES = "agent_rt.agent_memory, agent_rt.agent_skill, agent_rt.agent_session, agent_rt.agent_message"
TRACE_TABLES = "agent_rt.agent_turn, agent_rt.agent_turn_event"


def _if_role(statements: str) -> str:
    return (
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"{statements} END IF; END $$"
    )


def upgrade() -> None:
    op.create_table(
        "agent_session",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("prompt_fingerprint", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("first_kept", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "session_id"),
        sa.CheckConstraint("char_length(session_id) BETWEEN 1 AND 200", name="agent_session_id_size"),
        sa.CheckConstraint("message_count >= 0", name="agent_session_message_count"),
        sa.CheckConstraint(
            "(prompt_text IS NULL) = (prompt_fingerprint IS NULL)", name="agent_session_prompt_pair"
        ),
        sa.CheckConstraint("(summary IS NULL) = (first_kept IS NULL)", name="agent_session_compaction_pair"),
        schema=SCHEMA,
    )
    op.create_index(
        "agent_session_recent_idx",
        "agent_session",
        ["tenant_id", "agent", sa.text("updated_at DESC")],
        schema=SCHEMA,
    )
    op.create_table(
        "agent_message",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("uid", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("message", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "session_id", "seq"),
        sa.UniqueConstraint("uid", name="agent_message_uid"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            [f"{SCHEMA}.agent_session.tenant_id", f"{SCHEMA}.agent_session.session_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("seq >= 1", name="agent_message_seq"),
        schema=SCHEMA,
    )
    op.create_table(
        "agent_turn",
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("stop", sa.Text(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.Text(), nullable=True),
        sa.Column("compactions", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("turn_id"),
        sa.CheckConstraint("stop IN ('completed', 'max_steps', 'error')", name="agent_turn_stop"),
        sa.CheckConstraint("(stop = 'error') = (error_kind IS NOT NULL)", name="agent_turn_error_kind"),
        schema=SCHEMA,
    )
    op.create_index(
        "agent_turn_session_idx",
        "agent_turn",
        ["tenant_id", "session_id", sa.text("started_at DESC")],
        schema=SCHEMA,
    )
    op.create_table(
        "agent_turn_event",
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("turn_id", "seq"),
        sa.ForeignKeyConstraint(["turn_id"], [f"{SCHEMA}.agent_turn.turn_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "kind IN ('model_call', 'tool_call', 'compaction', 'memory_flush')", name="agent_turn_event_kind"
        ),
        schema=SCHEMA,
    )
    op.execute(
        _if_role(
            f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}; "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {DATA_TABLES} TO {ROLE}; "
            f"GRANT SELECT, INSERT ON {TRACE_TABLES} TO {ROLE};"
        )
    )


def downgrade() -> None:
    op.execute(
        _if_role(
            f"REVOKE ALL ON agent_rt.agent_memory, agent_rt.agent_skill FROM {ROLE}; "
            f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {ROLE};"
        )
    )
    op.drop_table("agent_turn_event", schema=SCHEMA)
    op.drop_index("agent_turn_session_idx", table_name="agent_turn", schema=SCHEMA)
    op.drop_table("agent_turn", schema=SCHEMA)
    op.drop_table("agent_message", schema=SCHEMA)
    op.drop_index("agent_session_recent_idx", table_name="agent_session", schema=SCHEMA)
    op.drop_table("agent_session", schema=SCHEMA)
