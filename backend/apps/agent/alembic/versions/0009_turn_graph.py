"""A turn's trace may hold one event per node of a plugin's graph, and stop with ``graph``
(``0009_turn_graph.sql``).

Revision ID: 0009_turn_graph
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0009_turn_graph"
down_revision = "0008_agent_limits"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DELETE FROM agent_rt.agent_turn_event WHERE kind = 'node'")
    op.execute("UPDATE agent_rt.agent_turn SET stop = 'max_steps' WHERE stop = 'graph'")
    op.execute(
        "ALTER TABLE agent_rt.agent_turn DROP CONSTRAINT agent_turn_stop, ADD CONSTRAINT agent_turn_stop CHECK "
        "(stop = ANY (ARRAY['completed', 'max_steps', 'deadline', 'budget', 'loop', 'error']))"
    )
    op.execute(
        "ALTER TABLE agent_rt.agent_turn_event DROP CONSTRAINT agent_turn_event_kind, ADD CONSTRAINT "
        "agent_turn_event_kind CHECK (kind = ANY (ARRAY['model_call', 'tool_call', 'compaction', 'memory_flush', "
        "'repair', 'model_retry', 'guard', 'inbox']))"
    )
