"""Settings an admin changes on the dashboard: timezone, failure reply, variables, persona, rules, memory and
which tools are on (``0002_agent_settings.sql``).

Revision ID: 0002_agent_settings
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0002_agent_settings"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_rt.agent_settings")
