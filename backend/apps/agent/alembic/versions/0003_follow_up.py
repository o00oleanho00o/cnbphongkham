"""The follow-up loop: the table of judged conversations and the switch in the agent settings
(``0003_follow_up.sql``).

Revision ID: 0003_follow_up
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0003_follow_up"
down_revision = "0002_agent_settings"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_rt.agent_follow_up")
    op.execute(
        "ALTER TABLE agent_rt.agent_settings DROP COLUMN follow_up_enabled, DROP COLUMN follow_up_channels"
    )
