"""Shared inbox, step O3: the delivery chain of the notification outbox, its log, push tokens, settings, quiet
hours, the one-time codes that link a personal Zalo, and the durable SLA checks.

Source: ``recipes/O/03-O3-notifications.md`` and ``docs/PLAN-AI01-O.md`` sections 1 (decision 4) and 4.
Single tenant: no row level security, ``clinic_id`` is the installation id.

* ``clinic.notification_outbox`` (O2) gets what the consumer needs: ``attempts``, ``next_attempt_at`` (when the
  row is looked at again; the bell step waits ``ack_timeout`` after the in-app step), ``chain_step`` (NULL: the
  first step of the recipient kind, ``bell``: waiting for the bell, ``done``), ``lease_until`` (a consumer
  that claimed the row; a crashed one lets go by itself), ``acked_at`` / ``acked_by``. ``recipient_kind`` also
  accepts ``on_call`` (the 24/7 contact of package M; the number is read again when the bell is sent, so it is
  never stored here).
* ``clinic.notification_log``: one row per attempt of one step (provider, attempt, status, latency, a short
  error code). Append only for the application role.
* ``clinic.push_token``: the token of a device, as a hash (the key) and encrypted (what the push provider
  needs). One token belongs to one user at a time.
* ``clinic.notify_setting``: one row per clinic: ack timeout (default 180 s), the team group id, which steps
  are on, the public base URL of the deep links. ``clinic.notify_preference``: quiet hours per operator.
* ``clinic.notify_link_code``: the one-time code of the bell linking (stored as a hash, expiring, single use).
* ``clinic.sla_check``: "look at this routing request again at T" asked by package M's ``SlaScheduler`` port;
  durable, deduplicated by key, claimed with a lease; a check that did not run stays ``pending``.

Downgrade: drops the new tables and columns. Rows of the outbox for the on-call contact cannot exist in the
older schema, so they are deleted first; every other row keeps its state. The downgrade target is
``o2_0010_assignment``.

Revision ID: o3_0010_notifications
Revises: o2_0010_assignment
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o3_0010_notifications"
down_revision = "o2_0010_assignment"
branch_labels = None
depends_on = None

OLD_RECIPIENT_KINDS = "'user', 'team_group'"
NEW_RECIPIENT_KINDS = "'user', 'team_group', 'on_call'"
PROVIDERS = "'in_app', 'push', 'zalo_bell', 'team_group'"
LOG_STATUSES = "'sent', 'failed', 'skipped'"
PLATFORMS = "'android', 'ios', 'web'"
SLA_STATES = "'pending', 'done', 'failed'"

OUTBOX = "clinic.notification_outbox"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    # ------------------------------------------------------------------ clinic.notification_outbox
    _sql(f"ALTER TABLE {OUTBOX} DROP CONSTRAINT IF EXISTS notification_outbox_recipient_kind_check")
    _sql(
        f"ALTER TABLE {OUTBOX} ADD CONSTRAINT notification_outbox_recipient_kind_check "
        f"CHECK (recipient_kind IN ({NEW_RECIPIENT_KINDS}))"
    )
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN attempts integer NOT NULL DEFAULT 0")
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now()")
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN chain_step text")
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN lease_until timestamptz")
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN acked_at timestamptz")
    _sql(f"ALTER TABLE {OUTBOX} ADD COLUMN acked_by uuid")
    _sql(
        f"ALTER TABLE {OUTBOX} ADD CONSTRAINT notification_outbox_chain_step_check "
        "CHECK (chain_step IS NULL OR chain_step IN ('bell', 'done'))"
    )
    _sql(f"ALTER TABLE {OUTBOX} ADD CONSTRAINT notification_outbox_attempts_check CHECK (attempts >= 0)")
    _sql(
        f"ALTER TABLE {OUTBOX} ADD CONSTRAINT notification_outbox_acked_by_fkey "
        "FOREIGN KEY (clinic_id, acked_by) REFERENCES clinic.user_account (clinic_id, id) "
        "ON DELETE SET NULL (acked_by)"
    )
    _sql(
        f"CREATE INDEX notification_outbox_due_idx ON {OUTBOX} (clinic_id, next_attempt_at) WHERE state = 'pending'"
    )
    _sql(
        f"CREATE INDEX notification_outbox_recipient_idx ON {OUTBOX} "
        "(clinic_id, recipient_user_id, created_at DESC) WHERE recipient_user_id IS NOT NULL"
    )

    # ------------------------------------------------------------------ clinic.notification_log
    _sql(f"""
        CREATE TABLE clinic.notification_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            outbox_id uuid NOT NULL,
            provider text NOT NULL CHECK (provider IN ({PROVIDERS})),
            attempt integer NOT NULL CHECK (attempt >= 1),
            status text NOT NULL CHECK (status IN ({LOG_STATUSES})),
            latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
            error_code text CHECK (error_code IS NULL OR length(error_code) <= 64),
            at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (clinic_id, outbox_id) REFERENCES {OUTBOX} (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX notification_log_outbox_idx ON clinic.notification_log (clinic_id, outbox_id, at)")
    _sql("GRANT SELECT, INSERT ON clinic.notification_log TO be_app")

    # ------------------------------------------------------------------ clinic.push_token
    _sql(f"""
        CREATE TABLE clinic.push_token (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            user_id uuid NOT NULL,
            platform text NOT NULL CHECK (platform IN ({PLATFORMS})),
            token_hash text NOT NULL CHECK (length(token_hash) = 64),
            token_enc text NOT NULL,
            last_seen timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, token_hash),
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX push_token_user_idx ON clinic.push_token (clinic_id, user_id)")
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.push_token TO be_app")

    # ------------------------------------------------------------------ clinic.notify_setting
    _sql("""
        CREATE TABLE clinic.notify_setting (
            clinic_id uuid PRIMARY KEY REFERENCES clinic.clinic (id),
            ack_timeout_s integer NOT NULL DEFAULT 180 CHECK (ack_timeout_s BETWEEN 30 AND 3600),
            team_group_id text CHECK (team_group_id IS NULL OR length(team_group_id) <= 200),
            in_app_enabled boolean NOT NULL DEFAULT true,
            push_enabled boolean NOT NULL DEFAULT false,
            bell_enabled boolean NOT NULL DEFAULT true,
            group_enabled boolean NOT NULL DEFAULT true,
            public_base_url text CHECK (public_base_url IS NULL OR length(public_base_url) <= 300),
            updated_at timestamptz NOT NULL DEFAULT now(),
            updated_by uuid
        )""")
    _sql(
        "CREATE TRIGGER notify_setting_touch BEFORE UPDATE ON clinic.notify_setting "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.notify_setting TO be_app")

    # ------------------------------------------------------------------ clinic.notify_preference
    _sql("""
        CREATE TABLE clinic.notify_preference (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            user_id uuid NOT NULL,
            quiet_start time,
            quiet_end time,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, user_id),
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id) ON DELETE CASCADE,
            CHECK ((quiet_start IS NULL) = (quiet_end IS NULL)),
            CHECK (quiet_start IS NULL OR quiet_start <> quiet_end)
        )""")
    _sql(
        "CREATE TRIGGER notify_preference_touch BEFORE UPDATE ON clinic.notify_preference "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.notify_preference TO be_app")

    # ------------------------------------------------------------------ clinic.notify_link_code
    _sql("""
        CREATE TABLE clinic.notify_link_code (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            user_id uuid NOT NULL,
            code_hash text NOT NULL CHECK (length(code_hash) = 64),
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, code_hash),
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql(
        "CREATE INDEX notify_link_code_user_idx ON clinic.notify_link_code (clinic_id, user_id, created_at DESC)"
    )
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.notify_link_code TO be_app")

    # ------------------------------------------------------------------ clinic.sla_check
    _sql(f"""
        CREATE TABLE clinic.sla_check (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            request_id uuid NOT NULL,
            idx integer NOT NULL CHECK (idx >= 0),
            due_at timestamptz NOT NULL,
            dedupe_key text NOT NULL CHECK (length(dedupe_key) BETWEEN 1 AND 200),
            state text NOT NULL DEFAULT 'pending' CHECK (state IN ({SLA_STATES})),
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            lease_until timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, dedupe_key)
        )""")
    _sql("CREATE INDEX sla_check_due_idx ON clinic.sla_check (clinic_id, due_at) WHERE state = 'pending'")
    _sql(
        "CREATE TRIGGER sla_check_touch BEFORE UPDATE ON clinic.sla_check "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.sla_check TO be_app")


def downgrade() -> None:
    _sql("DROP TABLE IF EXISTS clinic.sla_check")
    _sql("DROP TABLE IF EXISTS clinic.notify_link_code")
    _sql("DROP TABLE IF EXISTS clinic.notify_preference")
    _sql("DROP TABLE IF EXISTS clinic.notify_setting")
    _sql("DROP TABLE IF EXISTS clinic.push_token")
    _sql("DROP TABLE IF EXISTS clinic.notification_log")
    # The on-call rows cannot be told apart in the older schema (its CHECK knows two kinds only).
    _sql(f"DELETE FROM {OUTBOX} WHERE recipient_kind = 'on_call'")
    _sql("DROP INDEX IF EXISTS clinic.notification_outbox_recipient_idx")
    _sql("DROP INDEX IF EXISTS clinic.notification_outbox_due_idx")
    for constraint in (
        "notification_outbox_acked_by_fkey",
        "notification_outbox_attempts_check",
        "notification_outbox_chain_step_check",
    ):
        _sql(f"ALTER TABLE {OUTBOX} DROP CONSTRAINT IF EXISTS {constraint}")
    for column in ("acked_by", "acked_at", "lease_until", "chain_step", "next_attempt_at", "attempts"):
        _sql(f"ALTER TABLE {OUTBOX} DROP COLUMN IF EXISTS {column}")
    _sql(f"ALTER TABLE {OUTBOX} DROP CONSTRAINT IF EXISTS notification_outbox_recipient_kind_check")
    _sql(
        f"ALTER TABLE {OUTBOX} ADD CONSTRAINT notification_outbox_recipient_kind_check "
        f"CHECK (recipient_kind IN ({OLD_RECIPIENT_KINDS}))"
    )
