"""CRM rules (package B2): remember which session already produced the D+30 recommendation.

crm-automation.js ``refresh()`` sets ``recommendationAt = latest Laser CO2 session + 30 days`` only when
``p.crm.lastProtocolSession !== latest.id`` and then stores that session id. The id is what keeps a doctor's later
edit of the recommended date from being overwritten on the next run. ``clinic.patient`` had no place for it.

One nullable column, no new table, no new grant: ``be_app`` already has DML on ``clinic.patient`` and RLS applies
unchanged. ``clinic_agent`` views list their columns explicitly, so the agent side does not see it.

Revision ID: b2_0001_crm_protocol_marker
Revises: 0003_clinic_agent_access
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2_0001_crm_protocol_marker"
down_revision = "0003_clinic_agent_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE clinic.patient ADD COLUMN IF NOT EXISTS last_protocol_session_id text"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE clinic.patient DROP COLUMN IF EXISTS last_protocol_session_id"))
