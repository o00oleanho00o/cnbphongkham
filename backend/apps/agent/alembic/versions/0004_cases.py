"""Cases: the tables of the loop outside a turn and two settings of the agent (``0004_cases.sql``).

Revision ID: 0004_cases
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0004_cases"
down_revision = "0003_follow_up"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_rt.agent_case_event")
    op.execute("DROP TABLE IF EXISTS agent_rt.agent_case")
    op.execute(
        "ALTER TABLE agent_rt.agent_settings DROP CONSTRAINT IF EXISTS agent_settings_proactive_cap, "
        "DROP COLUMN cases_enabled, DROP COLUMN proactive_per_person_per_day"
    )
