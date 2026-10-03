"""tags on knowledge-base sources, so the staff guide can be KB-backed (package U, step U7).

Source: ``docs/PLAN-AI01-U.md`` section 3 (row ask / guide) and ``recipes/U/08-U7-guide-ask-crm.md``. The old
Clinic Web guide was a fixed array of articles; here an article is a text source of the knowledge base with
the tag ``guide``. ONE column is added to ``agent.kb_document``: ``tags text[]`` (default empty, at most 10
tags of 1 to 40 characters, no duplicates are stored by the action). Nothing of the ingest, search or binding
code reads it: an article stays an ordinary source for the agents (default-deny binding unchanged).

Single tenant: no row level security; both runtime roles keep the table-level grants they already have.

Revision ID: u7_0001_guide_tags
Revises: m_0002_paused_reminders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u7_0001_guide_tags"
down_revision = "m_0002_paused_reminders"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql(
        "ALTER TABLE agent.kb_document ADD COLUMN tags text[] NOT NULL DEFAULT '{}' "
        "CONSTRAINT kb_document_tags_count CHECK (cardinality(tags) <= 10)"
    )
    _sql("CREATE INDEX kb_document_tags_gin ON agent.kb_document USING gin (tags)")


def downgrade() -> None:
    _sql("DROP INDEX IF EXISTS agent.kb_document_tags_gin")
    _sql("ALTER TABLE agent.kb_document DROP COLUMN IF EXISTS tags")
