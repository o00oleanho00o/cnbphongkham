"""Channel accounts live in the agent service now (plugin zalo); the clinic keeps their id as plain text
(docs/PLAN-db-baseline.md, C2 and C3): no foreign key to ``agent.accounts``, no purpose guards, and the inbox
function stores the id it is given.

Revision ID: g2_0012_account_text
Revises: g1_0011_guide_article
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g2_0012_account_text"
down_revision = "g1_0011_guide_article"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _function_9() -> str:
    return """
        CREATE OR REPLACE FUNCTION clinic_agent.record_inbound_message(
            p_channel text, p_update_id text, p_thread_id text, p_external_user_id text,
            p_display_name text, p_text text, p_sent_at timestamptz, p_actor_type text, p_account_id text)
        RETURNS TABLE (o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx, pg_temp AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity uuid;
            v_patient uuid;
            v_conv uuid;
            v_msg uuid;
            v_conv_patient uuid;
            v_account text;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            IF p_update_id IS NULL OR p_update_id = '' THEN
                RAISE EXCEPTION 'update_id is the idempotency key';
            END IF;

            -- the account that received the message, as the channel names it (the agent keeps the accounts)
            v_account := NULLIF(p_account_id, '');

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


def upgrade() -> None:
    _sql("ALTER TABLE clinic.conversation DROP CONSTRAINT conversation_account_fk")
    _sql("ALTER TABLE clinic.account_roster DROP CONSTRAINT account_roster_clinic_id_account_id_fkey")
    _sql("DROP TRIGGER conversation_account_guard ON clinic.conversation")
    _sql("DROP FUNCTION clinic.conversation_account_guard()")
    _sql("DROP TRIGGER account_purpose_guard ON agent.accounts")
    _sql("DROP FUNCTION clinic.account_purpose_guard()")
    _sql(_function_9())


def downgrade() -> None:
    raise NotImplementedError("the baseline of docs/PLAN-db-baseline.md replaces this chain; no way back")
