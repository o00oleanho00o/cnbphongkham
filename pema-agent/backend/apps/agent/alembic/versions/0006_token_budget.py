"""The token budget of a session and of the agent per day: two settings and an index (``0006_token_budget.sql``).

Revision ID: 0006_token_budget
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0006_token_budget"
down_revision = "0005_case_pending"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS agent_rt.agent_turn_agent_started_idx")
    op.execute(
        "ALTER TABLE agent_rt.agent_settings DROP CONSTRAINT IF EXISTS agent_settings_tokens_per_session, "
        "DROP CONSTRAINT IF EXISTS agent_settings_tokens_per_day, "
        "DROP COLUMN tokens_per_session_per_day, DROP COLUMN tokens_per_day"
    )
