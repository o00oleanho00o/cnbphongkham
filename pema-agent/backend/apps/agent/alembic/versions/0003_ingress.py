"""agent_rt: conversations and the durable ingress queue; the trace learns the ``repair`` event.

``agent_conversation`` maps a channel conversation to its current epoch; the session id is
``agent:channel:conversation:epoch``, so starting over keeps the old session readable. ``agent_ingress`` stores
every inbound message before it is processed: the unique (tenant, agent, channel, external_id) makes a message
the channel sends twice run once, and a row left ``processing`` by a crash is queued again by the sweeper.

Revision ID: 0003_ingress
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_ingress"
down_revision = "0002_sessions_trace"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
ROLE = "agent_rt_app"
EVENT_KINDS_V2 = "'model_call', 'tool_call', 'compaction', 'memory_flush'"
EVENT_KINDS_V3 = f"{EVENT_KINDS_V2}, 'repair'"


def _if_role(statements: str) -> str:
    return (
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN "
        f"{statements} END IF; END $$"
    )


def _event_kinds(kinds: str) -> None:
    op.drop_constraint("agent_turn_event_kind", "agent_turn_event", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "agent_turn_event_kind", "agent_turn_event", f"kind IN ({kinds})", schema=SCHEMA
    )


def upgrade() -> None:
    _event_kinds(EVENT_KINDS_V3)
    op.create_table(
        "agent_conversation",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "agent", "channel", "conversation_id"),
        sa.CheckConstraint(
            "char_length(conversation_id) BETWEEN 1 AND 500", name="agent_conversation_id_size"
        ),
        sa.CheckConstraint("epoch >= 0", name="agent_conversation_epoch"),
        schema=SCHEMA,
    )
    op.create_table(
        "agent_ingress",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_kind", sa.Text(), nullable=True),
        sa.Column("reply", postgresql.JSONB(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "agent", "channel", "external_id", name="agent_ingress_once"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'done', 'failed', 'dead')", name="agent_ingress_status"
        ),
        sa.CheckConstraint(
            "char_length(external_id) BETWEEN 1 AND 200", name="agent_ingress_external_id_size"
        ),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 20000", name="agent_ingress_text_size"),
        sa.CheckConstraint("attempts >= 0", name="agent_ingress_attempts"),
        sa.CheckConstraint("(status = 'done') = (reply IS NOT NULL)", name="agent_ingress_reply_when_done"),
        schema=SCHEMA,
    )
    op.create_index(
        "agent_ingress_session_queue_idx",
        "agent_ingress",
        ["tenant_id", "session_id", "id"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "agent_ingress_open_idx",
        "agent_ingress",
        ["status", "received_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )
    op.execute(
        _if_role(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.agent_conversation, {SCHEMA}.agent_ingress "
            f"TO {ROLE}; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO {ROLE};"
        )
    )


def downgrade() -> None:
    op.drop_index("agent_ingress_open_idx", table_name="agent_ingress", schema=SCHEMA)
    op.drop_index("agent_ingress_session_queue_idx", table_name="agent_ingress", schema=SCHEMA)
    op.drop_table("agent_ingress", schema=SCHEMA)
    op.drop_table("agent_conversation", schema=SCHEMA)
    op.execute(f"DELETE FROM {SCHEMA}.agent_turn_event WHERE kind = 'repair'")
    _event_kinds(EVENT_KINDS_V2)
