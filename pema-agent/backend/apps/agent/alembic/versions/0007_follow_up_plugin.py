"""Following up becomes the plugin ``follow_up``: live appointments move to cases, the switch to the plugin, the
table and the two settings go (``0007_follow_up_plugin.sql``). Going down brings the empty table and settings
back (``0003_follow_up.sql``); the cases stay where they are.

Revision ID: 0007_follow_up_plugin
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0007_follow_up_plugin"
down_revision = "0006_token_budget"
branch_labels = None
depends_on = None

SCHEMA_SQL = Path(__file__).with_suffix(".sql")
OLD_SQL = Path(__file__).with_name("0003_follow_up.sql")


def upgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute(OLD_SQL.read_text(encoding="utf-8"))
