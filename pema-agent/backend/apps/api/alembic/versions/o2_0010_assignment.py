"""Shared inbox, step O2: assignment history, optimistic lock on the holder, notification outbox.

Source: ``recipes/O/02-O2-assignment-lock-takeover.md`` and ``docs/PLAN-AI01-O.md`` sections 1 (decision 3) and 4.
Single tenant: no row level security, ``clinic_id`` is the installation id.

* ``clinic.conversation.assignment_version`` (integer, default 1): bumped by every change of the holder. The
  holder itself stays ``clinic.conversation.assigned_user_id`` (one column, so one holder per thread by
  construction); the new column is the optimistic lock of the assignment actions.
* ``clinic.conversation_assignment``: the history, one row per change (``claim``, ``takeover``, ``release``,
  ``shift_end``, ``assign``) with the previous holder, the reason (a takeover needs one, enforced by a CHECK),
  the time and who made the change. Append only for the application role (SELECT and INSERT, no UPDATE, no
  DELETE). The user columns are set to NULL when the account is deleted (history is kept), the rows go with
  their conversation. Conversations that already have a holder get one ``assign`` row (``by`` NULL) so the
  history is complete from the day the table exists.
* ``clinic.notification_outbox``: what must be told to whom. ``recipient_kind`` is ``user`` (with the user id)
  or ``team_group``; the payload is PII-free JSON (the action validates it before the insert). ``state`` is
  ``pending`` until step O3 delivers it. O2 only writes rows: there is no consumer yet.

Downgrade: drops the outbox, the history and the column. Nothing in the older schema can hold them, and
dropping a table or a column never fails on rows that use the new values. The downgrade target is
``o1_0010_identities_roster``.

Revision ID: o2_0010_assignment
Revises: o1_0010_identities_roster
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "o2_0010_assignment"
down_revision = "o1_0010_identities_roster"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

KINDS = ("claim", "takeover", "release", "shift_end", "assign")
RECIPIENT_KINDS = ("user", "team_group")
STATES = ("pending", "sent", "failed", "skipped")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    # ------------------------------------------------------------------ clinic.conversation
    _sql("ALTER TABLE clinic.conversation ADD COLUMN assignment_version integer NOT NULL DEFAULT 1")
    _sql(
        "ALTER TABLE clinic.conversation ADD CONSTRAINT conversation_assignment_version_check "
        "CHECK (assignment_version >= 1)"
    )

    # ------------------------------------------------------------------ clinic.conversation_assignment
    _sql(f"""
        CREATE TABLE clinic.conversation_assignment (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            conversation_id uuid NOT NULL,
            user_id uuid,
            kind text NOT NULL CHECK (kind IN ({_in(KINDS)})),
            previous_user_id uuid,
            reason text CHECK (reason IS NULL OR length(reason) <= 500),
            at timestamptz NOT NULL DEFAULT now(),
            by uuid,
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation (clinic_id, id)
                ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id)
                ON DELETE SET NULL (user_id),
            FOREIGN KEY (clinic_id, previous_user_id) REFERENCES clinic.user_account (clinic_id, id)
                ON DELETE SET NULL (previous_user_id),
            FOREIGN KEY (clinic_id, by) REFERENCES clinic.user_account (clinic_id, id)
                ON DELETE SET NULL (by),
            CHECK (kind <> 'takeover' OR (reason IS NOT NULL AND length(btrim(reason)) > 0))
        )""")
    _sql(
        "CREATE INDEX conversation_assignment_conversation_idx "
        "ON clinic.conversation_assignment (clinic_id, conversation_id, at DESC)"
    )
    _sql("GRANT SELECT, INSERT ON clinic.conversation_assignment TO be_app")
    _sql("""
        INSERT INTO clinic.conversation_assignment (clinic_id, conversation_id, user_id, kind, at)
        SELECT c.clinic_id, c.id, c.assigned_user_id, 'assign', now()
          FROM clinic.conversation c
         WHERE c.assigned_user_id IS NOT NULL""")

    # ------------------------------------------------------------------ clinic.notification_outbox
    _sql(f"""
        CREATE TABLE clinic.notification_outbox (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            kind text NOT NULL CHECK (length(kind) BETWEEN 1 AND 64),
            recipient_kind text NOT NULL CHECK (recipient_kind IN ({_in(RECIPIENT_KINDS)})),
            recipient_user_id uuid,
            conversation_id uuid,
            payload jsonb NOT NULL,
            state text NOT NULL DEFAULT 'pending' CHECK (state IN ({_in(STATES)})),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, recipient_user_id) REFERENCES clinic.user_account (clinic_id, id)
                ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation (clinic_id, id)
                ON DELETE CASCADE,
            CHECK ((recipient_kind = 'user') = (recipient_user_id IS NOT NULL))
        )""")
    _sql(
        "CREATE INDEX notification_outbox_pending_idx ON clinic.notification_outbox "
        "(clinic_id, created_at) WHERE state = 'pending'"
    )
    _sql(
        "CREATE INDEX notification_outbox_conversation_idx ON clinic.notification_outbox "
        "(clinic_id, conversation_id)"
    )
    _sql(
        "CREATE TRIGGER notification_outbox_touch BEFORE UPDATE ON clinic.notification_outbox "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.notification_outbox TO be_app")


def downgrade() -> None:
    _sql("DROP TABLE IF EXISTS clinic.notification_outbox")
    _sql("DROP TABLE IF EXISTS clinic.conversation_assignment")
    _sql("ALTER TABLE clinic.conversation DROP CONSTRAINT IF EXISTS conversation_assignment_version_check")
    _sql("ALTER TABLE clinic.conversation DROP COLUMN IF EXISTS assignment_version")
