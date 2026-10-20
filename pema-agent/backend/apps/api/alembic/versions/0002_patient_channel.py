"""``clinic.patient_channel``: which patient a chat person is (docs/PLAN-crm-plugin.md).

One row per (channel, person of that channel), written by the agent gateway the first time someone saves a
contact in a chat. It is clinic data the gateway reads on the server; the agent never reads it, and no view,
function or role is made for it (.claude/rules/agent-crm-boundary.md, L3).

Revision ID: 0002_patient_channel
Revises: 0001_baseline
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_patient_channel"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

STATEMENTS = (
    """
    CREATE TABLE clinic.patient_channel (
        id uuid DEFAULT gen_random_uuid() NOT NULL,
        clinic_id uuid NOT NULL,
        channel text NOT NULL,
        external_id text NOT NULL,
        patient_id uuid NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT patient_channel_pkey PRIMARY KEY (id),
        CONSTRAINT patient_channel_clinic_id_id_key UNIQUE (clinic_id, id),
        CONSTRAINT patient_channel_person_key UNIQUE (clinic_id, channel, external_id),
        CONSTRAINT patient_channel_channel_check CHECK (length(channel) BETWEEN 1 AND 64),
        CONSTRAINT patient_channel_external_id_check CHECK (length(external_id) BETWEEN 1 AND 128),
        CONSTRAINT patient_channel_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id),
        CONSTRAINT patient_channel_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id)
            REFERENCES clinic.patient(clinic_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX patient_channel_patient_idx ON clinic.patient_channel USING btree (clinic_id, patient_id)",
    "GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_channel TO be_app",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE clinic.patient_channel"))
