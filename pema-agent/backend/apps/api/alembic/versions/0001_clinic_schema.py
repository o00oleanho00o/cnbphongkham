"""clinic schema: tenant, users, patients, care, appointments, CRM, inbox, review, consent, audit.

Security model (PLAN-AI01 principles 3 and 4):

* role ``be_app``: used by the API at runtime; DML on ``clinic.*`` (audit_log is insert/select only);
  never owns tables, so row level security applies to it.
* role ``agent_worker``: NO privilege on schema ``clinic`` at all. It reads clinic data only through the
  views and SECURITY DEFINER functions of schema ``clinic_agent`` (revision 0003).
* every table carries ``clinic_id`` and an RLS policy comparing it with ``ctx.current_clinic_id()``,
  which reads the transaction-local setting ``app.clinic_id`` (set with
  ``SELECT set_config('app.clinic_id', '<uuid>', true)``). Unset means no rows (fail closed).
  ``ctx`` is a neutral schema both runtime roles may use, so the same function serves ``clinic.*`` and
  ``agent.*`` policies.
* parent/child links are composite ``(clinic_id, id)`` foreign keys, so a row can never point at
  another clinic's row.
* two SECURITY DEFINER lookups exist for the moments before a clinic is known: ``ctx.resolve_clinic``
  (login, webhooks) and ``ctx.list_active_clinic_ids`` (scheduler loop).

Revision ID: 0001_clinic_schema
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0001_clinic_schema"
down_revision = None
branch_labels = None
depends_on = None

ROLES = ("owner", "manager", "doctor", "cs_staff", "reception", "patient")
RULE_KEYS = (
    "d1",
    "d3",
    "d7",
    "due",
    "overdue",
    "no_show",
    "abandoned",
    "dormant90",
    "dormant180",
    "birthday",
)
OUTCOMES = (
    "unanswered",
    "callback",
    "no_need",
    "busy",
    "booked",
    "doctor",
    "reaction",
    "complaint",
    "optout",
    "invalid",
)
CHANNELS = ("zalo_bot", "zalo_personal", "zalo_oa")
REVIEW_KINDS = ("reply_draft", "followup_draft", "triage_alert", "media_flag", "identity_check")
REVIEW_ORIGINS = ("agent_turn", "scheduled_agent", "crm_rule", "policy")

# Tables that carry clinic_id and get RLS + DML grants. audit_log is handled specially.
CLINIC_TABLES = (
    "user_account",
    "patient",
    "episode",
    "treatment_plan",
    "treatment_session",
    "appointment",
    "crm_rule",
    "crm_task",
    "crm_activity",
    "channel_setting",
    "channel_identity",
    "conversation",
    "message",
    "review_item",
    "consent",
    "message_template",
    "audit_log",
)
UPDATED_AT_TABLES = (
    "clinic",
    "user_account",
    "patient",
    "episode",
    "treatment_plan",
    "appointment",
    "crm_rule",
    "crm_task",
    "channel_setting",
    "conversation",
    "review_item",
    "message_template",
)


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _ensure_roles() -> None:
    for role in ("be_app", "agent_worker"):
        _sql(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '" + role + "') "
            "THEN CREATE ROLE " + role + " NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; "
            "END IF; END $$"
        )
    # Optional: give the roles a password from the environment so they can log in (docker/dev).
    # Without it they stay NOLOGIN and infra must run ALTER ROLE ... LOGIN PASSWORD itself.
    for role, env_name in (
        ("be_app", "PEMA_BE_APP_PASSWORD"),
        ("agent_worker", "PEMA_AGENT_WORKER_PASSWORD"),
    ):
        secret = os.environ.get(env_name)
        if not secret:
            continue
        op.execute(sa.text("SELECT set_config('pema.role_secret', :s, true)").bindparams(s=secret))
        _sql(
            "DO $$ BEGIN EXECUTE format('ALTER ROLE " + role + " LOGIN PASSWORD %L', "
            "current_setting('pema.role_secret')); END $$"
        )
        _sql("SELECT set_config('pema.role_secret', '', true)")


def upgrade() -> None:
    _ensure_roles()
    _sql("CREATE SCHEMA ctx")
    _sql("REVOKE ALL ON SCHEMA ctx FROM PUBLIC")
    _sql("GRANT USAGE ON SCHEMA ctx TO be_app, agent_worker")
    _sql("CREATE SCHEMA clinic")
    _sql("REVOKE ALL ON SCHEMA clinic FROM PUBLIC")

    _sql(
        "CREATE FUNCTION ctx.current_clinic_id() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.clinic_id', true), '')::uuid $$"
    )
    _sql("REVOKE ALL ON FUNCTION ctx.current_clinic_id() FROM PUBLIC")
    _sql("GRANT EXECUTE ON FUNCTION ctx.current_clinic_id() TO be_app, agent_worker")
    _sql(
        "CREATE FUNCTION clinic.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$"
    )

    # ---------------------------------------------------------------- tenant and users
    _sql("""
        CREATE TABLE clinic.clinic (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
            name text NOT NULL,
            timezone text NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )""")
    _sql(f"""
        CREATE TABLE clinic.user_account (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            email text NOT NULL CHECK (email = lower(email)),
            display_name text NOT NULL,
            role text NOT NULL CHECK (role IN ({_q(ROLES)})),
            password_hash text,
            active boolean NOT NULL DEFAULT true,
            last_login_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, email)
        )""")

    # ---------------------------------------------------------------- patient and care
    _sql("""
        CREATE TABLE clinic.patient (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            code text NOT NULL,
            full_name text NOT NULL,
            phone text,
            birth_date date,
            gender text NOT NULL DEFAULT 'unknown' CHECK (gender IN ('female', 'male', 'other', 'unknown')),
            doctor_id uuid,
            cs_owner_id uuid,
            marketing_opt_out boolean NOT NULL DEFAULT false,
            first_contact_at date,
            source text,
            recommendation_at date,
            expected_visit_source text CHECK (expected_visit_source IN
                ('doctor_recommendation', 'service_protocol', 'treatment_plan', 'appointment',
                 'followup_automation')),
            expected_visit_reason text,
            reactivated_at timestamptz,
            last_contact_at timestamptz,
            latest_outcome text,
            next_action_at timestamptz,
            next_action_type text,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, code),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, cs_owner_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX patient_name_idx ON clinic.patient (clinic_id, lower(full_name) text_pattern_ops)")
    _sql("CREATE INDEX patient_phone_idx ON clinic.patient (clinic_id, phone)")

    _sql("""
        CREATE TABLE clinic.episode (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            title text NOT NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
            started_on date NOT NULL,
            closed_on date,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id)
        )""")
    _sql("""
        CREATE TABLE clinic.treatment_plan (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            episode_id uuid,
            doctor_id uuid,
            service_code text NOT NULL,
            title text NOT NULL,
            total_sessions integer NOT NULL DEFAULT 1 CHECK (total_sessions >= 0),
            completed_sessions integer NOT NULL DEFAULT 0 CHECK (completed_sessions >= 0),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('planned', 'active', 'completed', 'abandoned', 'cancelled')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, episode_id) REFERENCES clinic.episode (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("""
        CREATE TABLE clinic.treatment_session (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            plan_id uuid,
            doctor_id uuid,
            performed_at timestamptz NOT NULL,
            protocol_id text,
            title text NOT NULL,
            note text,
            status text NOT NULL DEFAULT 'completed'
                CHECK (status IN ('scheduled', 'completed', 'cancelled')),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, plan_id) REFERENCES clinic.treatment_plan (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX treatment_session_patient_idx ON clinic.treatment_session "
        "(clinic_id, patient_id, performed_at DESC)"
    )

    # ---------------------------------------------------------------- appointments
    _sql("""
        CREATE TABLE clinic.appointment (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            doctor_id uuid,
            starts_at timestamptz NOT NULL,
            duration_min integer NOT NULL DEFAULT 30 CHECK (duration_min > 0),
            status text NOT NULL DEFAULT 'booked' CHECK (status IN
                ('booked', 'confirmed', 'arrived', 'in_progress', 'completed', 'cancelled', 'missed')),
            note text,
            cancel_reason text,
            cancelled_at timestamptz,
            missed_at timestamptz,
            created_by uuid,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX appointment_time_idx ON clinic.appointment (clinic_id, starts_at)")
    _sql("CREATE INDEX appointment_patient_idx ON clinic.appointment (clinic_id, patient_id, starts_at DESC)")
    _sql("CREATE INDEX appointment_doctor_idx ON clinic.appointment (clinic_id, doctor_id, starts_at)")

    # ---------------------------------------------------------------- CRM
    _sql(f"""
        CREATE TABLE clinic.crm_rule (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            rule_key text NOT NULL CHECK (rule_key IN ({_q(RULE_KEYS)})),
            name text NOT NULL,
            trigger text NOT NULL,
            delay_days integer NOT NULL DEFAULT 0 CHECK (delay_days >= 0),
            suggested_action text NOT NULL,
            priority text NOT NULL DEFAULT 'normal' CHECK (priority IN ('high', 'normal', 'low')),
            active boolean NOT NULL DEFAULT true,
            send_mode text NOT NULL DEFAULT 'staff_task'
                CHECK (send_mode IN ('staff_task', 'auto_reminder', 'draft_for_review')),
            conditions jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, rule_key),
            CHECK (rule_key <> 'birthday' OR send_mode = 'staff_task')
        )""")
    _sql(f"""
        CREATE TABLE clinic.crm_task (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            task_key text NOT NULL,
            patient_id uuid NOT NULL,
            rule_key text NOT NULL CHECK (rule_key IN ({_q(RULE_KEYS)}, 'manual')),
            reason text NOT NULL,
            priority text NOT NULL DEFAULT 'normal' CHECK (priority IN ('high', 'normal', 'low')),
            status text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'rescheduled', 'resolved', 'superseded')),
            owner_user_id uuid,
            due_at timestamptz NOT NULL,
            suggested_action text NOT NULL,
            source_event_id text,
            related_appointment_id uuid,
            related_plan_id uuid,
            resolution text,
            resolved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, task_key),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, owner_user_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment (clinic_id, id),
            FOREIGN KEY (clinic_id, related_plan_id) REFERENCES clinic.treatment_plan (clinic_id, id)
        )""")
    _sql("CREATE INDEX crm_task_queue_idx ON clinic.crm_task (clinic_id, status, due_at)")
    _sql("CREATE INDEX crm_task_patient_idx ON clinic.crm_task (clinic_id, patient_id)")
    _sql(f"""
        CREATE TABLE clinic.crm_activity (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            task_id uuid,
            kind text NOT NULL DEFAULT 'cskh' CHECK (kind IN ('cskh', 'complaint', 'note')),
            channel text NOT NULL CHECK (channel IN ('call', 'zalo', 'sms', 'internal_note')),
            outcome text CHECK (outcome IN ({_q(OUTCOMES)})),
            note text NOT NULL,
            actor_user_id uuid,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            next_action_at timestamptz,
            next_action_type text,
            related_appointment_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, task_id) REFERENCES clinic.crm_task (clinic_id, id),
            FOREIGN KEY (clinic_id, actor_user_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX crm_activity_patient_idx ON clinic.crm_activity (clinic_id, patient_id, occurred_at DESC)"
    )

    # ---------------------------------------------------------------- channels and inbox
    _sql(f"""
        CREATE TABLE clinic.channel_setting (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            channel text NOT NULL CHECK (channel IN ({_q(CHANNELS)})),
            enabled boolean NOT NULL DEFAULT false,
            kill_switch_on boolean NOT NULL DEFAULT false,
            kill_switch_reason text,
            kill_switch_changed_at timestamptz,
            kill_switch_changed_by uuid,
            daily_cap integer CHECK (daily_cap >= 0),
            send_window_start time,
            send_window_end time,
            min_gap_seconds integer NOT NULL DEFAULT 0 CHECK (min_gap_seconds >= 0),
            max_gap_seconds integer NOT NULL DEFAULT 0 CHECK (max_gap_seconds >= min_gap_seconds),
            requires_friend boolean NOT NULL DEFAULT false,
            bridge_state text CHECK (bridge_state IN
                ('not_configured', 'awaiting_qr', 'connected', 'blocked', 'down')),
            config jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            updated_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, channel),
            FOREIGN KEY (clinic_id, kill_switch_changed_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, updated_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(f"""
        CREATE TABLE clinic.channel_identity (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            channel text NOT NULL CHECK (channel IN ({_q(CHANNELS)})),
            external_user_id text NOT NULL,
            patient_id uuid,
            display_name text,
            friend_status text NOT NULL DEFAULT 'unknown'
                CHECK (friend_status IN ('unknown', 'friend', 'not_friend')),
            verification_status text NOT NULL DEFAULT 'unlinked'
                CHECK (verification_status IN ('unlinked', 'pending', 'verified', 'rejected')),
            verified_at timestamptz,
            verified_by uuid,
            last_inbound_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, channel, external_user_id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, verified_by) REFERENCES clinic.user_account (clinic_id, id),
            CHECK (verification_status <> 'verified' OR (patient_id IS NOT NULL AND verified_at IS NOT NULL))
        )""")
    _sql(f"""
        CREATE TABLE clinic.conversation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            channel text NOT NULL CHECK (channel IN ({_q(CHANNELS)})),
            external_ref text NOT NULL,
            patient_id uuid,
            identity_id uuid,
            status text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'pending_review', 'handoff', 'closed')),
            assigned_user_id uuid,
            last_message_at timestamptz,
            last_inbound_at timestamptz,
            unread_count integer NOT NULL DEFAULT 0 CHECK (unread_count >= 0),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, channel, external_ref),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, identity_id) REFERENCES clinic.channel_identity (clinic_id, id),
            FOREIGN KEY (clinic_id, assigned_user_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX conversation_inbox_idx ON clinic.conversation (clinic_id, status, last_message_at DESC)"
    )

    # review_item before message so message.review_item_id can reference it
    _sql(f"""
        CREATE TABLE clinic.review_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            kind text NOT NULL CHECK (kind IN ({_q(REVIEW_KINDS)})),
            origin text NOT NULL DEFAULT 'agent_turn' CHECK (origin IN ({_q(REVIEW_ORIGINS)})),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'escalated', 'expired')),
            conversation_id uuid,
            patient_id uuid,
            job_id text,
            draft_text text,
            final_text text,
            payload jsonb,
            sources jsonb NOT NULL DEFAULT '[]'::jsonb,
            risk_level text NOT NULL DEFAULT 'normal' CHECK (risk_level IN ('normal', 'attention', 'red_flag')),
            red_flags text[] NOT NULL DEFAULT '{{}}',
            requires_doctor boolean NOT NULL DEFAULT false,
            model text,
            prompt_version text,
            expires_at timestamptz,
            decided_by uuid,
            decided_at timestamptz,
            decision_note text,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, decided_by) REFERENCES clinic.user_account (clinic_id, id),
            CHECK (risk_level <> 'red_flag' OR requires_doctor),
            CHECK (kind <> 'triage_alert' OR requires_doctor)
        )""")
    _sql(
        "CREATE UNIQUE INDEX review_item_job_idx ON clinic.review_item (clinic_id, job_id) "
        "WHERE job_id IS NOT NULL"
    )
    _sql("CREATE INDEX review_item_queue_idx ON clinic.review_item (clinic_id, status, created_at)")

    _sql(f"""
        CREATE TABLE clinic.message (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            conversation_id uuid NOT NULL,
            channel text NOT NULL CHECK (channel IN ({_q(CHANNELS)})),
            direction text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
            sender_type text NOT NULL CHECK (sender_type IN ('patient', 'staff', 'ai_draft', 'system')),
            sender_user_id uuid,
            body text,
            masked_body text,
            status text NOT NULL DEFAULT 'received' CHECK (status IN
                ('received', 'draft', 'queued', 'sent', 'failed', 'rejected')),
            proactive boolean NOT NULL DEFAULT false,
            update_id text,
            external_message_id text,
            review_item_id uuid,
            error_code text,
            created_at timestamptz NOT NULL DEFAULT now(),
            sent_at timestamptz,
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation (clinic_id, id),
            FOREIGN KEY (clinic_id, sender_user_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, review_item_id) REFERENCES clinic.review_item (clinic_id, id),
            CHECK (NOT proactive OR direction = 'outbound')
        )""")
    _sql(
        "CREATE UNIQUE INDEX message_update_dedupe_idx ON clinic.message (clinic_id, channel, update_id) "
        "WHERE update_id IS NOT NULL"
    )
    _sql(
        "CREATE INDEX message_conversation_idx ON clinic.message (clinic_id, conversation_id, created_at DESC)"
    )
    _sql(
        "CREATE INDEX message_proactive_cap_idx ON clinic.message (clinic_id, channel, created_at) "
        "WHERE proactive AND direction = 'outbound'"
    )

    # ---------------------------------------------------------------- approved message templates
    # A scheduled ``kind: message`` job of the patient_channel profile may only send a template that a
    # doctor approved (PLAN-AI01 sections 5 and 8). ``marketing`` templates obey ``marketing_opt_out``.
    _sql("""
        CREATE TABLE clinic.message_template (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            template_key text NOT NULL CHECK (template_key ~ '^[a-z0-9][a-z0-9_.-]*$'),
            title text NOT NULL,
            body text NOT NULL,
            marketing boolean NOT NULL DEFAULT false,
            active boolean NOT NULL DEFAULT true,
            approved_by uuid,
            approved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, template_key),
            FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account (clinic_id, id),
            CHECK (NOT active OR approved_at IS NOT NULL)
        )""")

    # ---------------------------------------------------------------- consent and audit
    _sql("""
        CREATE TABLE clinic.consent (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('messaging', 'marketing', 'media', 'data_processing')),
            granted boolean NOT NULL,
            granted_at timestamptz,
            revoked_at timestamptz,
            source text,
            recorded_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, recorded_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX consent_patient_idx ON clinic.consent (clinic_id, patient_id, kind, created_at DESC)")
    _sql("""
        CREATE TABLE clinic.audit_log (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            occurred_at timestamptz NOT NULL DEFAULT now(),
            actor_type text NOT NULL CHECK (actor_type IN ('user', 'agent', 'scheduler', 'system')),
            actor_user_id uuid,
            actor_role text CHECK (actor_role IN ('owner', 'manager', 'doctor', 'cs_staff', 'reception', 'patient')),
            action text NOT NULL,
            entity_type text NOT NULL,
            entity_id text,
            request_id text,
            details jsonb
        )""")
    _sql("CREATE INDEX audit_log_time_idx ON clinic.audit_log (clinic_id, occurred_at DESC)")
    _sql("CREATE INDEX audit_log_entity_idx ON clinic.audit_log (clinic_id, entity_type, entity_id)")
    _sql(
        "CREATE FUNCTION clinic.audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'clinic.audit_log is append-only'; END $$"
    )
    _sql(
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON clinic.audit_log "
        "FOR EACH ROW EXECUTE FUNCTION clinic.audit_log_immutable()"
    )
    _sql(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON clinic.audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION clinic.audit_log_immutable()"
    )

    # ---------------------------------------------------------------- updated_at triggers
    for table in UPDATED_AT_TABLES:
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )

    # ---------------------------------------------------------------- row level security
    # ENABLE (not FORCE): the owner/migration role bypasses RLS, be_app (not an owner) does not.
    _sql("ALTER TABLE clinic.clinic ENABLE ROW LEVEL SECURITY")
    _sql(
        "CREATE POLICY clinic_isolation ON clinic.clinic "
        "USING (id = ctx.current_clinic_id()) WITH CHECK (id = ctx.current_clinic_id())"
    )
    for table in CLINIC_TABLES:
        _sql(f"ALTER TABLE clinic.{table} ENABLE ROW LEVEL SECURITY")
        _sql(
            f"CREATE POLICY clinic_isolation ON clinic.{table} "
            "USING (clinic_id = ctx.current_clinic_id()) "
            "WITH CHECK (clinic_id = ctx.current_clinic_id())"
        )

    # ---------------------------------------------------------------- lookups before a clinic is known
    # In schema ctx (not clinic) so BOTH runtime roles can call them without any privilege on clinic.
    _sql(
        "CREATE FUNCTION ctx.resolve_clinic(p_slug text) RETURNS uuid LANGUAGE sql STABLE "
        "SECURITY DEFINER SET search_path = pg_catalog, clinic AS "
        "$$ SELECT id FROM clinic.clinic WHERE slug = p_slug AND active $$"
    )
    _sql(
        "CREATE FUNCTION ctx.list_active_clinic_ids() RETURNS SETOF uuid LANGUAGE sql STABLE "
        "SECURITY DEFINER SET search_path = pg_catalog, clinic AS "
        "$$ SELECT id FROM clinic.clinic WHERE active ORDER BY created_at $$"
    )
    _sql("REVOKE ALL ON FUNCTION ctx.resolve_clinic(text) FROM PUBLIC")
    _sql("REVOKE ALL ON FUNCTION ctx.list_active_clinic_ids() FROM PUBLIC")
    _sql("GRANT EXECUTE ON FUNCTION ctx.resolve_clinic(text) TO be_app, agent_worker")
    _sql("GRANT EXECUTE ON FUNCTION ctx.list_active_clinic_ids() TO be_app, agent_worker")

    # ---------------------------------------------------------------- grants (agent_worker gets none)
    _sql("GRANT USAGE ON SCHEMA clinic TO be_app")
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.clinic TO be_app")
    for table in CLINIC_TABLES:
        if table == "audit_log":
            _sql("GRANT SELECT, INSERT ON clinic.audit_log TO be_app")
        else:
            _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")
    _sql("GRANT USAGE ON ALL SEQUENCES IN SCHEMA clinic TO be_app")
    # Later migrations get DML for be_app automatically; they must REVOKE where that is too wide.
    _sql("ALTER DEFAULT PRIVILEGES IN SCHEMA clinic GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO be_app")
    _sql("ALTER DEFAULT PRIVILEGES IN SCHEMA clinic GRANT USAGE ON SEQUENCES TO be_app")
    _sql("REVOKE ALL ON SCHEMA clinic FROM agent_worker")


def downgrade() -> None:
    # Roles are cluster-wide and may hold privileges in other databases; they are left in place.
    _sql("DROP SCHEMA IF EXISTS clinic CASCADE")
    _sql("DROP SCHEMA IF EXISTS ctx CASCADE")
