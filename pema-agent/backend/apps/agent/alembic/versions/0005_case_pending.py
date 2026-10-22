"""Cases: the decision of a steering tool, kept per turn (``0005_case_pending.sql``).

Revision ID: 0005_case_pending
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0005_case_pending"
down_revision = "0004_cases"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_rt.agent_case DROP CONSTRAINT IF EXISTS agent_case_pending, DROP COLUMN pending"
    )
