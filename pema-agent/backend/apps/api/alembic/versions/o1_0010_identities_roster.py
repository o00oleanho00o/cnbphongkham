"""Shared inbox, step O1: identities, per-identity limits, thread-to-identity link, roster.

Source: ``recipes/O/01-O1-identities-limits-roster.md`` and ``docs/PLAN-AI01-O.md`` sections 2 and 3. Single
tenant: no row level security, ``clinic_id`` is the installation id.

* ``agent.accounts.purpose`` (``customer`` | ``internal``, default ``customer``): an ``internal`` account is the
  clinic's own notifier (bell to the operators, team group). It can never be the identity of a conversation.
  ``send_gap_min_s``, ``send_gap_max_s`` and ``daily_cap`` are nullable per-identity overrides of the one
  row per channel in ``clinic.channel_setting`` (NULL = use the channel row).
* ``clinic.conversation.account_id`` + the composite foreign key ``(clinic_id, account_id)`` to
  ``agent.accounts``. ``ON DELETE SET NULL (account_id)`` (Postgres 15+ column list, ``clinic_id`` is NOT
  NULL and must stay): deleting an account detaches its conversations instead of deleting history. Two
  triggers keep the rule "a conversation never points to an internal account" in the database: one on the
  conversation (insert or update of ``account_id``) and one on the account (``purpose`` moving to
  ``internal`` while conversations still point at it).
* Backfill (``backfill_conversation_accounts``): a conversation gets the account ONLY when ``agent.threads``
  proves the pair, that is exactly one customer account of the same channel has a thread whose ``thread_id``
  is the conversation's ``external_ref``. Zero or several candidates leave the column NULL (a later inbound
  message fills it: the inbox function only ever fills a NULL). A dry run counts first; the counts go to the
  alembic log.
* ``clinic.account_roster``: who covers which identity when (a set of weekdays or one explicit date, a start
  and an end time; an end earlier than the start means the slot ends the next morning). The "user holds an
  assignable role" rule is checked by the action (it depends on the current role of the account, which
  changes).
* ``clinic.staff_profiles.notify_zalo_user_id`` and ``notify_zalo_consented_at`` (both set or both NULL): the
  operator's personal Zalo id for the notification bell, written only after the operator links it themselves
  (step O3). The worker's view ``clinic_agent.staff_profile`` names its columns, so these are NOT exposed to
  it.
* ``clinic_agent.record_inbound_message`` gets a ninth parameter ``p_account_id``. The old eight-parameter
  function stays as a thin wrapper (account NULL) so nothing that still calls it breaks. An account id the
  installation does not know is stored as NULL (an inbound message must never be lost over a configuration
  gap); an INTERNAL account raises.

Downgrade: restores the eight-parameter function body of ``st_0009_single_tenant``, then drops everything
above. Rows that use the new values (an internal account, a roster entry, a conversation with an account id,
a consented notify id) are dropped with their columns or tables: nothing in the older schema can hold them,
and dropping a column never fails on data. The downgrade target is ``u9_0010_patient_parity``.

Revision ID: o1_0010_identities_roster
Revises: u9_0010_patient_parity
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import sqlalchemy as sa
from alembic import op

revision = "o1_0010_identities_roster"
down_revision = "u9_0010_patient_parity"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
RECORD_INBOUND_9 = (
    "clinic_agent.record_inbound_message(text, text, text, text, text, text, timestamptz, text, text)"
)

_PROOF = """
    SELECT c.id AS conversation_id, c.clinic_id, min(t.account_id) AS account_id,
           count(DISTINCT t.account_id) AS candidates
      FROM clinic.conversation c
      JOIN agent.threads t ON t.clinic_id = c.clinic_id AND t.thread_id = c.external_ref
      JOIN agent.accounts a ON a.clinic_id = t.clinic_id AND a.id = t.account_id
                           AND a.channel = c.channel AND a.purpose = 'customer'
     WHERE c.account_id IS NULL
     GROUP BY c.id, c.clinic_id"""


class BackfillCounts(NamedTuple):
    """What the backfill sets (``set``) and what it leaves NULL (``ambiguous`` and ``unproven``)."""

    set: int
    ambiguous: int
    unproven: int

    @property
    def left_null(self) -> int:
        return self.ambiguous + self.unproven


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def backfill_conversation_accounts(connection: sa.Connection, *, dry_run: bool) -> BackfillCounts:
    """Count (``dry_run``) or set ``clinic.conversation.account_id`` where ``agent.threads`` proves it."""
    counts = connection.execute(
        sa.text(
            f"""
            WITH proof AS ({_PROOF})
            SELECT count(*) FILTER (WHERE candidates = 1) AS n_set,
                   count(*) FILTER (WHERE candidates > 1) AS n_ambiguous,
                   (SELECT count(*) FROM clinic.conversation WHERE account_id IS NULL)
                       - count(*) AS n_unproven
              FROM proof"""
        )
    ).one()
    result = BackfillCounts(set=counts.n_set, ambiguous=counts.n_ambiguous, unproven=counts.n_unproven)
    if not dry_run and result.set:
        connection.execute(
            sa.text(
                f"""
                WITH proof AS ({_PROOF})
                UPDATE clinic.conversation c SET account_id = p.account_id
                  FROM proof p
                 WHERE p.candidates = 1 AND c.clinic_id = p.clinic_id AND c.id = p.conversation_id"""
            )
        )
    return result


def _function_8_original() -> str:
    """The eight-parameter body as ``st_0009_single_tenant`` left it (``ctx.the_clinic_id()``)."""
    return """
        CREATE OR REPLACE FUNCTION clinic_agent.record_inbound_message(
            p_channel text, p_update_id text, p_thread_id text, p_external_user_id text,
            p_display_name text, p_text text, p_sent_at timestamptz, p_actor_type text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx, pg_temp AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity uuid;
            v_patient uuid;
            v_conv uuid;
            v_msg uuid;
            v_conv_patient uuid;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            IF p_update_id IS NULL OR p_update_id = '' THEN
                RAISE EXCEPTION 'update_id is the idempotency key';
            END IF;

            INSERT INTO clinic.channel_identity AS i
                   (clinic_id, channel, external_user_id, display_name, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, NULLIF(p_display_name, ''), now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE
               SET last_inbound_at = now(),
                   display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), i.display_name)
            RETURNING i.id, CASE WHEN i.verification_status = 'verified' THEN i.patient_id END
              INTO v_identity, v_patient;

            INSERT INTO clinic.conversation AS c
                   (clinic_id, channel, external_ref, patient_id, identity_id, last_message_at, last_inbound_at)
            VALUES (v_clinic, p_channel, p_thread_id, v_patient, v_identity,
                    COALESCE(p_sent_at, now()), COALESCE(p_sent_at, now()))
            ON CONFLICT (clinic_id, channel, external_ref) DO UPDATE
               SET identity_id = COALESCE(c.identity_id, EXCLUDED.identity_id),
                   patient_id = COALESCE(c.patient_id, EXCLUDED.patient_id)
            RETURNING c.id, c.patient_id INTO v_conv, v_conv_patient;

            INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body,
                                        status, update_id, sent_at)
            VALUES (v_clinic, v_conv, p_channel, 'inbound', 'patient', p_text, 'received', p_update_id,
                    p_sent_at)
            ON CONFLICT (clinic_id, channel, update_id) WHERE update_id IS NOT NULL DO NOTHING
            RETURNING id INTO v_msg;

            IF v_msg IS NULL THEN
                SELECT m.id INTO v_msg FROM clinic.message m
                 WHERE m.clinic_id = v_clinic AND m.channel = p_channel AND m.update_id = p_update_id;
                RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, true;
                RETURN;
            END IF;

            UPDATE clinic.conversation c
               SET unread_count = c.unread_count + 1,
                   last_message_at = GREATEST(COALESCE(c.last_message_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   last_inbound_at = GREATEST(COALESCE(c.last_inbound_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   status = CASE WHEN c.status = 'closed' THEN 'open' ELSE c.status END,
                   version = c.version + 1
             WHERE c.clinic_id = v_clinic AND c.id = v_conv;

            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, p_actor_type, 'message.record_inbound', 'message', v_msg::text,
                    jsonb_build_object('conversation_id', v_conv, 'channel', p_channel));
            RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, false;
        END $$"""


def _function_9() -> str:
    return """
        CREATE FUNCTION clinic_agent.record_inbound_message(
            p_channel text, p_update_id text, p_thread_id text, p_external_user_id text,
            p_display_name text, p_text text, p_sent_at timestamptz, p_actor_type text, p_account_id text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, agent, ctx, pg_temp AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity uuid;
            v_patient uuid;
            v_conv uuid;
            v_msg uuid;
            v_conv_patient uuid;
            v_account text;
            v_purpose text;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            IF p_update_id IS NULL OR p_update_id = '' THEN
                RAISE EXCEPTION 'update_id is the idempotency key';
            END IF;

            -- the identity that received the message: an unknown id is stored as NULL (never lose a message
            -- over a configuration gap), an internal notifier is refused
            IF p_account_id IS NOT NULL AND p_account_id <> '' THEN
                SELECT a.id, a.purpose INTO v_account, v_purpose FROM agent.accounts a
                 WHERE a.clinic_id = v_clinic AND a.id = p_account_id;
                IF v_purpose = 'internal' THEN
                    RAISE EXCEPTION 'an internal account cannot be the identity of a conversation'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            INSERT INTO clinic.channel_identity AS i
                   (clinic_id, channel, external_user_id, display_name, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, NULLIF(p_display_name, ''), now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE
               SET last_inbound_at = now(),
                   display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), i.display_name)
            RETURNING i.id, CASE WHEN i.verification_status = 'verified' THEN i.patient_id END
              INTO v_identity, v_patient;

            INSERT INTO clinic.conversation AS c
                   (clinic_id, channel, external_ref, patient_id, identity_id, account_id,
                    last_message_at, last_inbound_at)
            VALUES (v_clinic, p_channel, p_thread_id, v_patient, v_identity, v_account,
                    COALESCE(p_sent_at, now()), COALESCE(p_sent_at, now()))
            ON CONFLICT (clinic_id, channel, external_ref) DO UPDATE
               SET identity_id = COALESCE(c.identity_id, EXCLUDED.identity_id),
                   patient_id = COALESCE(c.patient_id, EXCLUDED.patient_id),
                   account_id = COALESCE(c.account_id, EXCLUDED.account_id)
            RETURNING c.id, c.patient_id INTO v_conv, v_conv_patient;

            INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body,
                                        status, update_id, sent_at)
            VALUES (v_clinic, v_conv, p_channel, 'inbound', 'patient', p_text, 'received', p_update_id,
                    p_sent_at)
            ON CONFLICT (clinic_id, channel, update_id) WHERE update_id IS NOT NULL DO NOTHING
            RETURNING id INTO v_msg;

            IF v_msg IS NULL THEN
                SELECT m.id INTO v_msg FROM clinic.message m
                 WHERE m.clinic_id = v_clinic AND m.channel = p_channel AND m.update_id = p_update_id;
                RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, true;
                RETURN;
            END IF;

            UPDATE clinic.conversation c
               SET unread_count = c.unread_count + 1,
                   last_message_at = GREATEST(COALESCE(c.last_message_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   last_inbound_at = GREATEST(COALESCE(c.last_inbound_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   status = CASE WHEN c.status = 'closed' THEN 'open' ELSE c.status END,
                   version = c.version + 1
             WHERE c.clinic_id = v_clinic AND c.id = v_conv;

            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, p_actor_type, 'message.record_inbound', 'message', v_msg::text,
                    jsonb_build_object('conversation_id', v_conv, 'channel', p_channel));
            RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, false;
        END $$"""


def _function_8_wrapper() -> str:
    return """
        CREATE OR REPLACE FUNCTION clinic_agent.record_inbound_message(
            p_channel text, p_update_id text, p_thread_id text, p_external_user_id text,
            p_display_name text, p_text text, p_sent_at timestamptz, p_actor_type text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx, pg_temp AS $$
        BEGIN
            RETURN QUERY SELECT * FROM clinic_agent.record_inbound_message(
                p_channel, p_update_id, p_thread_id, p_external_user_id, p_display_name, p_text, p_sent_at,
                p_actor_type, NULL::text);
        END $$"""


def upgrade() -> None:
    # ------------------------------------------------------------------ agent.accounts
    _sql("ALTER TABLE agent.accounts ADD COLUMN purpose text NOT NULL DEFAULT 'customer'")
    _sql(
        "ALTER TABLE agent.accounts ADD CONSTRAINT accounts_purpose_check "
        "CHECK (purpose IN ('customer', 'internal'))"
    )
    _sql("ALTER TABLE agent.accounts ADD COLUMN send_gap_min_s integer")
    _sql("ALTER TABLE agent.accounts ADD COLUMN send_gap_max_s integer")
    _sql("ALTER TABLE agent.accounts ADD COLUMN daily_cap integer")
    _sql(
        "ALTER TABLE agent.accounts ADD CONSTRAINT accounts_send_limits_check CHECK ("
        "(send_gap_min_s IS NULL OR send_gap_min_s >= 0) "
        "AND (send_gap_max_s IS NULL OR send_gap_max_s >= 0) "
        "AND (send_gap_min_s IS NULL OR send_gap_max_s IS NULL OR send_gap_max_s >= send_gap_min_s) "
        "AND (daily_cap IS NULL OR daily_cap >= 0))"
    )

    # ------------------------------------------------------------------ clinic.conversation.account_id
    _sql("ALTER TABLE clinic.conversation ADD COLUMN account_id text")
    _sql(
        "ALTER TABLE clinic.conversation ADD CONSTRAINT conversation_account_fk "
        "FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts (clinic_id, id) "
        "ON DELETE SET NULL (account_id)"
    )
    _sql(
        "CREATE INDEX conversation_account_idx ON clinic.conversation "
        "(clinic_id, account_id, status, last_message_at DESC)"
    )
    _sql("""
        CREATE FUNCTION clinic.conversation_account_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, agent, pg_temp AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM agent.accounts a
                        WHERE a.clinic_id = NEW.clinic_id AND a.id = NEW.account_id
                          AND a.purpose = 'internal') THEN
                RAISE EXCEPTION 'an internal account cannot be the identity of a conversation'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
    _sql("REVOKE ALL ON FUNCTION clinic.conversation_account_guard() FROM PUBLIC")
    _sql(
        "CREATE TRIGGER conversation_account_guard "
        "BEFORE INSERT OR UPDATE OF account_id ON clinic.conversation "
        "FOR EACH ROW WHEN (NEW.account_id IS NOT NULL) EXECUTE FUNCTION clinic.conversation_account_guard()"
    )
    _sql("""
        CREATE FUNCTION clinic.account_purpose_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, agent, pg_temp AS $$
        BEGIN
            IF NEW.purpose = 'internal' AND EXISTS (SELECT 1 FROM clinic.conversation c
                                                     WHERE c.clinic_id = NEW.clinic_id
                                                       AND c.account_id = NEW.id) THEN
                RAISE EXCEPTION 'conversations still point at this account'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
    _sql("REVOKE ALL ON FUNCTION clinic.account_purpose_guard() FROM PUBLIC")
    _sql(
        "CREATE TRIGGER account_purpose_guard BEFORE UPDATE OF purpose ON agent.accounts "
        "FOR EACH ROW WHEN (NEW.purpose = 'internal' AND OLD.purpose IS DISTINCT FROM NEW.purpose) "
        "EXECUTE FUNCTION clinic.account_purpose_guard()"
    )

    connection = op.get_bind()
    dry = backfill_conversation_accounts(connection, dry_run=True)
    log.info(
        "O1 backfill dry run: %d conversations would get an account, %d left NULL (%d ambiguous, %d unproven)",
        dry.set,
        dry.left_null,
        dry.ambiguous,
        dry.unproven,
    )
    done = backfill_conversation_accounts(connection, dry_run=False)
    log.info("O1 backfill: %d conversations got an account, %d left NULL", done.set, done.left_null)

    # ------------------------------------------------------------------ clinic.account_roster
    days = ", ".join(f"'{d}'" for d in WEEKDAYS)
    _sql(f"""
        CREATE TABLE clinic.account_roster (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            account_id text NOT NULL,
            user_id uuid NOT NULL,
            weekdays text[],
            on_date date,
            start_time time NOT NULL,
            end_time time NOT NULL,
            note text CHECK (note IS NULL OR length(note) <= 200),
            created_by uuid,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
                ON DELETE SET NULL (created_by),
            CHECK ((weekdays IS NULL) <> (on_date IS NULL)),
            CHECK (weekdays IS NULL OR (cardinality(weekdays) BETWEEN 1 AND 7 AND weekdays <@ ARRAY[{days}])),
            CHECK (start_time <> end_time)
        )""")
    _sql("CREATE INDEX account_roster_account_idx ON clinic.account_roster (clinic_id, account_id)")
    _sql("CREATE INDEX account_roster_user_idx ON clinic.account_roster (clinic_id, user_id)")
    _sql(
        "CREATE TRIGGER account_roster_touch BEFORE UPDATE ON clinic.account_roster "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.account_roster TO be_app")

    # ------------------------------------------------------------------ clinic.staff_profiles
    _sql("ALTER TABLE clinic.staff_profiles ADD COLUMN notify_zalo_user_id text")
    _sql("ALTER TABLE clinic.staff_profiles ADD COLUMN notify_zalo_consented_at timestamptz")
    _sql(
        "ALTER TABLE clinic.staff_profiles ADD CONSTRAINT staff_profiles_notify_consent CHECK "
        "((notify_zalo_user_id IS NULL) = (notify_zalo_consented_at IS NULL))"
    )

    # ------------------------------------------------------------------ record_inbound_message
    _sql(_function_9())
    _sql(f"REVOKE ALL ON FUNCTION {RECORD_INBOUND_9} FROM PUBLIC")
    _sql(f"GRANT EXECUTE ON FUNCTION {RECORD_INBOUND_9} TO agent_worker, be_app")
    _sql(_function_8_wrapper())


def downgrade() -> None:
    _sql(_function_8_original())
    _sql(f"DROP FUNCTION IF EXISTS {RECORD_INBOUND_9}")

    _sql("ALTER TABLE clinic.staff_profiles DROP CONSTRAINT IF EXISTS staff_profiles_notify_consent")
    _sql("ALTER TABLE clinic.staff_profiles DROP COLUMN IF EXISTS notify_zalo_consented_at")
    _sql("ALTER TABLE clinic.staff_profiles DROP COLUMN IF EXISTS notify_zalo_user_id")

    _sql("DROP TABLE IF EXISTS clinic.account_roster")

    _sql("DROP TRIGGER IF EXISTS account_purpose_guard ON agent.accounts")
    _sql("DROP FUNCTION IF EXISTS clinic.account_purpose_guard()")
    _sql("DROP TRIGGER IF EXISTS conversation_account_guard ON clinic.conversation")
    _sql("DROP FUNCTION IF EXISTS clinic.conversation_account_guard()")
    _sql("DROP INDEX IF EXISTS clinic.conversation_account_idx")
    _sql("ALTER TABLE clinic.conversation DROP CONSTRAINT IF EXISTS conversation_account_fk")
    _sql("ALTER TABLE clinic.conversation DROP COLUMN IF EXISTS account_id")

    _sql("ALTER TABLE agent.accounts DROP CONSTRAINT IF EXISTS accounts_send_limits_check")
    _sql("ALTER TABLE agent.accounts DROP COLUMN IF EXISTS daily_cap")
    _sql("ALTER TABLE agent.accounts DROP COLUMN IF EXISTS send_gap_max_s")
    _sql("ALTER TABLE agent.accounts DROP COLUMN IF EXISTS send_gap_min_s")
    _sql("ALTER TABLE agent.accounts DROP CONSTRAINT IF EXISTS accounts_purpose_check")
    _sql("ALTER TABLE agent.accounts DROP COLUMN IF EXISTS purpose")
