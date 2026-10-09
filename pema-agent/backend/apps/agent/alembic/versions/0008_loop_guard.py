"""agent_rt: turn traces record the loop guard and turns stopped by their token budget or by going in circles.

Revision ID: 0008_loop_guard
"""

from __future__ import annotations

from alembic import op

revision = "0008_loop_guard"
down_revision = "0007_retry_deadline"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
STOPS_V7 = "'completed', 'max_steps', 'deadline', 'error'"
STOPS_V8 = "'completed', 'max_steps', 'deadline', 'budget', 'loop', 'error'"
EVENT_KINDS_V7 = "'model_call', 'tool_call', 'compaction', 'memory_flush', 'repair', 'model_retry'"
EVENT_KINDS_V8 = f"{EVENT_KINDS_V7}, 'guard'"


def _constraints(stops: str, kinds: str) -> None:
    op.drop_constraint("agent_turn_stop", "agent_turn", schema=SCHEMA, type_="check")
    op.create_check_constraint("agent_turn_stop", "agent_turn", f"stop IN ({stops})", schema=SCHEMA)
    op.drop_constraint("agent_turn_event_kind", "agent_turn_event", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "agent_turn_event_kind", "agent_turn_event", f"kind IN ({kinds})", schema=SCHEMA
    )


def upgrade() -> None:
    _constraints(STOPS_V8, EVENT_KINDS_V8)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.agent_turn_event WHERE kind = 'guard'")
    op.execute(f"UPDATE {SCHEMA}.agent_turn SET stop = 'max_steps' WHERE stop IN ('budget', 'loop')")
    _constraints(STOPS_V7, EVENT_KINDS_V7)
