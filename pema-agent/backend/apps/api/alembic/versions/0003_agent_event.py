"""``clinic.agent_event``: the CRM's outbox of what the agent must hear (docs/PLAN-crm-plugin.md 3.4).

A row is written in the SAME transaction as the change it tells about (a visit of a person the agent chats with
was booked, moved, confirmed, cancelled...; the person agreed or refused reminders), so a change that rolls back
leaves no event and a change that commits always has one. A worker of the API process sends the rows, in the
order of ``id``, to the agent and marks them delivered; a row that fails is tried again later, a few times.
Payloads carry ids, times and statuses only: no name, no phone.

Clinic data of the CRM: the agent never reads this table, and no view, function or role is made for it
(.claude/rules/agent-crm-boundary.md, L3).

Revision ID: 0003_agent_event
Revises: 0002_patient_channel
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_agent_event"
down_revision = "0002_patient_channel"
branch_labels = None
depends_on = None

STATEMENTS = (
    """
    CREATE TABLE clinic.agent_event (
        id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
        clinic_id uuid NOT NULL,
        event_id uuid DEFAULT gen_random_uuid() NOT NULL,
        kind text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        attempts integer DEFAULT 0 NOT NULL,
        next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
        delivered_at timestamp with time zone,
        failed_at timestamp with time zone,
        last_error text,
        CONSTRAINT agent_event_pkey PRIMARY KEY (id),
        CONSTRAINT agent_event_event_id_key UNIQUE (event_id),
        CONSTRAINT agent_event_kind_check CHECK (kind IN ('appointment.changed', 'person.changed')),
        CONSTRAINT agent_event_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id)
    )
    """,
    "CREATE INDEX agent_event_due_idx ON clinic.agent_event USING btree (next_attempt_at, id) "
    "WHERE delivered_at IS NULL AND failed_at IS NULL",
    "GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.agent_event TO be_app",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE clinic.agent_event"))
