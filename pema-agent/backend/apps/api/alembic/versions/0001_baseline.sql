CREATE SCHEMA clinic;

CREATE SCHEMA ctx;

CREATE FUNCTION clinic.audit_log_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'clinic.audit_log is append-only'; END $$;

CREATE FUNCTION clinic.clinic_undeletable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'the clinic row is the installation id and cannot be deleted'; END $$;

CREATE FUNCTION clinic.ensure_clinic(p_name text, p_slug text DEFAULT 'clinic'::text, p_timezone text DEFAULT 'Asia/Ho_Chi_Minh'::text, p_id uuid DEFAULT NULL::uuid) RETURNS uuid
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'clinic', 'pg_temp'
    AS $$
        DECLARE
            v_id uuid;
        BEGIN
            INSERT INTO clinic.clinic (id, slug, name, timezone)
            VALUES (COALESCE(p_id, gen_random_uuid()), p_slug, p_name, p_timezone)
            ON CONFLICT (singleton) DO NOTHING;
            SELECT id INTO STRICT v_id FROM clinic.clinic;
            IF p_id IS NOT NULL AND v_id <> p_id THEN
                RAISE EXCEPTION 'the installed clinic has another id than the one asked for';
            END IF;
            RETURN v_id;
        END $$;

CREATE FUNCTION clinic.finance_closed_period_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE
            target_clinic uuid;
            target_day date;
            old_day date;
        BEGIN
            IF TG_TABLE_NAME = 'procedure_entry' THEN
                IF TG_OP <> 'INSERT' THEN old_day := OLD.entry_date; END IF;
                IF TG_OP <> 'DELETE' THEN target_day := NEW.entry_date; END IF;
                target_clinic := COALESCE(NEW.clinic_id, OLD.clinic_id);
            ELSE
                SELECT e.entry_date INTO target_day FROM clinic.procedure_entry e
                 WHERE e.clinic_id = COALESCE(NEW.clinic_id, OLD.clinic_id)
                   AND e.id = COALESCE(NEW.entry_id, OLD.entry_id);
                old_day := target_day;
                target_clinic := COALESCE(NEW.clinic_id, OLD.clinic_id);
            END IF;
            IF EXISTS (
                SELECT 1 FROM clinic.finance_period p
                 WHERE p.clinic_id = target_clinic
                   AND p.month IN (to_char(target_day, 'YYYY-MM'), to_char(old_day, 'YYYY-MM'))
            ) THEN
                RAISE EXCEPTION 'the finance period is closed';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;

CREATE FUNCTION clinic.finance_period_frozen() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'a finance period is never deleted';
            END IF;
            IF NEW.month IS DISTINCT FROM OLD.month OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
               OR NEW.closed_at IS DISTINCT FROM OLD.closed_at OR NEW.closed_by IS DISTINCT FROM OLD.closed_by
               OR (OLD.status = 'paid' AND NEW IS DISTINCT FROM OLD)
               OR (OLD.status = 'closed' AND NEW.status NOT IN ('closed', 'paid')) THEN
                RAISE EXCEPTION 'a closed finance period is immutable';
            END IF;
            RETURN NEW;
        END
        $$;

CREATE FUNCTION clinic.order_approved_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF TG_TABLE_NAME = 'order' THEN
                IF OLD.status = 'approved' AND (
                    NEW.status IS DISTINCT FROM OLD.status OR NEW.patient_id IS DISTINCT FROM OLD.patient_id
                    OR NEW.doctor_id IS DISTINCT FROM OLD.doctor_id OR NEW.diagnosis IS DISTINCT FROM OLD.diagnosis
                    OR NEW.note IS DISTINCT FROM OLD.note OR NEW.total_vnd IS DISTINCT FROM OLD.total_vnd
                    OR NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
                    OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at
                    OR NEW.order_date IS DISTINCT FROM OLD.order_date
                ) THEN
                    RAISE EXCEPTION 'an approved order is immutable';
                END IF;
                RETURN NEW;
            END IF;
            IF EXISTS (
                SELECT 1 FROM clinic."order" o
                 WHERE o.clinic_id = COALESCE(NEW.clinic_id, OLD.clinic_id)
                   AND o.id = COALESCE(NEW.order_id, OLD.order_id) AND o.status = 'approved'
            ) THEN
                RAISE EXCEPTION 'the lines of an approved order are immutable';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;

CREATE FUNCTION clinic.record_retention_run(p_scope text, p_counts jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $_$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_id bigint;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_scope <> 'clinic' THEN RAISE EXCEPTION 'bad retention scope'; END IF;
            IF p_counts IS NULL OR jsonb_typeof(p_counts) <> 'object' THEN
                RAISE EXCEPTION 'counts must be a JSON object';
            END IF;
            IF (SELECT count(*) FROM jsonb_object_keys(p_counts)) > 40 THEN
                RAISE EXCEPTION 'too many counters';
            END IF;
            -- Counters only: short snake_case keys, non-negative integers. No free text can get in.
            IF EXISTS (SELECT 1 FROM jsonb_each(p_counts) e
                        WHERE e.key !~ '^[a-z][a-z_]{0,39}$'
                           OR jsonb_typeof(e.value) <> 'number'
                           OR e.value::text !~ '^[0-9]{1,12}$') THEN
                RAISE EXCEPTION 'counts must map snake_case names to non-negative integers';
            END IF;
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'system', 'retention.run', 'retention', p_scope,
                    jsonb_build_object('scope', p_scope, 'deleted', p_counts))
            RETURNING id INTO v_id;
            RETURN v_id;
        END $_$;

CREATE FUNCTION clinic.service_version_append_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'clinic.service_version is append-only';
        END
        $$;

CREATE FUNCTION clinic.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

CREATE FUNCTION ctx.the_clinic_id() RETURNS uuid
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'pg_temp'
    AS $$
        DECLARE
            v_id uuid;
        BEGIN
            SELECT id INTO v_id FROM clinic.clinic;
            IF v_id IS NULL THEN
                RAISE EXCEPTION 'no clinic installed: run clinic.ensure_clinic first';
            END IF;
            RETURN v_id;
        END $$;

CREATE TABLE clinic.appointment (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    doctor_id uuid,
    starts_at timestamp with time zone NOT NULL,
    duration_min integer DEFAULT 30 NOT NULL,
    status text DEFAULT 'booked'::text NOT NULL,
    note text,
    cancel_reason text,
    cancelled_at timestamp with time zone,
    missed_at timestamp with time zone,
    created_by uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    room_id uuid,
    CONSTRAINT appointment_duration_min_check CHECK ((duration_min > 0)),
    CONSTRAINT appointment_status_check CHECK ((status = ANY (ARRAY['booked'::text, 'confirmed'::text, 'arrived'::text, 'in_progress'::text, 'completed'::text, 'cancelled'::text, 'missed'::text])))
);

CREATE TABLE clinic.audit_log (
    id bigint NOT NULL,
    clinic_id uuid NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    actor_type text NOT NULL,
    actor_user_id uuid,
    actor_role text,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    request_id text,
    details jsonb,
    CONSTRAINT audit_log_actor_role_check CHECK ((actor_role = ANY (ARRAY['owner'::text, 'manager'::text, 'doctor'::text, 'cs_staff'::text, 'reception'::text, 'accountant'::text, 'patient'::text]))),
    CONSTRAINT audit_log_actor_type_check CHECK ((actor_type = ANY (ARRAY['user'::text, 'agent'::text, 'scheduler'::text, 'system'::text])))
);

ALTER TABLE clinic.audit_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME clinic.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE clinic.auth_session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    password_fingerprint text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL
);

CREATE TABLE clinic.catalog_import (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    source_name text NOT NULL,
    sha256 text NOT NULL,
    source_sha256 text,
    total_rows integer NOT NULL,
    prescription_rows integer NOT NULL,
    imported_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT catalog_import_prescription_rows_check CHECK ((prescription_rows >= 0)),
    CONSTRAINT catalog_import_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT catalog_import_source_name_check CHECK (((length(source_name) >= 1) AND (length(source_name) <= 200))),
    CONSTRAINT catalog_import_source_sha256_check CHECK (((source_sha256 IS NULL) OR (source_sha256 ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT catalog_import_total_rows_check CHECK ((total_rows >= 1))
);

CREATE TABLE clinic.clinic (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    timezone text DEFAULT 'Asia/Ho_Chi_Minh'::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    singleton boolean DEFAULT true NOT NULL,
    CONSTRAINT clinic_singleton_is_true CHECK (singleton),
    CONSTRAINT clinic_slug_check CHECK ((slug ~ '^[a-z0-9][a-z0-9-]*$'::text))
);

CREATE TABLE clinic.consent (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    kind text NOT NULL,
    granted boolean NOT NULL,
    granted_at timestamp with time zone,
    revoked_at timestamp with time zone,
    source text,
    recorded_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT consent_kind_check CHECK ((kind = ANY (ARRAY['messaging'::text, 'marketing'::text, 'media'::text, 'data_processing'::text])))
);

CREATE TABLE clinic.consult_note (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    source_text text DEFAULT ''::text NOT NULL,
    body text NOT NULL,
    created_by uuid,
    approved_by uuid,
    approved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT consult_note_body_check CHECK (((length(body) >= 1) AND (length(body) <= 4000))),
    CONSTRAINT consult_note_check CHECK (((status <> 'approved'::text) OR (approved_at IS NOT NULL))),
    CONSTRAINT consult_note_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text])))
);

CREATE TABLE clinic.crm_activity (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    task_id uuid,
    kind text DEFAULT 'cskh'::text NOT NULL,
    channel text NOT NULL,
    outcome text,
    note text NOT NULL,
    actor_user_id uuid,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    next_action_at timestamp with time zone,
    next_action_type text,
    related_appointment_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT crm_activity_channel_check CHECK ((channel = ANY (ARRAY['call'::text, 'zalo'::text, 'sms'::text, 'internal_note'::text]))),
    CONSTRAINT crm_activity_kind_check CHECK ((kind = ANY (ARRAY['cskh'::text, 'complaint'::text, 'note'::text]))),
    CONSTRAINT crm_activity_outcome_check CHECK ((outcome = ANY (ARRAY['unanswered'::text, 'callback'::text, 'no_need'::text, 'busy'::text, 'booked'::text, 'doctor'::text, 'reaction'::text, 'complaint'::text, 'optout'::text, 'invalid'::text])))
);

CREATE TABLE clinic.crm_rule (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    rule_key text NOT NULL,
    name text NOT NULL,
    trigger text NOT NULL,
    delay_days integer DEFAULT 0 NOT NULL,
    suggested_action text NOT NULL,
    priority text DEFAULT 'normal'::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT crm_rule_delay_days_check CHECK ((delay_days >= 0)),
    CONSTRAINT crm_rule_priority_check CHECK ((priority = ANY (ARRAY['high'::text, 'normal'::text, 'low'::text]))),
    CONSTRAINT crm_rule_rule_key_check CHECK ((rule_key = ANY (ARRAY['d1'::text, 'd3'::text, 'd7'::text, 'due'::text, 'overdue'::text, 'no_show'::text, 'abandoned'::text, 'dormant90'::text, 'dormant180'::text, 'birthday'::text])))
);

CREATE TABLE clinic.crm_task (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    task_key text NOT NULL,
    patient_id uuid NOT NULL,
    rule_key text NOT NULL,
    reason text NOT NULL,
    priority text DEFAULT 'normal'::text NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    owner_user_id uuid,
    due_at timestamp with time zone NOT NULL,
    suggested_action text NOT NULL,
    source_event_id text,
    related_appointment_id uuid,
    related_plan_id uuid,
    resolution text,
    resolved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT crm_task_priority_check CHECK ((priority = ANY (ARRAY['high'::text, 'normal'::text, 'low'::text]))),
    CONSTRAINT crm_task_rule_key_check CHECK ((rule_key = ANY (ARRAY['d1'::text, 'd3'::text, 'd7'::text, 'due'::text, 'overdue'::text, 'no_show'::text, 'abandoned'::text, 'dormant90'::text, 'dormant180'::text, 'birthday'::text, 'manual'::text]))),
    CONSTRAINT crm_task_status_check CHECK ((status = ANY (ARRAY['open'::text, 'rescheduled'::text, 'resolved'::text, 'superseded'::text])))
);

CREATE TABLE clinic.episode (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    title text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    started_on date NOT NULL,
    closed_on date,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT episode_status_check CHECK ((status = ANY (ARRAY['active'::text, 'closed'::text])))
);

CREATE TABLE clinic.finance_notification (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    payment_id uuid NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    amount_vnd bigint NOT NULL,
    invoice_id uuid NOT NULL,
    is_read boolean DEFAULT false NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT finance_notification_amount_vnd_check CHECK ((amount_vnd >= 1)),
    CONSTRAINT finance_notification_body_check CHECK (((length(body) >= 1) AND (length(body) <= 500))),
    CONSTRAINT finance_notification_title_check CHECK (((length(title) >= 1) AND (length(title) <= 200)))
);

CREATE TABLE clinic.finance_period (
    clinic_id uuid NOT NULL,
    month text NOT NULL,
    status text DEFAULT 'closed'::text NOT NULL,
    closed_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_by uuid,
    paid_at timestamp with time zone,
    paid_by uuid,
    reference text,
    snapshot jsonb NOT NULL,
    CONSTRAINT finance_period_check CHECK (((status = 'paid'::text) = ((reference IS NOT NULL) AND (paid_at IS NOT NULL)))),
    CONSTRAINT finance_period_month_check CHECK ((month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'::text)),
    CONSTRAINT finance_period_reference_check CHECK (((reference IS NULL) OR ((length(reference) >= 1) AND (length(reference) <= 120)))),
    CONSTRAINT finance_period_status_check CHECK ((status = ANY (ARRAY['closed'::text, 'paid'::text])))
);

CREATE TABLE clinic.guide_article (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT guide_article_body_check CHECK (((char_length(body) >= 1) AND (char_length(body) <= 200000))),
    CONSTRAINT guide_article_id_check CHECK ((id ~ '^[a-z0-9][a-z0-9-]{0,79}$'::text)),
    CONSTRAINT guide_article_title_check CHECK (((char_length(title) >= 1) AND (char_length(title) <= 200)))
);

CREATE TABLE clinic.invoice (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    number text NOT NULL,
    patient_id uuid NOT NULL,
    source text NOT NULL,
    order_id uuid,
    amount_vnd bigint NOT NULL,
    received_vnd bigint DEFAULT 0 NOT NULL,
    invoice_date date NOT NULL,
    created_by uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT invoice_amount_vnd_check CHECK ((amount_vnd >= 0)),
    CONSTRAINT invoice_check CHECK ((received_vnd <= amount_vnd)),
    CONSTRAINT invoice_check1 CHECK (((source = 'order'::text) = (order_id IS NOT NULL))),
    CONSTRAINT invoice_number_check CHECK (((length(number) >= 3) AND (length(number) <= 40))),
    CONSTRAINT invoice_received_vnd_check CHECK ((received_vnd >= 0)),
    CONSTRAINT invoice_source_check CHECK ((source = ANY (ARRAY['finance'::text, 'order'::text])))
);

CREATE TABLE clinic.media (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    session_id uuid,
    stage text NOT NULL,
    region text,
    view text,
    storage_key text NOT NULL,
    mime text NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 text,
    consent_id uuid NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    uploaded_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    uploaded_at timestamp with time zone,
    confirmed_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT media_mime_check CHECK ((mime = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text]))),
    CONSTRAINT media_size_bytes_check CHECK ((size_bytes > 0)),
    CONSTRAINT media_stage_check CHECK ((stage = ANY (ARRAY['before'::text, 'after'::text]))),
    CONSTRAINT media_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'uploaded'::text, 'confirmed'::text])))
);

CREATE TABLE clinic."order" (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    doctor_id uuid NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    order_date date NOT NULL,
    diagnosis text DEFAULT ''::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    total_vnd bigint DEFAULT 0 NOT NULL,
    catalog_hash text,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    invoice_id uuid,
    received_vnd bigint DEFAULT 0 NOT NULL,
    paid boolean DEFAULT false NOT NULL,
    created_by uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT order_catalog_hash_check CHECK (((catalog_hash IS NULL) OR (catalog_hash ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT order_check CHECK (((status = 'draft'::text) OR ((reviewed_by IS NOT NULL) AND (reviewed_at IS NOT NULL)))),
    CONSTRAINT order_diagnosis_check CHECK ((length(diagnosis) <= 2000)),
    CONSTRAINT order_note_check CHECK ((length(note) <= 2000)),
    CONSTRAINT order_received_vnd_check CHECK ((received_vnd >= 0)),
    CONSTRAINT order_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text]))),
    CONSTRAINT order_total_vnd_check CHECK ((total_vnd >= 0))
);

CREATE TABLE clinic.order_item (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    order_id uuid NOT NULL,
    line_no integer NOT NULL,
    product_code text NOT NULL,
    name text NOT NULL,
    source_type text DEFAULT ''::text NOT NULL,
    unit text DEFAULT ''::text NOT NULL,
    row_number integer DEFAULT 0 NOT NULL,
    catalog_route text NOT NULL,
    route text NOT NULL,
    route_reason text DEFAULT ''::text NOT NULL,
    quantity integer NOT NULL,
    unit_price_vnd bigint NOT NULL,
    usage text DEFAULT ''::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    CONSTRAINT order_item_catalog_route_check CHECK ((catalog_route = ANY (ARRAY['PRESCRIPTION'::text, 'CONSULTATION'::text, 'NONE'::text, 'UNRESOLVED'::text]))),
    CONSTRAINT order_item_line_no_check CHECK ((line_no >= 1)),
    CONSTRAINT order_item_name_check CHECK (((length(name) >= 1) AND (length(name) <= 400))),
    CONSTRAINT order_item_note_check CHECK ((length(note) <= 1000)),
    CONSTRAINT order_item_quantity_check CHECK (((quantity >= 1) AND (quantity <= 9999))),
    CONSTRAINT order_item_route_check CHECK ((route = ANY (ARRAY['PRESCRIPTION'::text, 'CONSULTATION'::text, 'NONE'::text, 'UNRESOLVED'::text]))),
    CONSTRAINT order_item_route_reason_check CHECK ((length(route_reason) <= 500)),
    CONSTRAINT order_item_unit_price_vnd_check CHECK ((unit_price_vnd >= 0)),
    CONSTRAINT order_item_usage_check CHECK ((length(usage) <= 2000))
);

CREATE TABLE clinic.patient (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    code text NOT NULL,
    full_name text NOT NULL,
    phone text,
    birth_date date,
    gender text DEFAULT 'unknown'::text NOT NULL,
    doctor_id uuid,
    cs_owner_id uuid,
    marketing_opt_out boolean DEFAULT false NOT NULL,
    first_contact_at date,
    source text,
    recommendation_at date,
    expected_visit_source text,
    expected_visit_reason text,
    reactivated_at timestamp with time zone,
    last_contact_at timestamp with time zone,
    latest_outcome text,
    next_action_at timestamp with time zone,
    next_action_type text,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_protocol_session_id text,
    alerts text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT patient_alerts_size CHECK ((COALESCE(cardinality(alerts), 0) <= 20)),
    CONSTRAINT patient_expected_visit_source_check CHECK ((expected_visit_source = ANY (ARRAY['doctor_recommendation'::text, 'service_protocol'::text, 'treatment_plan'::text, 'appointment'::text, 'followup_automation'::text]))),
    CONSTRAINT patient_gender_check CHECK ((gender = ANY (ARRAY['female'::text, 'male'::text, 'other'::text, 'unknown'::text])))
);

CREATE TABLE clinic.patient_app_event (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    kind text NOT NULL,
    body text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT patient_app_event_body_check CHECK (((length(body) >= 1) AND (length(body) <= 2000))),
    CONSTRAINT patient_app_event_kind_check CHECK ((kind = 'aftercare'::text))
);

CREATE TABLE clinic.patient_brief (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    body text NOT NULL,
    source_ids text[] DEFAULT '{}'::text[] NOT NULL,
    approved_by uuid,
    approved_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT patient_brief_body_check CHECK (((length(body) >= 1) AND (length(body) <= 4000)))
);

CREATE TABLE clinic.patient_clinical_note (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    history text NOT NULL,
    diagnosis text NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    CONSTRAINT patient_clinical_note_diagnosis_check CHECK (((length(diagnosis) >= 1) AND (length(diagnosis) <= 4000))),
    CONSTRAINT patient_clinical_note_history_check CHECK (((length(history) >= 1) AND (length(history) <= 4000)))
);

CREATE TABLE clinic.payment (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    invoice_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    amount_vnd bigint NOT NULL,
    method text NOT NULL,
    paid_on date NOT NULL,
    received_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT payment_amount_vnd_check CHECK ((amount_vnd >= 1)),
    CONSTRAINT payment_idempotency_key_check CHECK (((length(idempotency_key) >= 3) AND (length(idempotency_key) <= 160))),
    CONSTRAINT payment_method_check CHECK ((method = ANY (ARRAY['cash'::text, 'transfer'::text])))
);

CREATE TABLE clinic.procedure_entry (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    service_id uuid NOT NULL,
    service_name text NOT NULL,
    terms_version integer NOT NULL,
    basis text NOT NULL,
    entry_date date NOT NULL,
    invoice_id uuid NOT NULL,
    owns_invoice boolean DEFAULT true NOT NULL,
    list_vnd bigint NOT NULL,
    discount_vnd bigint DEFAULT 0 NOT NULL,
    net_vnd bigint NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    note text NOT NULL,
    void_reason text,
    created_by uuid,
    approved_by uuid,
    approved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT procedure_entry_basis_check CHECK ((basis = ANY (ARRAY['net'::text, 'list'::text, 'collected'::text]))),
    CONSTRAINT procedure_entry_check CHECK ((discount_vnd <= list_vnd)),
    CONSTRAINT procedure_entry_check1 CHECK ((net_vnd = (list_vnd - discount_vnd))),
    CONSTRAINT procedure_entry_check2 CHECK (((status = 'void'::text) = (void_reason IS NOT NULL))),
    CONSTRAINT procedure_entry_discount_vnd_check CHECK ((discount_vnd >= 0)),
    CONSTRAINT procedure_entry_list_vnd_check CHECK ((list_vnd >= 1)),
    CONSTRAINT procedure_entry_net_vnd_check CHECK ((net_vnd >= 0)),
    CONSTRAINT procedure_entry_note_check CHECK (((length(note) >= 1) AND (length(note) <= 500))),
    CONSTRAINT procedure_entry_service_name_check CHECK (((length(service_name) >= 1) AND (length(service_name) <= 200))),
    CONSTRAINT procedure_entry_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'void'::text]))),
    CONSTRAINT procedure_entry_terms_version_check CHECK ((terms_version >= 1)),
    CONSTRAINT procedure_entry_void_reason_check CHECK (((void_reason IS NULL) OR ((length(void_reason) >= 1) AND (length(void_reason) <= 500))))
);

CREATE TABLE clinic.procedure_entry_person (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    entry_id uuid NOT NULL,
    "position" integer NOT NULL,
    doctor_id uuid NOT NULL,
    share_bp integer NOT NULL,
    rate_bp integer NOT NULL,
    CONSTRAINT procedure_entry_person_position_check CHECK ((("position" >= 1) AND ("position" <= 4))),
    CONSTRAINT procedure_entry_person_rate_bp_check CHECK (((rate_bp >= 0) AND (rate_bp <= 10000))),
    CONSTRAINT procedure_entry_person_share_bp_check CHECK (((share_bp >= 1) AND (share_bp <= 10000)))
);

CREATE TABLE clinic.product (
    clinic_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    unit text DEFAULT ''::text NOT NULL,
    source_type text DEFAULT ''::text NOT NULL,
    route text NOT NULL,
    price_vnd bigint NOT NULL,
    vat numeric(6,4) DEFAULT 0 NOT NULL,
    price_before_tax numeric(18,4) DEFAULT 0 NOT NULL,
    row_number integer DEFAULT 0 NOT NULL,
    batch text DEFAULT ''::text NOT NULL,
    serial text DEFAULT ''::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    catalog_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT product_catalog_hash_check CHECK ((catalog_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT product_code_check CHECK ((code ~ '^[A-Z0-9][A-Z0-9._-]{0,39}$'::text)),
    CONSTRAINT product_name_check CHECK (((length(name) >= 1) AND (length(name) <= 400))),
    CONSTRAINT product_price_before_tax_check CHECK ((price_before_tax >= (0)::numeric)),
    CONSTRAINT product_price_vnd_check CHECK ((price_vnd >= 0)),
    CONSTRAINT product_route_check CHECK ((route = ANY (ARRAY['PRESCRIPTION'::text, 'CONSULTATION'::text, 'NONE'::text, 'UNRESOLVED'::text]))),
    CONSTRAINT product_row_number_check CHECK ((row_number >= 0)),
    CONSTRAINT product_source_type_check CHECK ((length(source_type) <= 60)),
    CONSTRAINT product_unit_check CHECK ((length(unit) <= 40)),
    CONSTRAINT product_vat_check CHECK ((vat >= (0)::numeric))
);

CREATE TABLE clinic.protocol (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    milestones jsonb DEFAULT '[]'::jsonb NOT NULL,
    followup_days integer,
    window_days integer DEFAULT 45 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT protocol_code_check CHECK ((code ~ '^[a-z0-9][a-z0-9-]{1,39}$'::text)),
    CONSTRAINT protocol_followup_days_check CHECK (((followup_days IS NULL) OR ((followup_days >= 1) AND (followup_days <= 365)))),
    CONSTRAINT protocol_milestones_check CHECK ((jsonb_typeof(milestones) = 'array'::text)),
    CONSTRAINT protocol_name_check CHECK (((length(name) >= 1) AND (length(name) <= 120))),
    CONSTRAINT protocol_window_days_check CHECK (((window_days >= 1) AND (window_days <= 365)))
);

CREATE TABLE clinic.room (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    name text NOT NULL,
    capacity integer DEFAULT 1 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT room_capacity_check CHECK (((capacity >= 1) AND (capacity <= 20))),
    CONSTRAINT room_name_check CHECK (((length(name) >= 1) AND (length(name) <= 120)))
);

CREATE TABLE clinic.room_block (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    room_id uuid NOT NULL,
    day date NOT NULL,
    starts_at time without time zone NOT NULL,
    ends_at time without time zone NOT NULL,
    reason text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT room_block_check CHECK ((starts_at < ends_at)),
    CONSTRAINT room_block_reason_check CHECK (((length(reason) >= 1) AND (length(reason) <= 200)))
);

CREATE TABLE clinic.service (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    protocol_code text,
    room_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    terms_version integer DEFAULT 1 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT service_code_check CHECK ((code ~ '^[a-z0-9][a-z0-9-]{1,39}$'::text)),
    CONSTRAINT service_name_check CHECK (((length(name) >= 1) AND (length(name) <= 120))),
    CONSTRAINT service_terms_version_check CHECK ((terms_version >= 1))
);

CREATE TABLE clinic.service_version (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    service_id uuid NOT NULL,
    version_no integer NOT NULL,
    price_vnd bigint NOT NULL,
    rate_bp integer NOT NULL,
    basis text NOT NULL,
    duration_min integer NOT NULL,
    buffer_min integer DEFAULT 0 NOT NULL,
    changed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT service_version_basis_check CHECK ((basis = ANY (ARRAY['net'::text, 'list'::text, 'collected'::text]))),
    CONSTRAINT service_version_buffer_min_check CHECK (((buffer_min >= 0) AND (buffer_min <= 120))),
    CONSTRAINT service_version_duration_min_check CHECK (((duration_min >= 5) AND (duration_min <= 480))),
    CONSTRAINT service_version_price_vnd_check CHECK ((price_vnd >= 0)),
    CONSTRAINT service_version_rate_bp_check CHECK (((rate_bp >= 0) AND (rate_bp <= 10000))),
    CONSTRAINT service_version_version_no_check CHECK ((version_no >= 1))
);

CREATE TABLE clinic.staff_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text NOT NULL,
    shift jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT staff_profiles_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'manager'::text, 'doctor'::text, 'cs_staff'::text, 'reception'::text, 'accountant'::text]))),
    CONSTRAINT staff_profiles_shift_check CHECK ((jsonb_typeof(shift) = 'object'::text))
);

CREATE TABLE clinic.treatment_plan (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    episode_id uuid,
    doctor_id uuid,
    service_code text NOT NULL,
    title text NOT NULL,
    total_sessions integer DEFAULT 1 NOT NULL,
    completed_sessions integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    goal text,
    unit_price_vnd bigint,
    discount_vnd bigint,
    agreed_price_vnd bigint,
    service_terms_version integer,
    CONSTRAINT treatment_plan_agreed_price_vnd_check CHECK ((agreed_price_vnd >= 0)),
    CONSTRAINT treatment_plan_completed_sessions_check CHECK ((completed_sessions >= 0)),
    CONSTRAINT treatment_plan_discount_vnd_check CHECK ((discount_vnd >= 0)),
    CONSTRAINT treatment_plan_price_together CHECK ((((unit_price_vnd IS NULL) = (discount_vnd IS NULL)) AND ((unit_price_vnd IS NULL) = (agreed_price_vnd IS NULL)) AND ((unit_price_vnd IS NULL) = (service_terms_version IS NULL)))),
    CONSTRAINT treatment_plan_status_check CHECK ((status = ANY (ARRAY['planned'::text, 'active'::text, 'completed'::text, 'abandoned'::text, 'cancelled'::text]))),
    CONSTRAINT treatment_plan_total_sessions_check CHECK ((total_sessions >= 0)),
    CONSTRAINT treatment_plan_unit_price_vnd_check CHECK ((unit_price_vnd >= 0))
);

CREATE TABLE clinic.treatment_session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    plan_id uuid,
    doctor_id uuid,
    performed_at timestamp with time zone NOT NULL,
    protocol_id text,
    title text NOT NULL,
    note text,
    status text DEFAULT 'completed'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    session_type text,
    region text,
    view text,
    next_visit_on date,
    aftercare text,
    consent_id uuid,
    reviewed boolean DEFAULT false NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    created_by uuid,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT treatment_session_status_check CHECK ((status = ANY (ARRAY['scheduled'::text, 'completed'::text, 'cancelled'::text])))
);

CREATE TABLE clinic.user_account (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL,
    password_hash text,
    active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_account_email_check CHECK ((email = lower(email))),
    CONSTRAINT user_account_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'manager'::text, 'doctor'::text, 'cs_staff'::text, 'reception'::text, 'accountant'::text, 'patient'::text])))
);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.catalog_import
    ADD CONSTRAINT catalog_import_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_singleton_key UNIQUE (singleton);

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_slug_key UNIQUE (slug);

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_rule_key_key UNIQUE (clinic_id, rule_key);

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_task_key_key UNIQUE (clinic_id, task_key);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_payment_id_key UNIQUE (payment_id);

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_pkey PRIMARY KEY (clinic_id, month);

ALTER TABLE ONLY clinic.guide_article
    ADD CONSTRAINT guide_article_pkey PRIMARY KEY (clinic_id, id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_number_key UNIQUE (clinic_id, number);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_order_id_key UNIQUE (order_id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_storage_key_key UNIQUE (clinic_id, storage_key);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_order_id_line_no_key UNIQUE (order_id, line_no);

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_code_key UNIQUE (clinic_id, code);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_patient_id_key UNIQUE (clinic_id, patient_id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_idempotency_key_key UNIQUE (clinic_id, idempotency_key);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_entry_id_doctor_id_key UNIQUE (entry_id, doctor_id);

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_entry_id_position_key UNIQUE (entry_id, "position");

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.product
    ADD CONSTRAINT product_pkey PRIMARY KEY (clinic_id, code);

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_clinic_id_code_key UNIQUE (clinic_id, code);

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_name_key UNIQUE (clinic_id, name);

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_code_key UNIQUE (clinic_id, code);

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_service_id_version_no_key UNIQUE (service_id, version_no);

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_user_id_key UNIQUE (user_id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_pkey PRIMARY KEY (id);

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_email_key UNIQUE (clinic_id, email);

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_id_key UNIQUE (clinic_id, id);

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_pkey PRIMARY KEY (id);

CREATE INDEX appointment_doctor_idx ON clinic.appointment USING btree (clinic_id, doctor_id, starts_at);

CREATE INDEX appointment_patient_idx ON clinic.appointment USING btree (clinic_id, patient_id, starts_at DESC);

CREATE INDEX appointment_room_day_idx ON clinic.appointment USING btree (clinic_id, room_id, starts_at) WHERE (room_id IS NOT NULL);

CREATE INDEX appointment_time_idx ON clinic.appointment USING btree (clinic_id, starts_at);

CREATE INDEX audit_log_entity_idx ON clinic.audit_log USING btree (clinic_id, entity_type, entity_id);

CREATE INDEX audit_log_time_idx ON clinic.audit_log USING btree (clinic_id, occurred_at DESC);

CREATE INDEX auth_session_expiry_idx ON clinic.auth_session USING btree (expires_at);

CREATE INDEX auth_session_user_idx ON clinic.auth_session USING btree (clinic_id, user_id);

CREATE INDEX catalog_import_at_idx ON clinic.catalog_import USING btree (clinic_id, imported_at DESC);

CREATE INDEX consent_patient_idx ON clinic.consent USING btree (clinic_id, patient_id, kind, created_at DESC);

CREATE UNIQUE INDEX consult_note_one_draft_idx ON clinic.consult_note USING btree (clinic_id, patient_id) WHERE (status = 'draft'::text);

CREATE INDEX consult_note_patient_idx ON clinic.consult_note USING btree (clinic_id, patient_id, created_at DESC);

CREATE INDEX crm_activity_patient_idx ON clinic.crm_activity USING btree (clinic_id, patient_id, occurred_at DESC);

CREATE INDEX crm_task_patient_idx ON clinic.crm_task USING btree (clinic_id, patient_id);

CREATE INDEX crm_task_queue_idx ON clinic.crm_task USING btree (clinic_id, status, due_at);

CREATE INDEX finance_notification_idx ON clinic.finance_notification USING btree (clinic_id, created_at DESC);

CREATE INDEX invoice_due_idx ON clinic.invoice USING btree (clinic_id, invoice_date DESC) WHERE (received_vnd < amount_vnd);

CREATE INDEX invoice_patient_idx ON clinic.invoice USING btree (clinic_id, patient_id, invoice_date DESC);

CREATE INDEX media_patient_idx ON clinic.media USING btree (clinic_id, patient_id, created_at DESC);

CREATE INDEX media_session_idx ON clinic.media USING btree (clinic_id, session_id);

CREATE INDEX order_patient_idx ON clinic."order" USING btree (clinic_id, patient_id, created_at DESC);

CREATE INDEX order_status_idx ON clinic."order" USING btree (clinic_id, status, created_at DESC);

CREATE INDEX patient_app_event_idx ON clinic.patient_app_event USING btree (clinic_id, patient_id, created_at DESC);

CREATE INDEX patient_brief_idx ON clinic.patient_brief USING btree (clinic_id, patient_id, approved_at DESC);

CREATE INDEX patient_name_idx ON clinic.patient USING btree (clinic_id, lower(full_name) text_pattern_ops);

CREATE INDEX patient_phone_idx ON clinic.patient USING btree (clinic_id, phone);

CREATE INDEX payment_day_idx ON clinic.payment USING btree (clinic_id, paid_on DESC, created_at DESC);

CREATE INDEX payment_invoice_idx ON clinic.payment USING btree (clinic_id, invoice_id);

CREATE INDEX procedure_entry_day_idx ON clinic.procedure_entry USING btree (clinic_id, entry_date, created_at);

CREATE INDEX procedure_entry_invoice_idx ON clinic.procedure_entry USING btree (clinic_id, invoice_id);

CREATE INDEX procedure_entry_person_doctor_idx ON clinic.procedure_entry_person USING btree (clinic_id, doctor_id);

CREATE INDEX room_block_day_idx ON clinic.room_block USING btree (clinic_id, day, room_id);

CREATE INDEX treatment_session_patient_idx ON clinic.treatment_session USING btree (clinic_id, patient_id, performed_at DESC);

CREATE TRIGGER appointment_touch BEFORE UPDATE ON clinic.appointment FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON clinic.audit_log FOR EACH STATEMENT EXECUTE FUNCTION clinic.audit_log_immutable();

CREATE TRIGGER audit_log_no_update BEFORE DELETE OR UPDATE ON clinic.audit_log FOR EACH ROW EXECUTE FUNCTION clinic.audit_log_immutable();

CREATE TRIGGER clinic_no_delete BEFORE DELETE ON clinic.clinic FOR EACH ROW EXECUTE FUNCTION clinic.clinic_undeletable();

CREATE TRIGGER clinic_touch BEFORE UPDATE ON clinic.clinic FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER consult_note_touch BEFORE UPDATE ON clinic.consult_note FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER crm_rule_touch BEFORE UPDATE ON clinic.crm_rule FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER crm_task_touch BEFORE UPDATE ON clinic.crm_task FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER episode_touch BEFORE UPDATE ON clinic.episode FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER finance_period_frozen BEFORE DELETE OR UPDATE ON clinic.finance_period FOR EACH ROW EXECUTE FUNCTION clinic.finance_period_frozen();

CREATE TRIGGER guide_article_touch BEFORE UPDATE ON clinic.guide_article FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER invoice_touch BEFORE UPDATE ON clinic.invoice FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER media_touch BEFORE UPDATE ON clinic.media FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER order_approved_immutable BEFORE UPDATE ON clinic."order" FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable();

CREATE TRIGGER order_item_approved_immutable BEFORE DELETE OR UPDATE ON clinic.order_item FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable();

CREATE TRIGGER order_touch BEFORE UPDATE ON clinic."order" FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER patient_touch BEFORE UPDATE ON clinic.patient FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER procedure_entry_closed_guard BEFORE INSERT OR DELETE OR UPDATE ON clinic.procedure_entry FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard();

CREATE TRIGGER procedure_entry_person_closed_guard BEFORE INSERT OR DELETE OR UPDATE ON clinic.procedure_entry_person FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard();

CREATE TRIGGER procedure_entry_touch BEFORE UPDATE ON clinic.procedure_entry FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER product_touch BEFORE UPDATE ON clinic.product FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER protocol_touch BEFORE UPDATE ON clinic.protocol FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER room_touch BEFORE UPDATE ON clinic.room FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER service_touch BEFORE UPDATE ON clinic.service FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER service_version_append_only BEFORE DELETE OR UPDATE ON clinic.service_version FOR EACH ROW EXECUTE FUNCTION clinic.service_version_append_only();

CREATE TRIGGER staff_profiles_touch BEFORE UPDATE ON clinic.staff_profiles FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER treatment_plan_touch BEFORE UPDATE ON clinic.treatment_plan FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER treatment_session_touch BEFORE UPDATE ON clinic.treatment_session FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

CREATE TRIGGER user_account_touch BEFORE UPDATE ON clinic.user_account FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_room_fk FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room(clinic_id, id);

ALTER TABLE ONLY clinic.audit_log
    ADD CONSTRAINT audit_log_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY clinic.catalog_import
    ADD CONSTRAINT catalog_import_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_recorded_by_fkey FOREIGN KEY (clinic_id, recorded_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_actor_user_id_fkey FOREIGN KEY (clinic_id, actor_user_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_related_appointment_id_fkey FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment(clinic_id, id);

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_task_id_fkey FOREIGN KEY (clinic_id, task_id) REFERENCES clinic.crm_task(clinic_id, id);

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_owner_user_id_fkey FOREIGN KEY (clinic_id, owner_user_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_related_appointment_id_fkey FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment(clinic_id, id);

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_related_plan_id_fkey FOREIGN KEY (clinic_id, related_plan_id) REFERENCES clinic.treatment_plan(clinic_id, id);

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_payment_id_fkey FOREIGN KEY (clinic_id, payment_id) REFERENCES clinic.payment(clinic_id, id);

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_closed_by_fkey FOREIGN KEY (clinic_id, closed_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_paid_by_fkey FOREIGN KEY (clinic_id, paid_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.guide_article
    ADD CONSTRAINT guide_article_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_order_id_fkey FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order"(clinic_id, id);

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_consent_id_fkey FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent(clinic_id, id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_session_id_fkey FOREIGN KEY (clinic_id, session_id) REFERENCES clinic.treatment_session(clinic_id, id);

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_uploaded_by_fkey FOREIGN KEY (clinic_id, uploaded_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_reviewed_by_fkey FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_clinic_id_order_id_fkey FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order"(clinic_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_cs_owner_id_fkey FOREIGN KEY (clinic_id, cs_owner_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_reviewed_by_fkey FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_received_by_fkey FOREIGN KEY (clinic_id, received_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_service_id_fkey FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_entry_id_fkey FOREIGN KEY (clinic_id, entry_id) REFERENCES clinic.procedure_entry(clinic_id, id);

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_service_id_terms_version_fkey FOREIGN KEY (service_id, terms_version) REFERENCES clinic.service_version(service_id, version_no);

ALTER TABLE ONLY clinic.product
    ADD CONSTRAINT product_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_room_id_fkey FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room(clinic_id, id);

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_changed_by_fkey FOREIGN KEY (clinic_id, changed_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_service_id_fkey FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service(clinic_id, id);

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_episode_id_fkey FOREIGN KEY (clinic_id, episode_id) REFERENCES clinic.episode(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_plan_id_fkey FOREIGN KEY (clinic_id, plan_id) REFERENCES clinic.treatment_plan(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_consent_fk FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_created_by_fk FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_reviewed_by_fk FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);

GRANT USAGE ON SCHEMA clinic TO be_app;

GRANT USAGE ON SCHEMA ctx TO be_app;

REVOKE ALL ON FUNCTION clinic.ensure_clinic(p_name text, p_slug text, p_timezone text, p_id uuid) FROM PUBLIC;

REVOKE ALL ON FUNCTION clinic.record_retention_run(p_scope text, p_counts jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic.record_retention_run(p_scope text, p_counts jsonb) TO be_app;

REVOKE ALL ON FUNCTION ctx.the_clinic_id() FROM PUBLIC;
GRANT ALL ON FUNCTION ctx.the_clinic_id() TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.appointment TO be_app;

GRANT SELECT,INSERT ON TABLE clinic.audit_log TO be_app;

GRANT USAGE ON SEQUENCE clinic.audit_log_id_seq TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.auth_session TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.catalog_import TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.clinic TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.consent TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.consult_note TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_activity TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_rule TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_task TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.episode TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.finance_notification TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.finance_period TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.guide_article TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.invoice TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.media TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic."order" TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.order_item TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_app_event TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_brief TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_clinical_note TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.payment TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.procedure_entry TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.procedure_entry_person TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.product TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.protocol TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.room TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.room_block TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.service TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.service_version TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.staff_profiles TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.treatment_plan TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.treatment_session TO be_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.user_account TO be_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA clinic GRANT USAGE ON SEQUENCES TO be_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA clinic GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO be_app;
