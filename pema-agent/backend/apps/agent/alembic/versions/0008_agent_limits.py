"""The limits of a turn and of compaction in the agent settings, and the context window of each model
(``0008_agent_limits.sql``).

Revision ID: 0008_agent_limits
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0008_agent_limits"
down_revision = "0007_follow_up_plugin"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")
LIMITS = (
    "max_steps",
    "max_output_tokens",
    "max_turn_s",
    "max_turn_tokens",
    "stop_after_repeats",
    "error_streak_stop",
    "compact_at",
    "keep_recent_ratio",
    "max_parallel_tools",
    "max_tool_calls_per_step",
)


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("ALTER TABLE agent_rt.agent_model_settings DROP COLUMN window_tokens")
    op.execute("ALTER TABLE agent_rt.agent_model_entry DROP COLUMN window_tokens")
    op.execute(
        "ALTER TABLE agent_rt.agent_settings DROP CONSTRAINT agent_settings_limits, "
        + ", ".join(f"DROP COLUMN {name}" for name in LIMITS)
    )
