"""The agent's window into the clinic is closed (docs/PLAN-db-baseline.md, C7 and rule L3): the few functions
of ``clinic_agent`` the API itself calls move to ``clinic``; the rest of the schema (identity linking, the
read views for the old agent) goes, and ``agent_worker`` loses what it held on the moved objects.

Revision ID: g3_0013_clinic_agent_gone
Revises: g2_0012_account_text
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g3_0013_clinic_agent_gone"
down_revision = "g2_0012_account_text"
branch_labels = None
depends_on = None

_MOVED = (
    "FUNCTION clinic_agent.record_inbound_message(text, text, text, text, text, text, timestamptz, text, text)",
    "FUNCTION clinic_agent.record_outbound_message(uuid, text, text, boolean, uuid, text, text)",
    "FUNCTION clinic_agent.create_review_item(text, text, text, text, uuid, text, jsonb, jsonb, text, text[], "
    "text, text)",
    "FUNCTION clinic_agent.record_retention_run(text, jsonb)",
    "FUNCTION clinic_agent.retention_purge_link_attempts(timestamptz, integer, boolean)",
    "VIEW clinic_agent.review_item_summary",
)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    # the 8-argument wrapper calls the 9-argument function by its old schema
    _sql(
        "DROP FUNCTION clinic_agent.record_inbound_message(text, text, text, text, text, text, timestamptz, text)"
    )
    for obj in _MOVED:
        _sql(f"ALTER {obj} SET SCHEMA clinic")
        kind, name = obj.split(" ", 1)
        name = name.replace("clinic_agent.", "clinic.")
        target = "TABLE " + name if kind == "VIEW" else obj.replace("clinic_agent.", "clinic.")
        _sql(f"REVOKE ALL ON {target} FROM agent_worker")
    _sql("DROP SCHEMA clinic_agent CASCADE")


def downgrade() -> None:
    raise NotImplementedError("forward only: the baseline of step 8 replaces this revision")
