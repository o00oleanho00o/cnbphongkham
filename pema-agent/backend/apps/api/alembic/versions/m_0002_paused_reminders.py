"""reminders paused while a person handles the patient (package M, step M2c): ``agent.paused_reminders``.

Source: ``docs/PLAN-AI01-M.md`` section 8 and ``recipes/M/04-M2c-routing-oncall.md``. The tables of M1 have no
place for "a reminder that came due while the conversation was in HANDOFF_ROUTING or STAFF, with the text a
staff member may send by hand", so M2c adds ONE table; nothing of M1 changes (the decline reasons and the SLA
deadlines ride inside ``agent.handoff_requests.candidates``, the routing needs no new column).

One row per reminder (``UNIQUE (care_agent_id, dedupe_key)``: the same reminder arriving twice is one row).
``status`` is ``paused`` until the conversation is released to AUTO; then ``resumed`` (handed back to the turn
pipeline with a late label), ``dropped`` (past its meaning, ``resolution`` says why) or ``sent_by_staff``.
``prepared_text`` is a doctor-approved template, never model text. Single tenant: no row level security,
``clinic_id`` is the installation id; both runtime roles read and write the table like the other ``agent.*``
tables.

Revision ID: m_0002_paused_reminders
Revises: m_0001_care_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m_0002_paused_reminders"
down_revision = "m_0001_care_tables"
branch_labels = None
depends_on = None

EVENT_KINDS = (
    "milestone_due",
    "visit_overdue",
    "no_show",
    "dormant",
    "birthday",
    "session_completed",
)
STATUSES = ("paused", "resumed", "dropped", "sent_by_staff")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    _sql(f"""
        CREATE TABLE agent.paused_reminders (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            care_agent_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            patient_ref text NOT NULL CHECK (length(patient_ref) BETWEEN 1 AND 64),
            event_kind text NOT NULL CHECK (event_kind IN ({_q(EVENT_KINDS)})),
            rule text,
            due_at timestamptz NOT NULL,
            dedupe_key text NOT NULL CHECK (length(dedupe_key) BETWEEN 1 AND 300),
            prepared_text text,
            owner_user_id uuid,
            payload jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
            status text NOT NULL DEFAULT 'paused' CHECK (status IN ({_q(STATUSES)})),
            resolution text,
            paused_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (care_agent_id, dedupe_key),
            CHECK ((status = 'paused') = (resolved_at IS NULL)),
            FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents (clinic_id, id)
                ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, owner_user_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX paused_reminders_agent_idx ON agent.paused_reminders (care_agent_id, due_at) "
        "WHERE status = 'paused'"
    )
    _sql(
        "CREATE INDEX paused_reminders_owner_idx ON agent.paused_reminders (owner_user_id, due_at) "
        "WHERE status = 'paused'"
    )
    _sql(
        "CREATE TRIGGER paused_reminders_touch BEFORE UPDATE ON agent.paused_reminders "
        "FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON agent.paused_reminders TO be_app, agent_worker")


def downgrade() -> None:
    _sql("DROP TABLE IF EXISTS agent.paused_reminders")
