"""agent_rt: turn traces record retried model calls and turns cut short by their time limit.

Revision ID: 0007_retry_deadline
"""

from __future__ import annotations

from alembic import op

revision = "0007_retry_deadline"
down_revision = "0006_delivery"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
STOPS_V2 = "'completed', 'max_steps', 'error'"
STOPS_V7 = "'completed', 'max_steps', 'deadline', 'error'"
EVENT_KINDS_V3 = "'model_call', 'tool_call', 'compaction', 'memory_flush', 'repair'"
EVENT_KINDS_V7 = f"{EVENT_KINDS_V3}, 'model_retry'"


def _constraints(stops: str, kinds: str) -> None:
    op.drop_constraint("agent_turn_stop", "agent_turn", schema=SCHEMA, type_="check")
    op.create_check_constraint("agent_turn_stop", "agent_turn", f"stop IN ({stops})", schema=SCHEMA)
    op.drop_constraint("agent_turn_event_kind", "agent_turn_event", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "agent_turn_event_kind", "agent_turn_event", f"kind IN ({kinds})", schema=SCHEMA
    )


def upgrade() -> None:
    _constraints(STOPS_V7, EVENT_KINDS_V7)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.agent_turn_event WHERE kind = 'model_retry'")
    op.execute(f"UPDATE {SCHEMA}.agent_turn SET stop = 'max_steps' WHERE stop = 'deadline'")
    _constraints(STOPS_V2, EVENT_KINDS_V3)
