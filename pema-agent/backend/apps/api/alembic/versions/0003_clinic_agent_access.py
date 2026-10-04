"""clinic_agent: the ONLY door from the agent worker into clinic data (PLAN-AI01 principle 4).

``agent_worker`` has no privilege on schema ``clinic``. It can:

* SELECT the minimised views of schema ``clinic_agent`` (no phone, no birth date, no address, no free
  clinical text, no photo, no credentials);
* EXECUTE the SECURITY DEFINER functions of this schema, each of which audits (``actor_type='agent'``).

Views run with the privileges of their owner (the migration role), which bypasses RLS on the base
tables; that is why every view filters by ``ctx.current_clinic_id()`` itself and is declared
``security_barrier`` (no leaky-predicate push-down). The functions do the same check at their top and
refuse to run without a clinic context.

``pema.clinic.actions.agent_facing`` (package B1) wraps these objects behind
``pema_contracts.clinic_actions.AgentFacingClinicActions``; nothing else in the agent side may touch them.

Revision ID: 0003_clinic_agent_access
Revises: 0002_agent_schema
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_clinic_agent_access"
down_revision = "0002_agent_schema"
branch_labels = None
depends_on = None

VIEWS = (
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
FUNCTIONS = (
    "clinic_agent.touch_identity(text, text, text)",
    "clinic_agent.resolve_identity(text, text)",
    "clinic_agent.create_review_item(text, text, text, text, uuid, text, jsonb, jsonb, text, text[], text, text)",
)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("CREATE SCHEMA clinic_agent")
    _sql("REVOKE ALL ON SCHEMA clinic_agent FROM PUBLIC")
    _sql("GRANT USAGE ON SCHEMA clinic_agent TO agent_worker")

    _sql("""
        CREATE VIEW clinic_agent.patient_ref WITH (security_barrier = true) AS
        SELECT p.id, p.clinic_id, p.code, p.full_name, p.gender, p.doctor_id, p.marketing_opt_out,
               p.expected_visit_source, p.reactivated_at, p.last_contact_at
          FROM clinic.patient p
         WHERE p.clinic_id = ctx.current_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.patient_appointment WITH (security_barrier = true) AS
        SELECT a.id, a.clinic_id, a.patient_id, a.doctor_id, a.starts_at, a.duration_min, a.status
          FROM clinic.appointment a
         WHERE a.clinic_id = ctx.current_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.patient_open_task WITH (security_barrier = true) AS
        SELECT t.id, t.clinic_id, t.patient_id, t.rule_key, t.priority, t.status, t.due_at
          FROM clinic.crm_task t
         WHERE t.clinic_id = ctx.current_clinic_id() AND t.status IN ('open', 'rescheduled')""")
    _sql("""
        CREATE VIEW clinic_agent.patient_care_plan WITH (security_barrier = true) AS
        SELECT pl.id, pl.clinic_id, pl.patient_id, pl.service_code, pl.total_sessions,
               pl.completed_sessions, pl.status
          FROM clinic.treatment_plan pl
         WHERE pl.clinic_id = ctx.current_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.patient_last_session WITH (security_barrier = true) AS
        SELECT DISTINCT ON (s.patient_id) s.clinic_id, s.patient_id, s.protocol_id, s.performed_at
          FROM clinic.treatment_session s
         WHERE s.clinic_id = ctx.current_clinic_id() AND s.status = 'completed'
         ORDER BY s.patient_id, s.performed_at DESC""")
    _sql("""
        CREATE VIEW clinic_agent.consent_current WITH (security_barrier = true) AS
        SELECT DISTINCT ON (c.patient_id, c.kind) c.clinic_id, c.patient_id, c.kind, c.granted
          FROM clinic.consent c
         WHERE c.clinic_id = ctx.current_clinic_id()
         ORDER BY c.patient_id, c.kind, c.created_at DESC""")
    _sql("""
        CREATE VIEW clinic_agent.identity_verified WITH (security_barrier = true) AS
        SELECT i.clinic_id, i.channel, i.external_user_id, i.patient_id, i.verified_at
          FROM clinic.channel_identity i
         WHERE i.clinic_id = ctx.current_clinic_id() AND i.verification_status = 'verified'""")
    _sql("""
        CREATE VIEW clinic_agent.channel_policy WITH (security_barrier = true) AS
        SELECT s.clinic_id, s.channel, s.enabled, s.kill_switch_on, s.daily_cap, s.send_window_start,
               s.send_window_end, s.min_gap_seconds, s.max_gap_seconds, s.requires_friend
          FROM clinic.channel_setting s
         WHERE s.clinic_id = ctx.current_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.message_template_approved WITH (security_barrier = true) AS
        SELECT m.clinic_id, m.template_key, m.title, m.body, m.marketing
          FROM clinic.message_template m
         WHERE m.clinic_id = ctx.current_clinic_id() AND m.active AND m.approved_at IS NOT NULL""")

    # ------------------------------------------------------------------ functions
    _sql("""
        CREATE FUNCTION clinic_agent.touch_identity(p_channel text, p_external_user_id text, p_display_name text)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx AS $$
        DECLARE v_clinic uuid := ctx.current_clinic_id();
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, display_name, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, NULLIF(p_display_name, ''), now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE
               SET last_inbound_at = now(),
                   display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), clinic.channel_identity.display_name);
        END $$""")
    _sql("""
        CREATE FUNCTION clinic_agent.resolve_identity(p_channel text, p_external_user_id text)
        RETURNS TABLE (status text, patient_id uuid, patient_code text, verified_at timestamptz)
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx AS $$
        DECLARE v_clinic uuid := ctx.current_clinic_id();
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            RETURN QUERY
            SELECT i.verification_status, i.patient_id, p.code, i.verified_at
              FROM clinic.channel_identity i
              LEFT JOIN clinic.patient p ON p.clinic_id = i.clinic_id AND p.id = i.patient_id
             WHERE i.clinic_id = v_clinic AND i.channel = p_channel AND i.external_user_id = p_external_user_id;
            IF NOT FOUND THEN
                RETURN QUERY SELECT 'unlinked'::text, NULL::uuid, NULL::text, NULL::timestamptz;
            END IF;
        END $$""")
    _sql("""
        CREATE FUNCTION clinic_agent.create_review_item(
            p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid,
            p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[],
            p_model text, p_prompt_version text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx AS $$
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_patient uuid;
            v_id uuid;
            v_doctor boolean := (p_risk_level = 'red_flag' OR p_kind = 'triage_alert');
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_job_id IS NULL OR p_job_id = '' THEN RAISE EXCEPTION 'job_id is the idempotency key'; END IF;
            SELECT id INTO v_id FROM clinic.review_item WHERE clinic_id = v_clinic AND job_id = p_job_id;
            IF FOUND THEN RETURN v_id; END IF;
            IF p_patient_code IS NOT NULL THEN
                SELECT id INTO v_patient FROM clinic.patient WHERE clinic_id = v_clinic AND code = p_patient_code;
            END IF;
            INSERT INTO clinic.review_item (clinic_id, kind, origin, conversation_id, patient_id, job_id, draft_text,
                    payload, sources, risk_level, red_flags, requires_doctor, model, prompt_version)
            VALUES (v_clinic, p_kind, p_origin, p_conversation_id, v_patient, p_job_id, p_draft_text,
                    p_payload, COALESCE(p_sources, '[]'::jsonb), p_risk_level, COALESCE(p_red_flags, '{}'), v_doctor,
                    p_model, p_prompt_version)
            RETURNING id INTO v_id;
            IF p_conversation_id IS NOT NULL THEN
                UPDATE clinic.conversation
                   SET status = CASE WHEN v_doctor THEN 'handoff' ELSE 'pending_review' END
                 WHERE clinic_id = v_clinic AND id = p_conversation_id AND status <> 'closed';
            END IF;
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'review_item.create', 'review_item', v_id::text,
                    jsonb_build_object('kind', p_kind, 'origin', p_origin, 'risk_level', p_risk_level,
                                       'has_draft', p_draft_text IS NOT NULL));
            RETURN v_id;
        END $$""")

    for fn in FUNCTIONS:
        _sql(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        _sql(f"GRANT EXECUTE ON FUNCTION {fn} TO agent_worker")
    for view in VIEWS:
        _sql(f"GRANT SELECT ON clinic_agent.{view} TO agent_worker")


def downgrade() -> None:
    _sql("DROP SCHEMA IF EXISTS clinic_agent CASCADE")
