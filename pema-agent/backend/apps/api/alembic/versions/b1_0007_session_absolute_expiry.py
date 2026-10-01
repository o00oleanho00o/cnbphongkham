"""B1: absolute lifetime of a dashboard session (SEC-24).

``clinic.auth_session.expires_at`` is the ROLLING (idle) expiry that ``refresh`` pushes forward. Without a
ceiling a stolen cookie lives as long as its thief keeps refreshing it. ``absolute_expires_at`` is that
ceiling: fixed at login (``created_at + PEMA_SESSION_ABSOLUTE_DAYS``, default 7 days), never moved by
``refresh``, and checked on every request. Past it the session is dead and the user signs in again.

Existing sessions are backfilled with ``created_at + 7 days`` (the default; a migration cannot read the
application setting). A session older than that stops working at its next request, which is the intended
effect for a cookie that has been alive for a week. The column is NOT NULL afterwards, so no code path can
create a session without a ceiling. RLS, grants and indexes of the table are unchanged.

Revision ID: b1_0007_session_absolute_expiry
Revises: g_0006_definer_search_path
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1_0007_session_absolute_expiry"
down_revision = "g_0006_definer_search_path"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("ALTER TABLE clinic.auth_session ADD COLUMN absolute_expires_at timestamptz")
    _sql("UPDATE clinic.auth_session SET absolute_expires_at = created_at + interval '7 days'")
    _sql("ALTER TABLE clinic.auth_session ALTER COLUMN absolute_expires_at SET NOT NULL")


def downgrade() -> None:
    _sql("ALTER TABLE clinic.auth_session DROP COLUMN IF EXISTS absolute_expires_at")
