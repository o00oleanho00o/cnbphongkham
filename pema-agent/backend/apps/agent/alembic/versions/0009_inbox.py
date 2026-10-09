"""agent_rt: turn traces record messages collected into one turn or steered into a running one.

Revision ID: 0009_inbox
"""

from __future__ import annotations

from alembic import op

revision = "0009_inbox"
down_revision = "0008_loop_guard"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
EVENT_KINDS_V8 = "'model_call', 'tool_call', 'compaction', 'memory_flush', 'repair', 'model_retry', 'guard'"
EVENT_KINDS_V9 = f"{EVENT_KINDS_V8}, 'inbox'"


def _event_kinds(kinds: str) -> None:
    op.drop_constraint("agent_turn_event_kind", "agent_turn_event", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "agent_turn_event_kind", "agent_turn_event", f"kind IN ({kinds})", schema=SCHEMA
    )


def upgrade() -> None:
    _event_kinds(EVENT_KINDS_V9)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.agent_turn_event WHERE kind = 'inbox'")
    _event_kinds(EVENT_KINDS_V8)
