"""B1: dashboard sessions and the inbox door of the agent side.

Adds (nothing of 0001..0003 is edited):

* ``clinic.auth_session``: server-side record of a dashboard login. The JWT cookie carries only the session
  id; deleting the row revokes the cookie, and the stored password fingerprint kills every session of a user
  when the password changes (port of ``dashboard_sessions`` of zalo-agent). RLS by ``clinic_id``; ``be_app``
  only, ``agent_worker`` has no privilege on it.
* ``clinic_agent.review_item_summary``: the agent's own review item back, without the human's decision text
  (``final_text``, ``decision_note``) and without who decided.
* ``clinic_agent.record_inbound_message`` / ``record_outbound_message``: SECURITY DEFINER functions that write
  the Inbox of record (``clinic.conversation`` / ``clinic.message``) and audit it. The channel layer calls the
  inbound one in the API process and the outbound one from the worker, so both runtime roles may execute them.
* ``be_app`` gets USAGE on schema ``clinic_agent`` plus SELECT on its views and EXECUTE on its functions:
  the API process (webhooks, CRM rules) goes through the same door as the worker. This grants no table.

Revision ID: b1_0004_auth_session_and_inbox
Revises: 0003_clinic_agent_access
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1_0004_auth_session_and_inbox"
down_revision = "0003_clinic_agent_access"
branch_labels = None
depends_on = None

OLD_VIEWS = (
    "patient_ref",
    "patient_appointment",
    "patient_open_task",
    "patient_care_plan",
    "patient_last_session",
    "consent_current",
    "identity_verified",
    "channel_policy",
    "message_template_approved",
)
OLD_FUNCTIONS = (
    "clinic_agent.touch_identity(text, text, text)",
    "clinic_agent.resolve_identity(text, text)",
    "clinic_agent.create_review_item(text, text, text, text, uuid, text, jsonb, jsonb, text, text[], text, text)",
)
NEW_FUNCTIONS = (
    "clinic_agent.record_inbound_message(text, text, text, text, text, text, timestamptz, text)",
    "clinic_agent.record_outbound_message(uuid, text, text, boolean, uuid, text, text)",
)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    # ------------------------------------------------------------------ auth_session
    _sql("""
        CREATE TABLE clinic.auth_session (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            user_id uuid NOT NULL,
            password_fingerprint text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX auth_session_user_idx ON clinic.auth_session (clinic_id, user_id)")
    _sql("CREATE INDEX auth_session_expiry_idx ON clinic.auth_session (expires_at)")
    _sql("ALTER TABLE clinic.auth_session ENABLE ROW LEVEL SECURITY")
    _sql(
        "CREATE POLICY clinic_isolation ON clinic.auth_session "
        "USING (clinic_id = ctx.current_clinic_id()) WITH CHECK (clinic_id = ctx.current_clinic_id())"
    )
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.auth_session TO be_app")
    _sql("REVOKE ALL ON clinic.auth_session FROM agent_worker")

    # ------------------------------------------------------------------ review item summary for the agent
    _sql("""
        CREATE VIEW clinic_agent.review_item_summary WITH (security_barrier = true) AS
        SELECT r.id, r.clinic_id, r.kind, r.origin, r.status, r.conversation_id, r.patient_id,
               p.code AS patient_code, r.job_id, r.draft_text, r.payload, r.sources, r.risk_level,
               r.red_flags, r.requires_doctor, r.model, r.prompt_version, r.created_at, r.decided_at,
               r.version
          FROM clinic.review_item r
          LEFT JOIN clinic.patient p ON p.clinic_id = r.clinic_id AND p.id = r.patient_id
         WHERE r.clinic_id = ctx.current_clinic_id()""")

    # ------------------------------------------------------------------ inbox functions
    _sql("""
        CREATE FUNCTION clinic_agent.record_inbound_message(
            p_channel text, p_update_id text, p_thread_id text, p_external_user_id text,
            p_display_name text, p_text text, p_sent_at timestamptz, p_actor_type text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx AS $$
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_identity uuid;
            v_patient uuid;
            v_conv uuid;
            v_msg uuid;
            v_conv_patient uuid;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            IF p_update_id IS NULL OR p_update_id = '' THEN RAISE EXCEPTION 'update_id is the idempotency key'; END IF;

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
            VALUES (v_clinic, v_conv, p_channel, 'inbound', 'patient', p_text, 'received', p_update_id, p_sent_at)
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
        END $$""")
    _sql("""
        CREATE FUNCTION clinic_agent.record_outbound_message(
            p_conversation_id uuid, p_text text, p_status text, p_proactive boolean,
            p_review_item_id uuid, p_error_code text, p_actor_type text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx AS $$
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_channel text;
            v_msg uuid;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            SELECT c.channel INTO v_channel FROM clinic.conversation c
             WHERE c.clinic_id = v_clinic AND c.id = p_conversation_id;
            IF NOT FOUND THEN RAISE EXCEPTION 'conversation not found'; END IF;

            -- A message created when staff approved the review item is only updated (sent/failed), so
            -- the Inbox never holds the same reply twice.
            IF p_review_item_id IS NOT NULL THEN
                UPDATE clinic.message m
                   SET status = p_status,
                       error_code = p_error_code,
                       sent_at = CASE WHEN p_status = 'sent' THEN now() ELSE m.sent_at END
                 WHERE m.clinic_id = v_clinic AND m.review_item_id = p_review_item_id
                   AND m.conversation_id = p_conversation_id AND m.status = 'queued'
                RETURNING m.id INTO v_msg;
            END IF;

            IF v_msg IS NULL THEN
                INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body,
                                            status, proactive, review_item_id, error_code, sent_at)
                VALUES (v_clinic, p_conversation_id, v_channel, 'outbound',
                        CASE WHEN p_review_item_id IS NOT NULL THEN 'staff' ELSE 'system' END,
                        p_text, p_status, COALESCE(p_proactive, false), p_review_item_id, p_error_code,
                        CASE WHEN p_status = 'sent' THEN now() END)
                RETURNING id INTO v_msg;
                UPDATE clinic.conversation c
                   SET last_message_at = now(), version = c.version + 1
                 WHERE c.clinic_id = v_clinic AND c.id = p_conversation_id;
            END IF;

            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, p_actor_type, 'message.record_outbound', 'message', v_msg::text,
                    jsonb_build_object('conversation_id', p_conversation_id, 'status', p_status,
                                       'proactive', COALESCE(p_proactive, false)));
            RETURN QUERY SELECT p_conversation_id, v_msg;
        END $$""")

    # ------------------------------------------------------------------ grants
    for fn in NEW_FUNCTIONS:
        _sql(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        _sql(f"GRANT EXECUTE ON FUNCTION {fn} TO agent_worker, be_app")
    _sql("GRANT SELECT ON clinic_agent.review_item_summary TO agent_worker, be_app")
    _sql("GRANT USAGE ON SCHEMA clinic_agent TO be_app")
    for view in OLD_VIEWS:
        _sql(f"GRANT SELECT ON clinic_agent.{view} TO be_app")
    for fn in OLD_FUNCTIONS:
        _sql(f"GRANT EXECUTE ON FUNCTION {fn} TO be_app")


def downgrade() -> None:
    for fn in OLD_FUNCTIONS:
        _sql(f"REVOKE EXECUTE ON FUNCTION {fn} FROM be_app")
    for view in OLD_VIEWS:
        _sql(f"REVOKE SELECT ON clinic_agent.{view} FROM be_app")
    _sql("REVOKE USAGE ON SCHEMA clinic_agent FROM be_app")
    for fn in NEW_FUNCTIONS:
        _sql(f"DROP FUNCTION IF EXISTS {fn}")
    _sql("DROP VIEW IF EXISTS clinic_agent.review_item_summary")
    _sql("DROP TABLE IF EXISTS clinic.auth_session")
