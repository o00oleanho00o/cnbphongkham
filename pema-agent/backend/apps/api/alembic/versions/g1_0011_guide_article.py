"""The staff guide gets its own table, ``clinic.guide_article``: the articles were text sources of the old
``agent.kb_document`` (the zalo-agent port), which goes away with that schema (docs/PLAN-db-baseline.md, C1).

An article is visible while its ``tags`` hold ``guide``; the first other tag is its topic. ``be_app`` gets the
table through the default privileges of schema ``clinic``.

Revision ID: g1_0011_guide_article
Revises: o3_0010_notifications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g1_0011_guide_article"
down_revision = "o3_0010_notifications"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql(
        "CREATE TABLE clinic.guide_article ("
        " clinic_id uuid NOT NULL REFERENCES clinic.clinic(id),"
        " id text NOT NULL CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,79}$'),"
        " title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),"
        " body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 200000),"
        " tags text[] NOT NULL DEFAULT '{}',"
        " created_at timestamptz NOT NULL DEFAULT now(),"
        " updated_at timestamptz NOT NULL DEFAULT now(),"
        " PRIMARY KEY (clinic_id, id))"
    )
    _sql(
        "CREATE TRIGGER guide_article_touch BEFORE UPDATE ON clinic.guide_article "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )


def downgrade() -> None:
    _sql("DROP TABLE clinic.guide_article")
