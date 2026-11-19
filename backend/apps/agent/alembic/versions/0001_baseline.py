"""agent_rt baseline: the whole core schema of the agent app in one revision (``0001_baseline.sql``).

Tables of plugins that keep their own (``cv_``, ``kb_``, ``sk_``) are not here: ``agent db migrate-plugins`` runs
each plugin's SQL files. The runtime role ``agent_rt_app`` gets its rights here when it exists already, and from
``agent db bootstrap-role`` otherwise.

Revision ID: 0001_baseline
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS agent_rt CASCADE")
