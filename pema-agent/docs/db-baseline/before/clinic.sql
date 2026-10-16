--
-- PostgreSQL database dump
--

\restrict 0YZdW4AhSQ6cibJ9mGlIgCbKN9EOPb4swt0hg3DCjMVQY5dshaYsW2zfIMvgrBo

-- Dumped from database version 17.11 (Debian 17.11-1.pgdg12+2)
-- Dumped by pg_dump version 17.11 (Debian 17.11-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: clinic; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA clinic;


--
-- Name: account_purpose_guard(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.account_purpose_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'agent', 'pg_temp'
    AS $$
        BEGIN
            IF NEW.purpose = 'internal' AND EXISTS (SELECT 1 FROM clinic.conversation c
                                                     WHERE c.clinic_id = NEW.clinic_id
                                                       AND c.account_id = NEW.id) THEN
                RAISE EXCEPTION 'conversations still point at this account'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$;


--
-- Name: audit_log_immutable(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.audit_log_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'clinic.audit_log is append-only'; END $$;


--
-- Name: clinic_undeletable(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.clinic_undeletable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'the clinic row is the installation id and cannot be deleted'; END $$;


--
-- Name: conversation_account_guard(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.conversation_account_guard() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'agent', 'pg_temp'
    AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM agent.accounts a
                        WHERE a.clinic_id = NEW.clinic_id AND a.id = NEW.account_id
                          AND a.purpose = 'internal') THEN
                RAISE EXCEPTION 'an internal account cannot be the identity of a conversation'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$;


--
-- Name: ensure_clinic(text, text, text, uuid); Type: FUNCTION; Schema: clinic; Owner: -
--

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


--
-- Name: finance_closed_period_guard(); Type: FUNCTION; Schema: clinic; Owner: -
--

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


--
-- Name: finance_period_frozen(); Type: FUNCTION; Schema: clinic; Owner: -
--

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


--
-- Name: order_approved_immutable(); Type: FUNCTION; Schema: clinic; Owner: -
--

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


--
-- Name: service_version_append_only(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.service_version_append_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'clinic.service_version is append-only';
        END
        $$;


--
-- Name: touch_updated_at(); Type: FUNCTION; Schema: clinic; Owner: -
--

CREATE FUNCTION clinic.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: account_roster; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.account_roster (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    account_id text NOT NULL,
    user_id uuid NOT NULL,
    weekdays text[],
    on_date date,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    note text,
    created_by uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT account_roster_check CHECK (((weekdays IS NULL) <> (on_date IS NULL))),
    CONSTRAINT account_roster_check1 CHECK ((start_time <> end_time)),
    CONSTRAINT account_roster_note_check CHECK (((note IS NULL) OR (length(note) <= 200))),
    CONSTRAINT account_roster_weekdays_check CHECK (((weekdays IS NULL) OR (((cardinality(weekdays) >= 1) AND (cardinality(weekdays) <= 7)) AND (weekdays <@ ARRAY['mon'::text, 'tue'::text, 'wed'::text, 'thu'::text, 'fri'::text, 'sat'::text, 'sun'::text]))))
);


--
-- Name: appointment; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: audit_log; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: clinic; Owner: -
--

ALTER TABLE clinic.audit_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME clinic.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auth_session; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.auth_session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    password_fingerprint text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL
);


--
-- Name: catalog_import; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: channel_identity; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.channel_identity (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    channel text NOT NULL,
    external_user_id text NOT NULL,
    patient_id uuid,
    display_name text,
    friend_status text DEFAULT 'unknown'::text NOT NULL,
    verification_status text DEFAULT 'unlinked'::text NOT NULL,
    verified_at timestamp with time zone,
    verified_by uuid,
    last_inbound_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT channel_identity_channel_check CHECK ((channel = ANY (ARRAY['zalo_bot'::text, 'zalo_personal'::text, 'zalo_oa'::text]))),
    CONSTRAINT channel_identity_check CHECK (((verification_status <> 'verified'::text) OR ((patient_id IS NOT NULL) AND (verified_at IS NOT NULL)))),
    CONSTRAINT channel_identity_friend_status_check CHECK ((friend_status = ANY (ARRAY['unknown'::text, 'friend'::text, 'not_friend'::text]))),
    CONSTRAINT channel_identity_verification_status_check CHECK ((verification_status = ANY (ARRAY['unlinked'::text, 'pending'::text, 'verified'::text, 'rejected'::text])))
);


--
-- Name: channel_setting; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.channel_setting (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    channel text NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    kill_switch_on boolean DEFAULT false NOT NULL,
    kill_switch_reason text,
    kill_switch_changed_at timestamp with time zone,
    kill_switch_changed_by uuid,
    daily_cap integer,
    send_window_start time without time zone,
    send_window_end time without time zone,
    min_gap_seconds integer DEFAULT 0 NOT NULL,
    max_gap_seconds integer DEFAULT 0 NOT NULL,
    requires_friend boolean DEFAULT false NOT NULL,
    bridge_state text,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT channel_setting_bridge_state_check CHECK ((bridge_state = ANY (ARRAY['not_configured'::text, 'awaiting_qr'::text, 'connected'::text, 'blocked'::text, 'down'::text]))),
    CONSTRAINT channel_setting_channel_check CHECK ((channel = ANY (ARRAY['zalo_bot'::text, 'zalo_personal'::text, 'zalo_oa'::text]))),
    CONSTRAINT channel_setting_check CHECK ((max_gap_seconds >= min_gap_seconds)),
    CONSTRAINT channel_setting_daily_cap_check CHECK ((daily_cap >= 0)),
    CONSTRAINT channel_setting_min_gap_seconds_check CHECK ((min_gap_seconds >= 0))
);


--
-- Name: clinic; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: consent; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: consult_note; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: conversation; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.conversation (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    channel text NOT NULL,
    external_ref text NOT NULL,
    patient_id uuid,
    identity_id uuid,
    status text DEFAULT 'open'::text NOT NULL,
    assigned_user_id uuid,
    last_message_at timestamp with time zone,
    last_inbound_at timestamp with time zone,
    unread_count integer DEFAULT 0 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    account_id text,
    assignment_version integer DEFAULT 1 NOT NULL,
    CONSTRAINT conversation_assignment_version_check CHECK ((assignment_version >= 1)),
    CONSTRAINT conversation_channel_check CHECK ((channel = ANY (ARRAY['zalo_bot'::text, 'zalo_personal'::text, 'zalo_oa'::text]))),
    CONSTRAINT conversation_status_check CHECK ((status = ANY (ARRAY['open'::text, 'pending_review'::text, 'handoff'::text, 'closed'::text]))),
    CONSTRAINT conversation_unread_count_check CHECK ((unread_count >= 0))
);


--
-- Name: conversation_assignment; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.conversation_assignment (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    user_id uuid,
    kind text NOT NULL,
    previous_user_id uuid,
    reason text,
    at timestamp with time zone DEFAULT now() NOT NULL,
    by uuid,
    CONSTRAINT conversation_assignment_check CHECK (((kind <> 'takeover'::text) OR ((reason IS NOT NULL) AND (length(btrim(reason)) > 0)))),
    CONSTRAINT conversation_assignment_kind_check CHECK ((kind = ANY (ARRAY['claim'::text, 'takeover'::text, 'release'::text, 'shift_end'::text, 'assign'::text]))),
    CONSTRAINT conversation_assignment_reason_check CHECK (((reason IS NULL) OR (length(reason) <= 500)))
);


--
-- Name: crm_activity; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: crm_rule; Type: TABLE; Schema: clinic; Owner: -
--

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
    send_mode text DEFAULT 'staff_task'::text NOT NULL,
    conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT crm_rule_check CHECK (((rule_key <> 'birthday'::text) OR (send_mode = 'staff_task'::text))),
    CONSTRAINT crm_rule_delay_days_check CHECK ((delay_days >= 0)),
    CONSTRAINT crm_rule_priority_check CHECK ((priority = ANY (ARRAY['high'::text, 'normal'::text, 'low'::text]))),
    CONSTRAINT crm_rule_rule_key_check CHECK ((rule_key = ANY (ARRAY['d1'::text, 'd3'::text, 'd7'::text, 'due'::text, 'overdue'::text, 'no_show'::text, 'abandoned'::text, 'dormant90'::text, 'dormant180'::text, 'birthday'::text]))),
    CONSTRAINT crm_rule_send_mode_check CHECK ((send_mode = ANY (ARRAY['staff_task'::text, 'auto_reminder'::text, 'draft_for_review'::text])))
);


--
-- Name: crm_task; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: episode; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: finance_notification; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: finance_period; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: identity_link_attempt; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.identity_link_attempt (
    id bigint NOT NULL,
    clinic_id uuid NOT NULL,
    channel text NOT NULL,
    external_user_id text NOT NULL,
    method text NOT NULL,
    succeeded boolean NOT NULL,
    attempted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT identity_link_attempt_method_check CHECK ((method = ANY (ARRAY['phone'::text, 'code'::text])))
);


--
-- Name: identity_link_attempt_id_seq; Type: SEQUENCE; Schema: clinic; Owner: -
--

ALTER TABLE clinic.identity_link_attempt ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME clinic.identity_link_attempt_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: identity_link_code; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.identity_link_code (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    code_hash text NOT NULL,
    issued_by uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    used_identity_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT identity_link_code_code_hash_check CHECK ((code_hash ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: invoice; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: media; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: message; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.message (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    channel text NOT NULL,
    direction text NOT NULL,
    sender_type text NOT NULL,
    sender_user_id uuid,
    body text,
    masked_body text,
    status text DEFAULT 'received'::text NOT NULL,
    proactive boolean DEFAULT false NOT NULL,
    update_id text,
    external_message_id text,
    review_item_id uuid,
    error_code text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    sent_at timestamp with time zone,
    CONSTRAINT message_channel_check CHECK ((channel = ANY (ARRAY['zalo_bot'::text, 'zalo_personal'::text, 'zalo_oa'::text]))),
    CONSTRAINT message_check CHECK (((NOT proactive) OR (direction = 'outbound'::text))),
    CONSTRAINT message_direction_check CHECK ((direction = ANY (ARRAY['inbound'::text, 'outbound'::text]))),
    CONSTRAINT message_sender_type_check CHECK ((sender_type = ANY (ARRAY['patient'::text, 'staff'::text, 'ai_draft'::text, 'system'::text]))),
    CONSTRAINT message_status_check CHECK ((status = ANY (ARRAY['received'::text, 'draft'::text, 'queued'::text, 'sent'::text, 'failed'::text, 'rejected'::text])))
);


--
-- Name: message_template; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.message_template (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    template_key text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    marketing boolean DEFAULT false NOT NULL,
    active boolean DEFAULT true NOT NULL,
    approved_by uuid,
    approved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT message_template_check CHECK (((NOT active) OR (approved_at IS NOT NULL))),
    CONSTRAINT message_template_template_key_check CHECK ((template_key ~ '^[a-z0-9][a-z0-9_.-]*$'::text))
);


--
-- Name: notification_log; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.notification_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    outbox_id uuid NOT NULL,
    provider text NOT NULL,
    attempt integer NOT NULL,
    status text NOT NULL,
    latency_ms integer,
    error_code text,
    at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT notification_log_attempt_check CHECK ((attempt >= 1)),
    CONSTRAINT notification_log_error_code_check CHECK (((error_code IS NULL) OR (length(error_code) <= 64))),
    CONSTRAINT notification_log_latency_ms_check CHECK (((latency_ms IS NULL) OR (latency_ms >= 0))),
    CONSTRAINT notification_log_provider_check CHECK ((provider = ANY (ARRAY['in_app'::text, 'push'::text, 'zalo_bell'::text, 'team_group'::text]))),
    CONSTRAINT notification_log_status_check CHECK ((status = ANY (ARRAY['sent'::text, 'failed'::text, 'skipped'::text])))
);


--
-- Name: notification_outbox; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.notification_outbox (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    kind text NOT NULL,
    recipient_kind text NOT NULL,
    recipient_user_id uuid,
    conversation_id uuid,
    payload jsonb NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    chain_step text,
    lease_until timestamp with time zone,
    acked_at timestamp with time zone,
    acked_by uuid,
    CONSTRAINT notification_outbox_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT notification_outbox_chain_step_check CHECK (((chain_step IS NULL) OR (chain_step = ANY (ARRAY['bell'::text, 'done'::text])))),
    CONSTRAINT notification_outbox_check CHECK (((recipient_kind = 'user'::text) = (recipient_user_id IS NOT NULL))),
    CONSTRAINT notification_outbox_kind_check CHECK (((length(kind) >= 1) AND (length(kind) <= 64))),
    CONSTRAINT notification_outbox_recipient_kind_check CHECK ((recipient_kind = ANY (ARRAY['user'::text, 'team_group'::text, 'on_call'::text]))),
    CONSTRAINT notification_outbox_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text, 'skipped'::text])))
);


--
-- Name: notify_link_code; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.notify_link_code (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    code_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT notify_link_code_code_hash_check CHECK ((length(code_hash) = 64))
);


--
-- Name: notify_preference; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.notify_preference (
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    quiet_start time without time zone,
    quiet_end time without time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT notify_preference_check CHECK (((quiet_start IS NULL) = (quiet_end IS NULL))),
    CONSTRAINT notify_preference_check1 CHECK (((quiet_start IS NULL) OR (quiet_start <> quiet_end)))
);


--
-- Name: notify_setting; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.notify_setting (
    clinic_id uuid NOT NULL,
    ack_timeout_s integer DEFAULT 180 NOT NULL,
    team_group_id text,
    in_app_enabled boolean DEFAULT true NOT NULL,
    push_enabled boolean DEFAULT false NOT NULL,
    bell_enabled boolean DEFAULT true NOT NULL,
    group_enabled boolean DEFAULT true NOT NULL,
    public_base_url text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by uuid,
    CONSTRAINT notify_setting_ack_timeout_s_check CHECK (((ack_timeout_s >= 30) AND (ack_timeout_s <= 3600))),
    CONSTRAINT notify_setting_public_base_url_check CHECK (((public_base_url IS NULL) OR (length(public_base_url) <= 300))),
    CONSTRAINT notify_setting_team_group_id_check CHECK (((team_group_id IS NULL) OR (length(team_group_id) <= 200)))
);


--
-- Name: on_call_contacts; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.on_call_contacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    zalo_number text NOT NULL,
    owner text NOT NULL,
    valid_from timestamp with time zone DEFAULT now() NOT NULL,
    valid_to timestamp with time zone,
    active boolean DEFAULT true NOT NULL,
    is_fixture boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT on_call_contacts_check CHECK (((valid_to IS NULL) OR (valid_to > valid_from))),
    CONSTRAINT on_call_contacts_owner_check CHECK (((length(owner) >= 1) AND (length(owner) <= 120))),
    CONSTRAINT on_call_contacts_zalo_number_check CHECK ((zalo_number ~ '^\+?[0-9]{8,15}$'::text))
);


--
-- Name: order; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: order_item; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: patient; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: patient_app_event; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.patient_app_event (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    kind text NOT NULL,
    body text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT patient_app_event_body_check CHECK (((length(body) >= 1) AND (length(body) <= 2000))),
    CONSTRAINT patient_app_event_kind_check CHECK ((kind = ANY (ARRAY['message'::text, 'aftercare'::text])))
);


--
-- Name: patient_brief; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: patient_clinical_note; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: patient_ownership; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.patient_ownership (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    cs_owner uuid,
    doctor uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: payment; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: procedure_entry; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: procedure_entry_person; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: product; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: protocol; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: push_token; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.push_token (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    platform text NOT NULL,
    token_hash text NOT NULL,
    token_enc text NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT push_token_platform_check CHECK ((platform = ANY (ARRAY['android'::text, 'ios'::text, 'web'::text]))),
    CONSTRAINT push_token_token_hash_check CHECK ((length(token_hash) = 64))
);


--
-- Name: review_item; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.review_item (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    kind text NOT NULL,
    origin text DEFAULT 'agent_turn'::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    conversation_id uuid,
    patient_id uuid,
    job_id text,
    draft_text text,
    final_text text,
    payload jsonb,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    risk_level text DEFAULT 'normal'::text NOT NULL,
    red_flags text[] DEFAULT '{}'::text[] NOT NULL,
    requires_doctor boolean DEFAULT false NOT NULL,
    model text,
    prompt_version text,
    expires_at timestamp with time zone,
    decided_by uuid,
    decided_at timestamp with time zone,
    decision_note text,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT review_item_check CHECK (((risk_level <> 'red_flag'::text) OR requires_doctor)),
    CONSTRAINT review_item_check1 CHECK (((kind <> 'triage_alert'::text) OR requires_doctor)),
    CONSTRAINT review_item_kind_check CHECK ((kind = ANY (ARRAY['reply_draft'::text, 'followup_draft'::text, 'triage_alert'::text, 'media_flag'::text, 'identity_check'::text]))),
    CONSTRAINT review_item_origin_check CHECK ((origin = ANY (ARRAY['agent_turn'::text, 'scheduled_agent'::text, 'crm_rule'::text, 'policy'::text]))),
    CONSTRAINT review_item_risk_level_check CHECK ((risk_level = ANY (ARRAY['normal'::text, 'attention'::text, 'red_flag'::text]))),
    CONSTRAINT review_item_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text, 'escalated'::text, 'expired'::text])))
);


--
-- Name: room; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: room_block; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: service; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: service_version; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: sla_check; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.sla_check (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    request_id uuid NOT NULL,
    idx integer NOT NULL,
    due_at timestamp with time zone NOT NULL,
    dedupe_key text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    lease_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sla_check_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT sla_check_dedupe_key_check CHECK (((length(dedupe_key) >= 1) AND (length(dedupe_key) <= 200))),
    CONSTRAINT sla_check_idx_check CHECK ((idx >= 0)),
    CONSTRAINT sla_check_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'done'::text, 'failed'::text])))
);


--
-- Name: staff_profiles; Type: TABLE; Schema: clinic; Owner: -
--

CREATE TABLE clinic.staff_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text NOT NULL,
    skills text[] DEFAULT '{}'::text[] NOT NULL,
    shift jsonb DEFAULT '{}'::jsonb NOT NULL,
    capacity integer DEFAULT 5 NOT NULL,
    languages text[] DEFAULT ARRAY['vi'::text] NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    notify_zalo_user_id text,
    notify_zalo_consented_at timestamp with time zone,
    CONSTRAINT staff_profiles_capacity_check CHECK ((capacity >= 0)),
    CONSTRAINT staff_profiles_notify_consent CHECK (((notify_zalo_user_id IS NULL) = (notify_zalo_consented_at IS NULL))),
    CONSTRAINT staff_profiles_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'manager'::text, 'doctor'::text, 'cs_staff'::text, 'reception'::text, 'accountant'::text]))),
    CONSTRAINT staff_profiles_shift_check CHECK ((jsonb_typeof(shift) = 'object'::text))
);


--
-- Name: treatment_plan; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: treatment_session; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: user_account; Type: TABLE; Schema: clinic; Owner: -
--

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


--
-- Name: account_roster account_roster_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: account_roster account_roster_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_pkey PRIMARY KEY (id);


--
-- Name: appointment appointment_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: appointment appointment_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: auth_session auth_session_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: auth_session auth_session_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_pkey PRIMARY KEY (id);


--
-- Name: catalog_import catalog_import_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.catalog_import
    ADD CONSTRAINT catalog_import_pkey PRIMARY KEY (id);


--
-- Name: channel_identity channel_identity_clinic_id_channel_external_user_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_clinic_id_channel_external_user_id_key UNIQUE (clinic_id, channel, external_user_id);


--
-- Name: channel_identity channel_identity_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: channel_identity channel_identity_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_pkey PRIMARY KEY (id);


--
-- Name: channel_setting channel_setting_clinic_id_channel_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_clinic_id_channel_key UNIQUE (clinic_id, channel);


--
-- Name: channel_setting channel_setting_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: channel_setting channel_setting_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_pkey PRIMARY KEY (id);


--
-- Name: clinic clinic_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_pkey PRIMARY KEY (id);


--
-- Name: clinic clinic_singleton_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_singleton_key UNIQUE (singleton);


--
-- Name: clinic clinic_slug_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.clinic
    ADD CONSTRAINT clinic_slug_key UNIQUE (slug);


--
-- Name: consent consent_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: consent consent_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_pkey PRIMARY KEY (id);


--
-- Name: consult_note consult_note_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: consult_note consult_note_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_pkey PRIMARY KEY (id);


--
-- Name: conversation_assignment conversation_assignment_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: conversation_assignment conversation_assignment_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_pkey PRIMARY KEY (id);


--
-- Name: conversation conversation_clinic_id_channel_external_ref_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_channel_external_ref_key UNIQUE (clinic_id, channel, external_ref);


--
-- Name: conversation conversation_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: conversation conversation_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_pkey PRIMARY KEY (id);


--
-- Name: crm_activity crm_activity_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: crm_activity crm_activity_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_pkey PRIMARY KEY (id);


--
-- Name: crm_rule crm_rule_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: crm_rule crm_rule_clinic_id_rule_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_rule_key_key UNIQUE (clinic_id, rule_key);


--
-- Name: crm_rule crm_rule_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_pkey PRIMARY KEY (id);


--
-- Name: crm_task crm_task_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: crm_task crm_task_clinic_id_task_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_task_key_key UNIQUE (clinic_id, task_key);


--
-- Name: crm_task crm_task_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_pkey PRIMARY KEY (id);


--
-- Name: episode episode_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: episode episode_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_pkey PRIMARY KEY (id);


--
-- Name: finance_notification finance_notification_payment_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_payment_id_key UNIQUE (payment_id);


--
-- Name: finance_notification finance_notification_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_pkey PRIMARY KEY (id);


--
-- Name: finance_period finance_period_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_pkey PRIMARY KEY (clinic_id, month);


--
-- Name: identity_link_attempt identity_link_attempt_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_attempt
    ADD CONSTRAINT identity_link_attempt_pkey PRIMARY KEY (id);


--
-- Name: identity_link_code identity_link_code_clinic_id_code_hash_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_code_hash_key UNIQUE (clinic_id, code_hash);


--
-- Name: identity_link_code identity_link_code_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: identity_link_code identity_link_code_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_pkey PRIMARY KEY (id);


--
-- Name: invoice invoice_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: invoice invoice_clinic_id_number_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_number_key UNIQUE (clinic_id, number);


--
-- Name: invoice invoice_order_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_order_id_key UNIQUE (order_id);


--
-- Name: invoice invoice_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_pkey PRIMARY KEY (id);


--
-- Name: media media_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: media media_clinic_id_storage_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_storage_key_key UNIQUE (clinic_id, storage_key);


--
-- Name: media media_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_pkey PRIMARY KEY (id);


--
-- Name: message message_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: message message_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (id);


--
-- Name: message_template message_template_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message_template
    ADD CONSTRAINT message_template_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: message_template message_template_clinic_id_template_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message_template
    ADD CONSTRAINT message_template_clinic_id_template_key_key UNIQUE (clinic_id, template_key);


--
-- Name: message_template message_template_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message_template
    ADD CONSTRAINT message_template_pkey PRIMARY KEY (id);


--
-- Name: notification_log notification_log_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_log
    ADD CONSTRAINT notification_log_pkey PRIMARY KEY (id);


--
-- Name: notification_outbox notification_outbox_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: notification_outbox notification_outbox_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_pkey PRIMARY KEY (id);


--
-- Name: notify_link_code notify_link_code_clinic_id_code_hash_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_link_code
    ADD CONSTRAINT notify_link_code_clinic_id_code_hash_key UNIQUE (clinic_id, code_hash);


--
-- Name: notify_link_code notify_link_code_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_link_code
    ADD CONSTRAINT notify_link_code_pkey PRIMARY KEY (id);


--
-- Name: notify_preference notify_preference_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_preference
    ADD CONSTRAINT notify_preference_pkey PRIMARY KEY (clinic_id, user_id);


--
-- Name: notify_setting notify_setting_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_setting
    ADD CONSTRAINT notify_setting_pkey PRIMARY KEY (clinic_id);


--
-- Name: on_call_contacts on_call_contacts_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.on_call_contacts
    ADD CONSTRAINT on_call_contacts_pkey PRIMARY KEY (id);


--
-- Name: order order_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: order_item order_item_order_id_line_no_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_order_id_line_no_key UNIQUE (order_id, line_no);


--
-- Name: order_item order_item_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_pkey PRIMARY KEY (id);


--
-- Name: order order_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_pkey PRIMARY KEY (id);


--
-- Name: patient_app_event patient_app_event_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: patient_app_event patient_app_event_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_pkey PRIMARY KEY (id);


--
-- Name: patient_brief patient_brief_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: patient_brief patient_brief_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_pkey PRIMARY KEY (id);


--
-- Name: patient patient_clinic_id_code_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_code_key UNIQUE (clinic_id, code);


--
-- Name: patient patient_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: patient_clinical_note patient_clinical_note_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: patient_clinical_note patient_clinical_note_clinic_id_patient_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_patient_id_key UNIQUE (clinic_id, patient_id);


--
-- Name: patient_clinical_note patient_clinical_note_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_pkey PRIMARY KEY (id);


--
-- Name: patient_ownership patient_ownership_patient_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_patient_id_key UNIQUE (patient_id);


--
-- Name: patient_ownership patient_ownership_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_pkey PRIMARY KEY (id);


--
-- Name: patient patient_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_pkey PRIMARY KEY (id);


--
-- Name: payment payment_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: payment payment_clinic_id_idempotency_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_idempotency_key_key UNIQUE (clinic_id, idempotency_key);


--
-- Name: payment payment_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_pkey PRIMARY KEY (id);


--
-- Name: procedure_entry procedure_entry_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: procedure_entry_person procedure_entry_person_entry_id_doctor_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_entry_id_doctor_id_key UNIQUE (entry_id, doctor_id);


--
-- Name: procedure_entry_person procedure_entry_person_entry_id_position_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_entry_id_position_key UNIQUE (entry_id, "position");


--
-- Name: procedure_entry_person procedure_entry_person_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_pkey PRIMARY KEY (id);


--
-- Name: procedure_entry procedure_entry_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_pkey PRIMARY KEY (id);


--
-- Name: product product_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.product
    ADD CONSTRAINT product_pkey PRIMARY KEY (clinic_id, code);


--
-- Name: protocol protocol_clinic_id_code_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_clinic_id_code_key UNIQUE (clinic_id, code);


--
-- Name: protocol protocol_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_pkey PRIMARY KEY (id);


--
-- Name: push_token push_token_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.push_token
    ADD CONSTRAINT push_token_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: push_token push_token_clinic_id_token_hash_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.push_token
    ADD CONSTRAINT push_token_clinic_id_token_hash_key UNIQUE (clinic_id, token_hash);


--
-- Name: push_token push_token_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.push_token
    ADD CONSTRAINT push_token_pkey PRIMARY KEY (id);


--
-- Name: review_item review_item_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: review_item review_item_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_pkey PRIMARY KEY (id);


--
-- Name: room_block room_block_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_pkey PRIMARY KEY (id);


--
-- Name: room room_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: room room_clinic_id_name_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_name_key UNIQUE (clinic_id, name);


--
-- Name: room room_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_pkey PRIMARY KEY (id);


--
-- Name: service service_clinic_id_code_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_code_key UNIQUE (clinic_id, code);


--
-- Name: service service_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: service service_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_pkey PRIMARY KEY (id);


--
-- Name: service_version service_version_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_pkey PRIMARY KEY (id);


--
-- Name: service_version service_version_service_id_version_no_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_service_id_version_no_key UNIQUE (service_id, version_no);


--
-- Name: sla_check sla_check_clinic_id_dedupe_key_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.sla_check
    ADD CONSTRAINT sla_check_clinic_id_dedupe_key_key UNIQUE (clinic_id, dedupe_key);


--
-- Name: sla_check sla_check_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.sla_check
    ADD CONSTRAINT sla_check_pkey PRIMARY KEY (id);


--
-- Name: staff_profiles staff_profiles_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_pkey PRIMARY KEY (id);


--
-- Name: staff_profiles staff_profiles_user_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_user_id_key UNIQUE (user_id);


--
-- Name: treatment_plan treatment_plan_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: treatment_plan treatment_plan_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_pkey PRIMARY KEY (id);


--
-- Name: treatment_session treatment_session_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: treatment_session treatment_session_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_pkey PRIMARY KEY (id);


--
-- Name: user_account user_account_clinic_id_email_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_email_key UNIQUE (clinic_id, email);


--
-- Name: user_account user_account_clinic_id_id_key; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: user_account user_account_pkey; Type: CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_pkey PRIMARY KEY (id);


--
-- Name: account_roster_account_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX account_roster_account_idx ON clinic.account_roster USING btree (clinic_id, account_id);


--
-- Name: account_roster_user_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX account_roster_user_idx ON clinic.account_roster USING btree (clinic_id, user_id);


--
-- Name: appointment_doctor_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX appointment_doctor_idx ON clinic.appointment USING btree (clinic_id, doctor_id, starts_at);


--
-- Name: appointment_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX appointment_patient_idx ON clinic.appointment USING btree (clinic_id, patient_id, starts_at DESC);


--
-- Name: appointment_room_day_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX appointment_room_day_idx ON clinic.appointment USING btree (clinic_id, room_id, starts_at) WHERE (room_id IS NOT NULL);


--
-- Name: appointment_time_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX appointment_time_idx ON clinic.appointment USING btree (clinic_id, starts_at);


--
-- Name: audit_log_entity_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX audit_log_entity_idx ON clinic.audit_log USING btree (clinic_id, entity_type, entity_id);


--
-- Name: audit_log_time_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX audit_log_time_idx ON clinic.audit_log USING btree (clinic_id, occurred_at DESC);


--
-- Name: auth_session_expiry_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX auth_session_expiry_idx ON clinic.auth_session USING btree (expires_at);


--
-- Name: auth_session_user_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX auth_session_user_idx ON clinic.auth_session USING btree (clinic_id, user_id);


--
-- Name: catalog_import_at_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX catalog_import_at_idx ON clinic.catalog_import USING btree (clinic_id, imported_at DESC);


--
-- Name: consent_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX consent_patient_idx ON clinic.consent USING btree (clinic_id, patient_id, kind, created_at DESC);


--
-- Name: consult_note_one_draft_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE UNIQUE INDEX consult_note_one_draft_idx ON clinic.consult_note USING btree (clinic_id, patient_id) WHERE (status = 'draft'::text);


--
-- Name: consult_note_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX consult_note_patient_idx ON clinic.consult_note USING btree (clinic_id, patient_id, created_at DESC);


--
-- Name: conversation_account_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX conversation_account_idx ON clinic.conversation USING btree (clinic_id, account_id, status, last_message_at DESC);


--
-- Name: conversation_assignment_conversation_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX conversation_assignment_conversation_idx ON clinic.conversation_assignment USING btree (clinic_id, conversation_id, at DESC);


--
-- Name: conversation_closed_age_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX conversation_closed_age_idx ON clinic.conversation USING btree (clinic_id, updated_at) WHERE (status = 'closed'::text);


--
-- Name: conversation_inbox_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX conversation_inbox_idx ON clinic.conversation USING btree (clinic_id, status, last_message_at DESC);


--
-- Name: crm_activity_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX crm_activity_patient_idx ON clinic.crm_activity USING btree (clinic_id, patient_id, occurred_at DESC);


--
-- Name: crm_task_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX crm_task_patient_idx ON clinic.crm_task USING btree (clinic_id, patient_id);


--
-- Name: crm_task_queue_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX crm_task_queue_idx ON clinic.crm_task USING btree (clinic_id, status, due_at);


--
-- Name: finance_notification_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX finance_notification_idx ON clinic.finance_notification USING btree (clinic_id, created_at DESC);


--
-- Name: identity_link_attempt_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX identity_link_attempt_idx ON clinic.identity_link_attempt USING btree (clinic_id, channel, external_user_id, attempted_at DESC);


--
-- Name: identity_link_code_expiry_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX identity_link_code_expiry_idx ON clinic.identity_link_code USING btree (clinic_id, expires_at);


--
-- Name: identity_link_code_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX identity_link_code_patient_idx ON clinic.identity_link_code USING btree (clinic_id, patient_id, created_at DESC);


--
-- Name: invoice_due_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX invoice_due_idx ON clinic.invoice USING btree (clinic_id, invoice_date DESC) WHERE (received_vnd < amount_vnd);


--
-- Name: invoice_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX invoice_patient_idx ON clinic.invoice USING btree (clinic_id, patient_id, invoice_date DESC);


--
-- Name: media_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX media_patient_idx ON clinic.media USING btree (clinic_id, patient_id, created_at DESC);


--
-- Name: media_session_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX media_session_idx ON clinic.media USING btree (clinic_id, session_id);


--
-- Name: message_conversation_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX message_conversation_idx ON clinic.message USING btree (clinic_id, conversation_id, created_at DESC);


--
-- Name: message_proactive_cap_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX message_proactive_cap_idx ON clinic.message USING btree (clinic_id, channel, created_at) WHERE (proactive AND (direction = 'outbound'::text));


--
-- Name: message_update_dedupe_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE UNIQUE INDEX message_update_dedupe_idx ON clinic.message USING btree (clinic_id, channel, update_id) WHERE (update_id IS NOT NULL);


--
-- Name: notification_log_outbox_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notification_log_outbox_idx ON clinic.notification_log USING btree (clinic_id, outbox_id, at);


--
-- Name: notification_outbox_conversation_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notification_outbox_conversation_idx ON clinic.notification_outbox USING btree (clinic_id, conversation_id);


--
-- Name: notification_outbox_due_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notification_outbox_due_idx ON clinic.notification_outbox USING btree (clinic_id, next_attempt_at) WHERE (state = 'pending'::text);


--
-- Name: notification_outbox_pending_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notification_outbox_pending_idx ON clinic.notification_outbox USING btree (clinic_id, created_at) WHERE (state = 'pending'::text);


--
-- Name: notification_outbox_recipient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notification_outbox_recipient_idx ON clinic.notification_outbox USING btree (clinic_id, recipient_user_id, created_at DESC) WHERE (recipient_user_id IS NOT NULL);


--
-- Name: notify_link_code_user_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX notify_link_code_user_idx ON clinic.notify_link_code USING btree (clinic_id, user_id, created_at DESC);


--
-- Name: on_call_contacts_active_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX on_call_contacts_active_idx ON clinic.on_call_contacts USING btree (clinic_id, active, valid_from);


--
-- Name: order_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX order_patient_idx ON clinic."order" USING btree (clinic_id, patient_id, created_at DESC);


--
-- Name: order_status_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX order_status_idx ON clinic."order" USING btree (clinic_id, status, created_at DESC);


--
-- Name: patient_app_event_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX patient_app_event_idx ON clinic.patient_app_event USING btree (clinic_id, patient_id, created_at DESC);


--
-- Name: patient_brief_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX patient_brief_idx ON clinic.patient_brief USING btree (clinic_id, patient_id, approved_at DESC);


--
-- Name: patient_name_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX patient_name_idx ON clinic.patient USING btree (clinic_id, lower(full_name) text_pattern_ops);


--
-- Name: patient_phone_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX patient_phone_idx ON clinic.patient USING btree (clinic_id, phone);


--
-- Name: payment_day_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX payment_day_idx ON clinic.payment USING btree (clinic_id, paid_on DESC, created_at DESC);


--
-- Name: payment_invoice_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX payment_invoice_idx ON clinic.payment USING btree (clinic_id, invoice_id);


--
-- Name: procedure_entry_day_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX procedure_entry_day_idx ON clinic.procedure_entry USING btree (clinic_id, entry_date, created_at);


--
-- Name: procedure_entry_invoice_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX procedure_entry_invoice_idx ON clinic.procedure_entry USING btree (clinic_id, invoice_id);


--
-- Name: procedure_entry_person_doctor_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX procedure_entry_person_doctor_idx ON clinic.procedure_entry_person USING btree (clinic_id, doctor_id);


--
-- Name: push_token_user_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX push_token_user_idx ON clinic.push_token USING btree (clinic_id, user_id);


--
-- Name: review_item_job_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE UNIQUE INDEX review_item_job_idx ON clinic.review_item USING btree (clinic_id, job_id) WHERE (job_id IS NOT NULL);


--
-- Name: review_item_queue_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX review_item_queue_idx ON clinic.review_item USING btree (clinic_id, status, created_at);


--
-- Name: room_block_day_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX room_block_day_idx ON clinic.room_block USING btree (clinic_id, day, room_id);


--
-- Name: sla_check_due_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX sla_check_due_idx ON clinic.sla_check USING btree (clinic_id, due_at) WHERE (state = 'pending'::text);


--
-- Name: treatment_session_patient_idx; Type: INDEX; Schema: clinic; Owner: -
--

CREATE INDEX treatment_session_patient_idx ON clinic.treatment_session USING btree (clinic_id, patient_id, performed_at DESC);


--
-- Name: account_roster account_roster_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER account_roster_touch BEFORE UPDATE ON clinic.account_roster FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: appointment appointment_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER appointment_touch BEFORE UPDATE ON clinic.appointment FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: audit_log audit_log_no_truncate; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON clinic.audit_log FOR EACH STATEMENT EXECUTE FUNCTION clinic.audit_log_immutable();


--
-- Name: audit_log audit_log_no_update; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER audit_log_no_update BEFORE DELETE OR UPDATE ON clinic.audit_log FOR EACH ROW EXECUTE FUNCTION clinic.audit_log_immutable();


--
-- Name: channel_setting channel_setting_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER channel_setting_touch BEFORE UPDATE ON clinic.channel_setting FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: clinic clinic_no_delete; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER clinic_no_delete BEFORE DELETE ON clinic.clinic FOR EACH ROW EXECUTE FUNCTION clinic.clinic_undeletable();


--
-- Name: clinic clinic_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER clinic_touch BEFORE UPDATE ON clinic.clinic FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: consult_note consult_note_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER consult_note_touch BEFORE UPDATE ON clinic.consult_note FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: conversation conversation_account_guard; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER conversation_account_guard BEFORE INSERT OR UPDATE OF account_id ON clinic.conversation FOR EACH ROW WHEN ((new.account_id IS NOT NULL)) EXECUTE FUNCTION clinic.conversation_account_guard();


--
-- Name: conversation conversation_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER conversation_touch BEFORE UPDATE ON clinic.conversation FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: crm_rule crm_rule_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER crm_rule_touch BEFORE UPDATE ON clinic.crm_rule FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: crm_task crm_task_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER crm_task_touch BEFORE UPDATE ON clinic.crm_task FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: episode episode_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER episode_touch BEFORE UPDATE ON clinic.episode FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: finance_period finance_period_frozen; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER finance_period_frozen BEFORE DELETE OR UPDATE ON clinic.finance_period FOR EACH ROW EXECUTE FUNCTION clinic.finance_period_frozen();


--
-- Name: invoice invoice_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER invoice_touch BEFORE UPDATE ON clinic.invoice FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: media media_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER media_touch BEFORE UPDATE ON clinic.media FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: message_template message_template_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER message_template_touch BEFORE UPDATE ON clinic.message_template FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: notification_outbox notification_outbox_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER notification_outbox_touch BEFORE UPDATE ON clinic.notification_outbox FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: notify_preference notify_preference_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER notify_preference_touch BEFORE UPDATE ON clinic.notify_preference FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: notify_setting notify_setting_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER notify_setting_touch BEFORE UPDATE ON clinic.notify_setting FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: on_call_contacts on_call_contacts_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER on_call_contacts_touch BEFORE UPDATE ON clinic.on_call_contacts FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: order order_approved_immutable; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER order_approved_immutable BEFORE UPDATE ON clinic."order" FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable();


--
-- Name: order_item order_item_approved_immutable; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER order_item_approved_immutable BEFORE DELETE OR UPDATE ON clinic.order_item FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable();


--
-- Name: order order_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER order_touch BEFORE UPDATE ON clinic."order" FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: patient_ownership patient_ownership_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER patient_ownership_touch BEFORE UPDATE ON clinic.patient_ownership FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: patient patient_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER patient_touch BEFORE UPDATE ON clinic.patient FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: procedure_entry procedure_entry_closed_guard; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER procedure_entry_closed_guard BEFORE INSERT OR DELETE OR UPDATE ON clinic.procedure_entry FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard();


--
-- Name: procedure_entry_person procedure_entry_person_closed_guard; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER procedure_entry_person_closed_guard BEFORE INSERT OR DELETE OR UPDATE ON clinic.procedure_entry_person FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard();


--
-- Name: procedure_entry procedure_entry_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER procedure_entry_touch BEFORE UPDATE ON clinic.procedure_entry FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: product product_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER product_touch BEFORE UPDATE ON clinic.product FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: protocol protocol_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER protocol_touch BEFORE UPDATE ON clinic.protocol FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: review_item review_item_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER review_item_touch BEFORE UPDATE ON clinic.review_item FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: room room_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER room_touch BEFORE UPDATE ON clinic.room FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: service service_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER service_touch BEFORE UPDATE ON clinic.service FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: service_version service_version_append_only; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER service_version_append_only BEFORE DELETE OR UPDATE ON clinic.service_version FOR EACH ROW EXECUTE FUNCTION clinic.service_version_append_only();


--
-- Name: sla_check sla_check_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER sla_check_touch BEFORE UPDATE ON clinic.sla_check FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: staff_profiles staff_profiles_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER staff_profiles_touch BEFORE UPDATE ON clinic.staff_profiles FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: treatment_plan treatment_plan_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER treatment_plan_touch BEFORE UPDATE ON clinic.treatment_plan FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: treatment_session treatment_session_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER treatment_session_touch BEFORE UPDATE ON clinic.treatment_session FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: user_account user_account_touch; Type: TRIGGER; Schema: clinic; Owner: -
--

CREATE TRIGGER user_account_touch BEFORE UPDATE ON clinic.user_account FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at();


--
-- Name: account_roster account_roster_clinic_id_account_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_clinic_id_account_id_fkey FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts(clinic_id, id) ON DELETE CASCADE;


--
-- Name: account_roster account_roster_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id) ON DELETE SET NULL (created_by);


--
-- Name: account_roster account_roster_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: account_roster account_roster_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.account_roster
    ADD CONSTRAINT account_roster_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: appointment appointment_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: appointment appointment_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: appointment appointment_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: appointment appointment_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: appointment appointment_room_fk; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.appointment
    ADD CONSTRAINT appointment_room_fk FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room(clinic_id, id);


--
-- Name: audit_log audit_log_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.audit_log
    ADD CONSTRAINT audit_log_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: auth_session auth_session_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: auth_session auth_session_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.auth_session
    ADD CONSTRAINT auth_session_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: catalog_import catalog_import_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.catalog_import
    ADD CONSTRAINT catalog_import_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: channel_identity channel_identity_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: channel_identity channel_identity_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: channel_identity channel_identity_clinic_id_verified_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_identity
    ADD CONSTRAINT channel_identity_clinic_id_verified_by_fkey FOREIGN KEY (clinic_id, verified_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: channel_setting channel_setting_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: channel_setting channel_setting_clinic_id_kill_switch_changed_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_clinic_id_kill_switch_changed_by_fkey FOREIGN KEY (clinic_id, kill_switch_changed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: channel_setting channel_setting_clinic_id_updated_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.channel_setting
    ADD CONSTRAINT channel_setting_clinic_id_updated_by_fkey FOREIGN KEY (clinic_id, updated_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: consent consent_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: consent consent_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: consent consent_clinic_id_recorded_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consent
    ADD CONSTRAINT consent_clinic_id_recorded_by_fkey FOREIGN KEY (clinic_id, recorded_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: consult_note consult_note_clinic_id_approved_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: consult_note consult_note_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: consult_note consult_note_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: consult_note consult_note_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.consult_note
    ADD CONSTRAINT consult_note_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: conversation conversation_account_fk; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_account_fk FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts(clinic_id, id) ON DELETE SET NULL (account_id);


--
-- Name: conversation_assignment conversation_assignment_clinic_id_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_by_fkey FOREIGN KEY (clinic_id, by) REFERENCES clinic.user_account(clinic_id, id) ON DELETE SET NULL (by);


--
-- Name: conversation_assignment conversation_assignment_clinic_id_conversation_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_conversation_id_fkey FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation(clinic_id, id) ON DELETE CASCADE;


--
-- Name: conversation_assignment conversation_assignment_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: conversation_assignment conversation_assignment_clinic_id_previous_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_previous_user_id_fkey FOREIGN KEY (clinic_id, previous_user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE SET NULL (previous_user_id);


--
-- Name: conversation_assignment conversation_assignment_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation_assignment
    ADD CONSTRAINT conversation_assignment_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE SET NULL (user_id);


--
-- Name: conversation conversation_clinic_id_assigned_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_assigned_user_id_fkey FOREIGN KEY (clinic_id, assigned_user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: conversation conversation_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: conversation conversation_clinic_id_identity_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_identity_id_fkey FOREIGN KEY (clinic_id, identity_id) REFERENCES clinic.channel_identity(clinic_id, id);


--
-- Name: conversation conversation_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.conversation
    ADD CONSTRAINT conversation_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: crm_activity crm_activity_clinic_id_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_actor_user_id_fkey FOREIGN KEY (clinic_id, actor_user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: crm_activity crm_activity_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: crm_activity crm_activity_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: crm_activity crm_activity_clinic_id_related_appointment_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_related_appointment_id_fkey FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment(clinic_id, id);


--
-- Name: crm_activity crm_activity_clinic_id_task_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_activity
    ADD CONSTRAINT crm_activity_clinic_id_task_id_fkey FOREIGN KEY (clinic_id, task_id) REFERENCES clinic.crm_task(clinic_id, id);


--
-- Name: crm_rule crm_rule_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_rule
    ADD CONSTRAINT crm_rule_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: crm_task crm_task_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: crm_task crm_task_clinic_id_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_owner_user_id_fkey FOREIGN KEY (clinic_id, owner_user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: crm_task crm_task_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: crm_task crm_task_clinic_id_related_appointment_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_related_appointment_id_fkey FOREIGN KEY (clinic_id, related_appointment_id) REFERENCES clinic.appointment(clinic_id, id);


--
-- Name: crm_task crm_task_clinic_id_related_plan_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.crm_task
    ADD CONSTRAINT crm_task_clinic_id_related_plan_id_fkey FOREIGN KEY (clinic_id, related_plan_id) REFERENCES clinic.treatment_plan(clinic_id, id);


--
-- Name: episode episode_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: episode episode_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.episode
    ADD CONSTRAINT episode_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: finance_notification finance_notification_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: finance_notification finance_notification_clinic_id_invoice_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);


--
-- Name: finance_notification finance_notification_clinic_id_payment_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_notification
    ADD CONSTRAINT finance_notification_clinic_id_payment_id_fkey FOREIGN KEY (clinic_id, payment_id) REFERENCES clinic.payment(clinic_id, id);


--
-- Name: finance_period finance_period_clinic_id_closed_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_closed_by_fkey FOREIGN KEY (clinic_id, closed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: finance_period finance_period_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: finance_period finance_period_clinic_id_paid_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.finance_period
    ADD CONSTRAINT finance_period_clinic_id_paid_by_fkey FOREIGN KEY (clinic_id, paid_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: identity_link_attempt identity_link_attempt_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_attempt
    ADD CONSTRAINT identity_link_attempt_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: identity_link_code identity_link_code_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: identity_link_code identity_link_code_clinic_id_issued_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_issued_by_fkey FOREIGN KEY (clinic_id, issued_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: identity_link_code identity_link_code_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: identity_link_code identity_link_code_clinic_id_used_identity_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.identity_link_code
    ADD CONSTRAINT identity_link_code_clinic_id_used_identity_id_fkey FOREIGN KEY (clinic_id, used_identity_id) REFERENCES clinic.channel_identity(clinic_id, id);


--
-- Name: invoice invoice_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: invoice invoice_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: invoice invoice_clinic_id_order_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_order_id_fkey FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order"(clinic_id, id);


--
-- Name: invoice invoice_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.invoice
    ADD CONSTRAINT invoice_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: media media_clinic_id_consent_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_consent_id_fkey FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent(clinic_id, id);


--
-- Name: media media_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: media media_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: media media_clinic_id_session_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_session_id_fkey FOREIGN KEY (clinic_id, session_id) REFERENCES clinic.treatment_session(clinic_id, id);


--
-- Name: media media_clinic_id_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.media
    ADD CONSTRAINT media_clinic_id_uploaded_by_fkey FOREIGN KEY (clinic_id, uploaded_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: message message_clinic_id_conversation_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_clinic_id_conversation_id_fkey FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation(clinic_id, id);


--
-- Name: message message_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: message message_clinic_id_review_item_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_clinic_id_review_item_id_fkey FOREIGN KEY (clinic_id, review_item_id) REFERENCES clinic.review_item(clinic_id, id);


--
-- Name: message message_clinic_id_sender_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message
    ADD CONSTRAINT message_clinic_id_sender_user_id_fkey FOREIGN KEY (clinic_id, sender_user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: message_template message_template_clinic_id_approved_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message_template
    ADD CONSTRAINT message_template_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: message_template message_template_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.message_template
    ADD CONSTRAINT message_template_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: notification_log notification_log_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_log
    ADD CONSTRAINT notification_log_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: notification_log notification_log_clinic_id_outbox_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_log
    ADD CONSTRAINT notification_log_clinic_id_outbox_id_fkey FOREIGN KEY (clinic_id, outbox_id) REFERENCES clinic.notification_outbox(clinic_id, id) ON DELETE CASCADE;


--
-- Name: notification_outbox notification_outbox_acked_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_acked_by_fkey FOREIGN KEY (clinic_id, acked_by) REFERENCES clinic.user_account(clinic_id, id) ON DELETE SET NULL (acked_by);


--
-- Name: notification_outbox notification_outbox_clinic_id_conversation_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_clinic_id_conversation_id_fkey FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation(clinic_id, id) ON DELETE CASCADE;


--
-- Name: notification_outbox notification_outbox_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: notification_outbox notification_outbox_clinic_id_recipient_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notification_outbox
    ADD CONSTRAINT notification_outbox_clinic_id_recipient_user_id_fkey FOREIGN KEY (clinic_id, recipient_user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: notify_link_code notify_link_code_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_link_code
    ADD CONSTRAINT notify_link_code_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: notify_link_code notify_link_code_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_link_code
    ADD CONSTRAINT notify_link_code_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: notify_preference notify_preference_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_preference
    ADD CONSTRAINT notify_preference_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: notify_preference notify_preference_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_preference
    ADD CONSTRAINT notify_preference_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: notify_setting notify_setting_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.notify_setting
    ADD CONSTRAINT notify_setting_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: on_call_contacts on_call_contacts_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.on_call_contacts
    ADD CONSTRAINT on_call_contacts_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: order order_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: order order_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: order order_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: order order_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: order order_clinic_id_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic."order"
    ADD CONSTRAINT order_clinic_id_reviewed_by_fkey FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: order_item order_item_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: order_item order_item_clinic_id_order_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.order_item
    ADD CONSTRAINT order_item_clinic_id_order_id_fkey FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order"(clinic_id, id) ON DELETE CASCADE;


--
-- Name: patient_app_event patient_app_event_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient_app_event patient_app_event_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: patient_app_event patient_app_event_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_app_event
    ADD CONSTRAINT patient_app_event_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: patient_brief patient_brief_clinic_id_approved_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient_brief patient_brief_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: patient_brief patient_brief_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_brief
    ADD CONSTRAINT patient_brief_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: patient patient_clinic_id_cs_owner_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_cs_owner_id_fkey FOREIGN KEY (clinic_id, cs_owner_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient patient_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient patient_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient
    ADD CONSTRAINT patient_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: patient_clinical_note patient_clinical_note_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: patient_clinical_note patient_clinical_note_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: patient_clinical_note patient_clinical_note_clinic_id_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_clinical_note
    ADD CONSTRAINT patient_clinical_note_clinic_id_reviewed_by_fkey FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient_ownership patient_ownership_clinic_id_cs_owner_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_clinic_id_cs_owner_fkey FOREIGN KEY (clinic_id, cs_owner) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient_ownership patient_ownership_clinic_id_doctor_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_clinic_id_doctor_fkey FOREIGN KEY (clinic_id, doctor) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: patient_ownership patient_ownership_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: patient_ownership patient_ownership_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.patient_ownership
    ADD CONSTRAINT patient_ownership_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id) ON DELETE CASCADE;


--
-- Name: payment payment_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: payment payment_clinic_id_invoice_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);


--
-- Name: payment payment_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: payment payment_clinic_id_received_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.payment
    ADD CONSTRAINT payment_clinic_id_received_by_fkey FOREIGN KEY (clinic_id, received_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: procedure_entry procedure_entry_clinic_id_approved_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_approved_by_fkey FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: procedure_entry procedure_entry_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: procedure_entry procedure_entry_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: procedure_entry procedure_entry_clinic_id_invoice_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_invoice_id_fkey FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice(clinic_id, id);


--
-- Name: procedure_entry procedure_entry_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: procedure_entry procedure_entry_clinic_id_service_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_clinic_id_service_id_fkey FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service(clinic_id, id);


--
-- Name: procedure_entry_person procedure_entry_person_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: procedure_entry_person procedure_entry_person_clinic_id_entry_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_entry_id_fkey FOREIGN KEY (clinic_id, entry_id) REFERENCES clinic.procedure_entry(clinic_id, id);


--
-- Name: procedure_entry_person procedure_entry_person_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry_person
    ADD CONSTRAINT procedure_entry_person_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: procedure_entry procedure_entry_service_id_terms_version_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.procedure_entry
    ADD CONSTRAINT procedure_entry_service_id_terms_version_fkey FOREIGN KEY (service_id, terms_version) REFERENCES clinic.service_version(service_id, version_no);


--
-- Name: product product_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.product
    ADD CONSTRAINT product_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: protocol protocol_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.protocol
    ADD CONSTRAINT protocol_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: push_token push_token_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.push_token
    ADD CONSTRAINT push_token_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: push_token push_token_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.push_token
    ADD CONSTRAINT push_token_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id) ON DELETE CASCADE;


--
-- Name: review_item review_item_clinic_id_conversation_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_clinic_id_conversation_id_fkey FOREIGN KEY (clinic_id, conversation_id) REFERENCES clinic.conversation(clinic_id, id);


--
-- Name: review_item review_item_clinic_id_decided_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_clinic_id_decided_by_fkey FOREIGN KEY (clinic_id, decided_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: review_item review_item_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: review_item review_item_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.review_item
    ADD CONSTRAINT review_item_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: room_block room_block_clinic_id_created_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_created_by_fkey FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: room_block room_block_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: room_block room_block_clinic_id_room_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room_block
    ADD CONSTRAINT room_block_clinic_id_room_id_fkey FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room(clinic_id, id);


--
-- Name: room room_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.room
    ADD CONSTRAINT room_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: service service_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service
    ADD CONSTRAINT service_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: service_version service_version_clinic_id_changed_by_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_changed_by_fkey FOREIGN KEY (clinic_id, changed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: service_version service_version_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: service_version service_version_clinic_id_service_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.service_version
    ADD CONSTRAINT service_version_clinic_id_service_id_fkey FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service(clinic_id, id);


--
-- Name: sla_check sla_check_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.sla_check
    ADD CONSTRAINT sla_check_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: staff_profiles staff_profiles_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: staff_profiles staff_profiles_clinic_id_user_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.staff_profiles
    ADD CONSTRAINT staff_profiles_clinic_id_user_id_fkey FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: treatment_plan treatment_plan_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: treatment_plan treatment_plan_clinic_id_episode_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_episode_id_fkey FOREIGN KEY (clinic_id, episode_id) REFERENCES clinic.episode(clinic_id, id);


--
-- Name: treatment_plan treatment_plan_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: treatment_plan treatment_plan_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_plan
    ADD CONSTRAINT treatment_plan_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: treatment_session treatment_session_clinic_id_doctor_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_doctor_id_fkey FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: treatment_session treatment_session_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: treatment_session treatment_session_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id);


--
-- Name: treatment_session treatment_session_clinic_id_plan_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_clinic_id_plan_id_fkey FOREIGN KEY (clinic_id, plan_id) REFERENCES clinic.treatment_plan(clinic_id, id);


--
-- Name: treatment_session treatment_session_consent_fk; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_consent_fk FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent(clinic_id, id);


--
-- Name: treatment_session treatment_session_created_by_fk; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_created_by_fk FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: treatment_session treatment_session_reviewed_by_fk; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.treatment_session
    ADD CONSTRAINT treatment_session_reviewed_by_fk FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: user_account user_account_clinic_id_fkey; Type: FK CONSTRAINT; Schema: clinic; Owner: -
--

ALTER TABLE ONLY clinic.user_account
    ADD CONSTRAINT user_account_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: SCHEMA clinic; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA clinic TO be_app;


--
-- Name: FUNCTION account_purpose_guard(); Type: ACL; Schema: clinic; Owner: -
--

REVOKE ALL ON FUNCTION clinic.account_purpose_guard() FROM PUBLIC;


--
-- Name: FUNCTION conversation_account_guard(); Type: ACL; Schema: clinic; Owner: -
--

REVOKE ALL ON FUNCTION clinic.conversation_account_guard() FROM PUBLIC;


--
-- Name: FUNCTION ensure_clinic(p_name text, p_slug text, p_timezone text, p_id uuid); Type: ACL; Schema: clinic; Owner: -
--

REVOKE ALL ON FUNCTION clinic.ensure_clinic(p_name text, p_slug text, p_timezone text, p_id uuid) FROM PUBLIC;


--
-- Name: TABLE account_roster; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.account_roster TO be_app;


--
-- Name: TABLE appointment; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.appointment TO be_app;


--
-- Name: TABLE audit_log; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT ON TABLE clinic.audit_log TO be_app;


--
-- Name: SEQUENCE audit_log_id_seq; Type: ACL; Schema: clinic; Owner: -
--

GRANT USAGE ON SEQUENCE clinic.audit_log_id_seq TO be_app;


--
-- Name: TABLE auth_session; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.auth_session TO be_app;


--
-- Name: TABLE catalog_import; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.catalog_import TO be_app;


--
-- Name: TABLE channel_identity; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.channel_identity TO be_app;


--
-- Name: TABLE channel_setting; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.channel_setting TO be_app;


--
-- Name: TABLE clinic; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.clinic TO be_app;


--
-- Name: TABLE consent; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.consent TO be_app;


--
-- Name: TABLE consult_note; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.consult_note TO be_app;


--
-- Name: TABLE conversation; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.conversation TO be_app;


--
-- Name: TABLE conversation_assignment; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.conversation_assignment TO be_app;


--
-- Name: TABLE crm_activity; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_activity TO be_app;


--
-- Name: TABLE crm_rule; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_rule TO be_app;


--
-- Name: TABLE crm_task; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.crm_task TO be_app;


--
-- Name: TABLE episode; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.episode TO be_app;


--
-- Name: TABLE finance_notification; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.finance_notification TO be_app;


--
-- Name: TABLE finance_period; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.finance_period TO be_app;


--
-- Name: TABLE identity_link_attempt; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT ON TABLE clinic.identity_link_attempt TO be_app;


--
-- Name: SEQUENCE identity_link_attempt_id_seq; Type: ACL; Schema: clinic; Owner: -
--

GRANT USAGE ON SEQUENCE clinic.identity_link_attempt_id_seq TO be_app;


--
-- Name: TABLE identity_link_code; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.identity_link_code TO be_app;


--
-- Name: TABLE invoice; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.invoice TO be_app;


--
-- Name: TABLE media; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.media TO be_app;


--
-- Name: TABLE message; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.message TO be_app;


--
-- Name: TABLE message_template; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.message_template TO be_app;


--
-- Name: TABLE notification_log; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.notification_log TO be_app;


--
-- Name: TABLE notification_outbox; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.notification_outbox TO be_app;


--
-- Name: TABLE notify_link_code; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.notify_link_code TO be_app;


--
-- Name: TABLE notify_preference; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.notify_preference TO be_app;


--
-- Name: TABLE notify_setting; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.notify_setting TO be_app;


--
-- Name: TABLE on_call_contacts; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.on_call_contacts TO be_app;


--
-- Name: TABLE "order"; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic."order" TO be_app;


--
-- Name: TABLE order_item; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.order_item TO be_app;


--
-- Name: TABLE patient; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient TO be_app;


--
-- Name: TABLE patient_app_event; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_app_event TO be_app;


--
-- Name: TABLE patient_brief; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_brief TO be_app;


--
-- Name: TABLE patient_clinical_note; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_clinical_note TO be_app;


--
-- Name: TABLE patient_ownership; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.patient_ownership TO be_app;


--
-- Name: TABLE payment; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.payment TO be_app;


--
-- Name: TABLE procedure_entry; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.procedure_entry TO be_app;


--
-- Name: TABLE procedure_entry_person; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.procedure_entry_person TO be_app;


--
-- Name: TABLE product; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.product TO be_app;


--
-- Name: TABLE protocol; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.protocol TO be_app;


--
-- Name: TABLE push_token; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.push_token TO be_app;


--
-- Name: TABLE review_item; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.review_item TO be_app;


--
-- Name: TABLE room; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.room TO be_app;


--
-- Name: TABLE room_block; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.room_block TO be_app;


--
-- Name: TABLE service; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.service TO be_app;


--
-- Name: TABLE service_version; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.service_version TO be_app;


--
-- Name: TABLE sla_check; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.sla_check TO be_app;


--
-- Name: TABLE staff_profiles; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.staff_profiles TO be_app;


--
-- Name: TABLE treatment_plan; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.treatment_plan TO be_app;


--
-- Name: TABLE treatment_session; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.treatment_session TO be_app;


--
-- Name: TABLE user_account; Type: ACL; Schema: clinic; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE clinic.user_account TO be_app;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: clinic; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA clinic GRANT USAGE ON SEQUENCES TO be_app;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: clinic; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA clinic GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO be_app;


--
-- PostgreSQL database dump complete
--

\unrestrict 0YZdW4AhSQ6cibJ9mGlIgCbKN9EOPb4swt0hg3DCjMVQY5dshaYsW2zfIMvgrBo

