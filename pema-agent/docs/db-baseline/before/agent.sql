--
-- PostgreSQL database dump
--

\restrict x0ftDF1TMVOoPbbcknlhifJF6xSEVd18fe8auNDJewxQEFociVteetXSTmAuFdc

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
-- Name: agent; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA agent;


--
-- Name: touch_updated_at(); Type: FUNCTION; Schema: agent; Owner: -
--

CREATE FUNCTION agent.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accounts; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.accounts (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    label text NOT NULL,
    channel text DEFAULT 'zalo_personal'::text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    agent_id text NOT NULL,
    allowlist_mode text DEFAULT 'all'::text NOT NULL,
    allowlist_user_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    group_require_mention boolean DEFAULT true NOT NULL,
    respond_to_groups boolean DEFAULT true NOT NULL,
    group_passive_listen boolean DEFAULT true NOT NULL,
    auto_react_enabled boolean DEFAULT true NOT NULL,
    auto_react_icon text DEFAULT 'heart'::text NOT NULL,
    typing_indicator_enabled boolean DEFAULT true NOT NULL,
    disabled_tools jsonb DEFAULT '[]'::jsonb NOT NULL,
    auto_accept_friends boolean DEFAULT false NOT NULL,
    auto_accept_friend_delay_minutes integer DEFAULT 1 NOT NULL,
    policy_profile text DEFAULT 'patient_channel'::text NOT NULL,
    bot_token_enc text DEFAULT ''::text NOT NULL,
    credential_enc text DEFAULT ''::text NOT NULL,
    webhook_secret_enc text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    purpose text DEFAULT 'customer'::text NOT NULL,
    send_gap_min_s integer,
    send_gap_max_s integer,
    daily_cap integer,
    CONSTRAINT accounts_allowlist_mode_check CHECK ((allowlist_mode = ANY (ARRAY['all'::text, 'list'::text]))),
    CONSTRAINT accounts_auto_accept_friend_delay_minutes_check CHECK (((auto_accept_friend_delay_minutes >= 0) AND (auto_accept_friend_delay_minutes <= 1440))),
    CONSTRAINT accounts_channel_check CHECK ((channel = ANY (ARRAY['zalo_bot'::text, 'zalo_personal'::text, 'zalo_oa'::text]))),
    CONSTRAINT accounts_id_check CHECK ((id ~ '^[a-z0-9][a-z0-9-]*$'::text)),
    CONSTRAINT accounts_policy_profile_check CHECK ((policy_profile = ANY (ARRAY['staff_assistant'::text, 'patient_channel'::text]))),
    CONSTRAINT accounts_purpose_check CHECK ((purpose = ANY (ARRAY['customer'::text, 'internal'::text]))),
    CONSTRAINT accounts_send_limits_check CHECK ((((send_gap_min_s IS NULL) OR (send_gap_min_s >= 0)) AND ((send_gap_max_s IS NULL) OR (send_gap_max_s >= 0)) AND ((send_gap_min_s IS NULL) OR (send_gap_max_s IS NULL) OR (send_gap_max_s >= send_gap_min_s)) AND ((daily_cap IS NULL) OR (daily_cap >= 0))))
);


--
-- Name: actions_log; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.actions_log (
    id bigint NOT NULL,
    clinic_id uuid NOT NULL,
    care_agent_id uuid NOT NULL,
    action_type text NOT NULL,
    depth text,
    disposition text NOT NULL,
    reviewer_edit_diff jsonb,
    at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT actions_log_depth_check CHECK ((depth = ANY (ARRAY['D1'::text, 'D2'::text, 'D3'::text, 'D4'::text, 'D5'::text]))),
    CONSTRAINT actions_log_disposition_check CHECK ((disposition = ANY (ARRAY['auto_sent'::text, 'reviewed'::text, 'paused'::text])))
);


--
-- Name: actions_log_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.actions_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.actions_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_kb_document; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agent_kb_document (
    clinic_id uuid NOT NULL,
    agent_id text NOT NULL,
    source_id text NOT NULL
);


--
-- Name: agent_mcp_servers; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agent_mcp_servers (
    clinic_id uuid NOT NULL,
    agent_id text NOT NULL,
    server_id text NOT NULL
);


--
-- Name: agents; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agents (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    icon text DEFAULT '🤖'::text NOT NULL,
    name text NOT NULL,
    persona text DEFAULT ''::text NOT NULL,
    model_provider text,
    model_name text,
    max_steps integer,
    reasoning_effort text,
    disabled_tools jsonb DEFAULT '[]'::jsonb NOT NULL,
    context_window integer,
    is_default boolean DEFAULT false NOT NULL,
    policy_profile text DEFAULT 'patient_channel'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agents_context_window_check CHECK ((context_window >= 1000)),
    CONSTRAINT agents_id_check CHECK ((id ~ '^[a-z0-9][a-z0-9-]*$'::text)),
    CONSTRAINT agents_max_steps_check CHECK ((max_steps >= 1)),
    CONSTRAINT agents_model_provider_check CHECK ((model_provider = ANY (ARRAY['openai-compatible'::text, 'anthropic'::text, 'google'::text]))),
    CONSTRAINT agents_policy_profile_check CHECK ((policy_profile = ANY (ARRAY['staff_assistant'::text, 'patient_channel'::text]))),
    CONSTRAINT agents_reasoning_effort_check CHECK ((reasoning_effort = ANY (ARRAY['off'::text, 'low'::text, 'medium'::text, 'high'::text, 'xhigh'::text])))
);


--
-- Name: care_agents; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.care_agents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    profile text DEFAULT 'patient_channel'::text NOT NULL,
    autonomy_levels jsonb DEFAULT '{}'::jsonb NOT NULL,
    autonomy_override jsonb,
    trust_scores jsonb DEFAULT '{}'::jsonb NOT NULL,
    preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    last_tick_at timestamp with time zone,
    paused boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT care_agents_autonomy_levels_check CHECK ((jsonb_typeof(autonomy_levels) = 'object'::text)),
    CONSTRAINT care_agents_autonomy_override_check CHECK (((autonomy_override IS NULL) OR ((jsonb_typeof(autonomy_override) = 'object'::text) AND (autonomy_override ? 'level'::text) AND (autonomy_override ? 'until'::text) AND ((autonomy_override ->> 'level'::text) = ANY (ARRAY['L0'::text, 'L1'::text, 'L2'::text]))))),
    CONSTRAINT care_agents_preferences_check CHECK ((jsonb_typeof(preferences) = 'object'::text)),
    CONSTRAINT care_agents_profile_check CHECK ((profile = ANY (ARRAY['staff_assistant'::text, 'patient_channel'::text]))),
    CONSTRAINT care_agents_trust_scores_check CHECK ((jsonb_typeof(trust_scores) = 'object'::text))
);


--
-- Name: care_memory; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.care_memory (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    care_agent_id uuid NOT NULL,
    fact text NOT NULL,
    source text NOT NULL,
    valid_until timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT care_memory_fact_check CHECK (((length(fact) >= 1) AND (length(fact) <= 500))),
    CONSTRAINT care_memory_source_check CHECK ((source = ANY (ARRAY['patient'::text, 'staff'::text, 'doctor_edit'::text])))
);


--
-- Name: channel_update_seen; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.channel_update_seen (
    clinic_id uuid NOT NULL,
    account_id text NOT NULL,
    update_id text NOT NULL,
    seen_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: contacts; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.contacts (
    clinic_id uuid NOT NULL,
    account_id text NOT NULL,
    user_id text NOT NULL,
    display_name text DEFAULT ''::text NOT NULL,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    message_count integer DEFAULT 0 NOT NULL
);


--
-- Name: conversation_control; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.conversation_control (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    state text DEFAULT 'AUTO'::text NOT NULL,
    since timestamp with time zone DEFAULT now() NOT NULL,
    staff_owner uuid,
    release_note text,
    auto_release_after interval,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT conversation_control_auto_release_after_check CHECK (((auto_release_after IS NULL) OR (auto_release_after > '00:00:00'::interval))),
    CONSTRAINT conversation_control_check CHECK (((state <> 'STAFF'::text) OR (staff_owner IS NOT NULL))),
    CONSTRAINT conversation_control_state_check CHECK ((state = ANY (ARRAY['AUTO'::text, 'HANDOFF_ROUTING'::text, 'STAFF'::text])))
);


--
-- Name: friend_requests; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.friend_requests (
    clinic_id uuid NOT NULL,
    account_id text NOT NULL,
    from_uid text NOT NULL,
    message text DEFAULT ''::text NOT NULL,
    sender_name text,
    avatar_url text,
    received_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: handoff_requests; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.handoff_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    reason text NOT NULL,
    depth text NOT NULL,
    confidence double precision NOT NULL,
    required_skill text,
    urgency text DEFAULT 'normal'::text NOT NULL,
    candidates jsonb DEFAULT '[]'::jsonb NOT NULL,
    current_idx integer DEFAULT 0 NOT NULL,
    current_notified_at timestamp with time zone,
    accepted_by uuid,
    outcome text,
    resolved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT handoff_requests_candidates_check CHECK ((jsonb_typeof(candidates) = 'array'::text)),
    CONSTRAINT handoff_requests_check CHECK (((accepted_by IS NULL) OR (NOT (outcome IS DISTINCT FROM 'accepted'::text)))),
    CONSTRAINT handoff_requests_check1 CHECK (((outcome IS DISTINCT FROM 'accepted'::text) OR (accepted_by IS NOT NULL))),
    CONSTRAINT handoff_requests_confidence_check CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT handoff_requests_current_idx_check CHECK ((current_idx >= 0)),
    CONSTRAINT handoff_requests_depth_check CHECK ((depth = ANY (ARRAY['D1'::text, 'D2'::text, 'D3'::text, 'D4'::text, 'D5'::text]))),
    CONSTRAINT handoff_requests_outcome_check CHECK ((outcome = ANY (ARRAY['accepted'::text, 'exhausted_to_oncall'::text, 'cancelled'::text]))),
    CONSTRAINT handoff_requests_urgency_check CHECK ((urgency = ANY (ARRAY['urgent'::text, 'normal'::text])))
);


--
-- Name: history; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.history (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    account_id text NOT NULL,
    thread_id text NOT NULL,
    role text NOT NULL,
    sender_name text,
    sender_id text,
    content text NOT NULL,
    images jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT history_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])))
);


--
-- Name: history_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.history ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: image_descriptions; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.image_descriptions (
    clinic_id uuid NOT NULL,
    rel_path text NOT NULL,
    description text NOT NULL,
    model text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: job_runs; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.job_runs (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    job_id text NOT NULL,
    turn_id bigint,
    status text NOT NULL,
    detail text DEFAULT ''::text NOT NULL,
    delivered_chars integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    worker_id text,
    heartbeat_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_runs_status_check CHECK ((status = ANY (ARRAY['running'::text, 'ok'::text, 'silent'::text, 'skipped'::text, 'error'::text, 'interrupted'::text])))
);


--
-- Name: job_runs_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.job_runs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.job_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: jobs; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.jobs (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    account_id text NOT NULL,
    thread_id text NOT NULL,
    thread_type integer NOT NULL,
    name text NOT NULL,
    kind text NOT NULL,
    payload text NOT NULL,
    schedule_kind text NOT NULL,
    run_at timestamp with time zone,
    every_minutes integer,
    cron_expr text,
    timezone text DEFAULT ''::text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    next_run_at timestamp with time zone,
    last_run_at timestamp with time zone,
    last_status text,
    last_error text,
    run_count integer DEFAULT 0 NOT NULL,
    max_runs integer,
    delivery_attempts integer DEFAULT 0 NOT NULL,
    created_by text DEFAULT ''::text NOT NULL,
    dedupe_key text,
    patient_id uuid,
    origin text DEFAULT 'agent_tool'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT jobs_check CHECK (((schedule_kind <> 'once'::text) OR (max_runs = 1))),
    CONSTRAINT jobs_kind_check CHECK ((kind = ANY (ARRAY['message'::text, 'agent'::text]))),
    CONSTRAINT jobs_origin_check CHECK ((origin = ANY (ARRAY['agent_tool'::text, 'staff'::text, 'crm_rule'::text, 'system'::text]))),
    CONSTRAINT jobs_schedule_kind_check CHECK ((schedule_kind = ANY (ARRAY['once'::text, 'every'::text, 'cron'::text])))
);


--
-- Name: kb_chunk; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.kb_chunk (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    source_id text NOT NULL,
    ord integer NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    content text NOT NULL,
    folded text NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, folded)) STORED,
    embedding public.vector(1024)
);


--
-- Name: kb_chunk_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.kb_chunk ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.kb_chunk_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: kb_document; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.kb_document (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    name text NOT NULL,
    kind text NOT NULL,
    format text DEFAULT ''::text NOT NULL,
    storage_key text DEFAULT ''::text NOT NULL,
    raw_text text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'cho_xu_ly'::text NOT NULL,
    error text DEFAULT ''::text NOT NULL,
    chunk_count integer DEFAULT 0 NOT NULL,
    byte_size integer DEFAULT 0 NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    approved_by_clinical_owner boolean DEFAULT false NOT NULL,
    approved_by uuid,
    approved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT kb_document_kind_check CHECK ((kind = ANY (ARRAY['file'::text, 'text'::text]))),
    CONSTRAINT kb_document_status_check CHECK ((status = ANY (ARRAY['cho_xu_ly'::text, 'dang_xu_ly'::text, 'san_sang'::text, 'hong'::text]))),
    CONSTRAINT kb_document_tags_count CHECK ((cardinality(tags) <= 10))
);


--
-- Name: mcp_servers; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.mcp_servers (
    clinic_id uuid NOT NULL,
    id text NOT NULL,
    name text NOT NULL,
    url text NOT NULL,
    headers_enc text DEFAULT ''::text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    status text DEFAULT 'cho_ket_noi'::text NOT NULL,
    error text DEFAULT ''::text NOT NULL,
    tools_snapshot jsonb DEFAULT '[]'::jsonb NOT NULL,
    fingerprint text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mcp_servers_status_check CHECK ((status = ANY (ARRAY['cho_ket_noi'::text, 'da_ket_noi'::text, 'loi'::text, 'can_duyet_lai'::text])))
);


--
-- Name: memories; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.memories (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    account_id text NOT NULL,
    subject_id text NOT NULL,
    content text NOT NULL,
    learned_in_thread_id text NOT NULL,
    learned_in_group boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memories_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.memories ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.memories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: paused_reminders; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.paused_reminders (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    care_agent_id uuid NOT NULL,
    patient_id uuid NOT NULL,
    patient_ref text NOT NULL,
    event_kind text NOT NULL,
    rule text,
    due_at timestamp with time zone NOT NULL,
    dedupe_key text NOT NULL,
    prepared_text text,
    owner_user_id uuid,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'paused'::text NOT NULL,
    resolution text,
    paused_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT paused_reminders_check CHECK (((status = 'paused'::text) = (resolved_at IS NULL))),
    CONSTRAINT paused_reminders_dedupe_key_check CHECK (((length(dedupe_key) >= 1) AND (length(dedupe_key) <= 300))),
    CONSTRAINT paused_reminders_event_kind_check CHECK ((event_kind = ANY (ARRAY['milestone_due'::text, 'visit_overdue'::text, 'no_show'::text, 'dormant'::text, 'birthday'::text, 'session_completed'::text]))),
    CONSTRAINT paused_reminders_patient_ref_check CHECK (((length(patient_ref) >= 1) AND (length(patient_ref) <= 64))),
    CONSTRAINT paused_reminders_payload_check CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT paused_reminders_status_check CHECK ((status = ANY (ARRAY['paused'::text, 'resumed'::text, 'dropped'::text, 'sent_by_staff'::text])))
);


--
-- Name: proactive_send_counters; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.proactive_send_counters (
    clinic_id uuid NOT NULL,
    scope_key text NOT NULL,
    day_key text NOT NULL,
    count integer DEFAULT 0 NOT NULL,
    notice_sent boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT proactive_send_counters_count_check CHECK ((count >= 0))
);


--
-- Name: runtime_settings; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.runtime_settings (
    clinic_id uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: skills; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.skills (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    name text NOT NULL,
    instruction text NOT NULL,
    classifier_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled_for_profiles text[] DEFAULT '{}'::text[] NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT skills_classifier_config_check CHECK ((jsonb_typeof(classifier_config) = 'object'::text)),
    CONSTRAINT skills_enabled_for_profiles_check CHECK ((enabled_for_profiles <@ ARRAY['staff_assistant'::text, 'patient_channel'::text])),
    CONSTRAINT skills_name_check CHECK ((name ~ '^[a-z0-9][a-z0-9_-]*$'::text))
);


--
-- Name: tasks; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id uuid NOT NULL,
    parent_id uuid,
    care_agent_id uuid NOT NULL,
    agent_id text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    result jsonb,
    tokens integer DEFAULT 0 NOT NULL,
    cost numeric(12,6) DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    deadline_at timestamp with time zone,
    error text,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tasks_cost_check CHECK ((cost >= (0)::numeric)),
    CONSTRAINT tasks_input_check CHECK ((jsonb_typeof(input) = 'object'::text)),
    CONSTRAINT tasks_result_check CHECK (((result IS NULL) OR (jsonb_typeof(result) = 'object'::text))),
    CONSTRAINT tasks_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'done'::text, 'failed'::text, 'needs_human'::text, 'cancelled'::text]))),
    CONSTRAINT tasks_tokens_check CHECK ((tokens >= 0))
);


--
-- Name: threads; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.threads (
    clinic_id uuid NOT NULL,
    account_id text NOT NULL,
    thread_id text NOT NULL,
    thread_type integer NOT NULL,
    display_name text DEFAULT ''::text NOT NULL,
    bot_enabled boolean DEFAULT true NOT NULL,
    message_count integer DEFAULT 0 NOT NULL,
    last_message_at timestamp with time zone,
    last_sender_name text,
    summary text DEFAULT ''::text NOT NULL,
    summary_covers_to_message_id bigint DEFAULT 0 NOT NULL,
    context_epoch integer DEFAULT 0 NOT NULL
);


--
-- Name: usage; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.usage (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    account_id text NOT NULL,
    thread_id text NOT NULL,
    source text DEFAULT 'message'::text NOT NULL,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    steps integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT usage_source_check CHECK ((source = ANY (ARRAY['message'::text, 'schedule'::text])))
);


--
-- Name: usage_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.usage ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.usage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: usage_steps; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.usage_steps (
    clinic_id uuid NOT NULL,
    id bigint NOT NULL,
    turn_id bigint NOT NULL,
    step_number integer NOT NULL,
    attempt integer DEFAULT 1 NOT NULL,
    text text DEFAULT ''::text NOT NULL,
    reasoning text DEFAULT ''::text NOT NULL,
    tool_calls jsonb DEFAULT '[]'::jsonb NOT NULL,
    tool_results jsonb DEFAULT '[]'::jsonb NOT NULL,
    tool_errors jsonb DEFAULT '[]'::jsonb NOT NULL,
    finish_reason text DEFAULT ''::text NOT NULL,
    warnings jsonb DEFAULT '[]'::jsonb NOT NULL,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: usage_steps_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

ALTER TABLE agent.usage_steps ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent.usage_steps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (clinic_id, id);


--
-- Name: actions_log actions_log_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.actions_log
    ADD CONSTRAINT actions_log_pkey PRIMARY KEY (id);


--
-- Name: agent_kb_document agent_kb_document_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_kb_document
    ADD CONSTRAINT agent_kb_document_pkey PRIMARY KEY (clinic_id, agent_id, source_id);


--
-- Name: agent_mcp_servers agent_mcp_servers_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_mcp_servers
    ADD CONSTRAINT agent_mcp_servers_pkey PRIMARY KEY (clinic_id, agent_id, server_id);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (clinic_id, id);


--
-- Name: care_agents care_agents_clinic_id_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_agents
    ADD CONSTRAINT care_agents_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: care_agents care_agents_patient_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_agents
    ADD CONSTRAINT care_agents_patient_id_key UNIQUE (patient_id);


--
-- Name: care_agents care_agents_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_agents
    ADD CONSTRAINT care_agents_pkey PRIMARY KEY (id);


--
-- Name: care_memory care_memory_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_memory
    ADD CONSTRAINT care_memory_pkey PRIMARY KEY (id);


--
-- Name: channel_update_seen channel_update_seen_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.channel_update_seen
    ADD CONSTRAINT channel_update_seen_pkey PRIMARY KEY (clinic_id, account_id, update_id);


--
-- Name: contacts contacts_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (clinic_id, account_id, user_id);


--
-- Name: conversation_control conversation_control_patient_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.conversation_control
    ADD CONSTRAINT conversation_control_patient_id_key UNIQUE (patient_id);


--
-- Name: conversation_control conversation_control_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.conversation_control
    ADD CONSTRAINT conversation_control_pkey PRIMARY KEY (id);


--
-- Name: friend_requests friend_requests_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.friend_requests
    ADD CONSTRAINT friend_requests_pkey PRIMARY KEY (clinic_id, account_id, from_uid);


--
-- Name: handoff_requests handoff_requests_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.handoff_requests
    ADD CONSTRAINT handoff_requests_pkey PRIMARY KEY (id);


--
-- Name: history history_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.history
    ADD CONSTRAINT history_pkey PRIMARY KEY (id);


--
-- Name: image_descriptions image_descriptions_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.image_descriptions
    ADD CONSTRAINT image_descriptions_pkey PRIMARY KEY (clinic_id, rel_path);


--
-- Name: job_runs job_runs_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.job_runs
    ADD CONSTRAINT job_runs_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (clinic_id, id);


--
-- Name: kb_chunk kb_chunk_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.kb_chunk
    ADD CONSTRAINT kb_chunk_pkey PRIMARY KEY (id);


--
-- Name: kb_document kb_document_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.kb_document
    ADD CONSTRAINT kb_document_pkey PRIMARY KEY (clinic_id, id);


--
-- Name: mcp_servers mcp_servers_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.mcp_servers
    ADD CONSTRAINT mcp_servers_pkey PRIMARY KEY (clinic_id, id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (id);


--
-- Name: paused_reminders paused_reminders_care_agent_id_dedupe_key_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.paused_reminders
    ADD CONSTRAINT paused_reminders_care_agent_id_dedupe_key_key UNIQUE (care_agent_id, dedupe_key);


--
-- Name: paused_reminders paused_reminders_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.paused_reminders
    ADD CONSTRAINT paused_reminders_pkey PRIMARY KEY (id);


--
-- Name: proactive_send_counters proactive_send_counters_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.proactive_send_counters
    ADD CONSTRAINT proactive_send_counters_pkey PRIMARY KEY (clinic_id, scope_key, day_key);


--
-- Name: runtime_settings runtime_settings_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.runtime_settings
    ADD CONSTRAINT runtime_settings_pkey PRIMARY KEY (clinic_id, key);


--
-- Name: skills skills_clinic_id_name_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skills
    ADD CONSTRAINT skills_clinic_id_name_key UNIQUE (clinic_id, name);


--
-- Name: skills skills_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skills
    ADD CONSTRAINT skills_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_clinic_id_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.tasks
    ADD CONSTRAINT tasks_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: threads threads_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.threads
    ADD CONSTRAINT threads_pkey PRIMARY KEY (clinic_id, account_id, thread_id);


--
-- Name: usage usage_clinic_id_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage
    ADD CONSTRAINT usage_clinic_id_id_key UNIQUE (clinic_id, id);


--
-- Name: usage usage_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage
    ADD CONSTRAINT usage_pkey PRIMARY KEY (id);


--
-- Name: usage_steps usage_steps_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage_steps
    ADD CONSTRAINT usage_steps_pkey PRIMARY KEY (id);


--
-- Name: actions_log_agent_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX actions_log_agent_idx ON agent.actions_log USING btree (care_agent_id, at DESC);


--
-- Name: agents_one_default_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE UNIQUE INDEX agents_one_default_idx ON agent.agents USING btree (clinic_id) WHERE is_default;


--
-- Name: care_memory_agent_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX care_memory_agent_idx ON agent.care_memory USING btree (care_agent_id, valid_until);


--
-- Name: channel_update_seen_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX channel_update_seen_age_idx ON agent.channel_update_seen USING btree (seen_at);


--
-- Name: handoff_requests_one_open_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE UNIQUE INDEX handoff_requests_one_open_idx ON agent.handoff_requests USING btree (patient_id) WHERE (outcome IS NULL);


--
-- Name: handoff_requests_patient_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX handoff_requests_patient_idx ON agent.handoff_requests USING btree (patient_id, created_at DESC);


--
-- Name: history_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX history_age_idx ON agent.history USING btree (clinic_id, created_at);


--
-- Name: history_thread_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX history_thread_idx ON agent.history USING btree (clinic_id, account_id, thread_id, id);


--
-- Name: image_descriptions_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX image_descriptions_age_idx ON agent.image_descriptions USING btree (clinic_id, created_at);


--
-- Name: job_runs_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX job_runs_age_idx ON agent.job_runs USING btree (clinic_id, started_at);


--
-- Name: job_runs_job_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX job_runs_job_idx ON agent.job_runs USING btree (clinic_id, job_id, id DESC);


--
-- Name: job_runs_running_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX job_runs_running_idx ON agent.job_runs USING btree (clinic_id, heartbeat_at) WHERE (status = 'running'::text);


--
-- Name: jobs_dedupe_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE UNIQUE INDEX jobs_dedupe_idx ON agent.jobs USING btree (clinic_id, dedupe_key) WHERE (dedupe_key IS NOT NULL);


--
-- Name: jobs_due_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX jobs_due_idx ON agent.jobs USING btree (clinic_id, enabled, next_run_at);


--
-- Name: jobs_thread_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX jobs_thread_idx ON agent.jobs USING btree (clinic_id, account_id, thread_id);


--
-- Name: kb_chunk_embedding_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX kb_chunk_embedding_idx ON agent.kb_chunk USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: kb_chunk_source_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX kb_chunk_source_idx ON agent.kb_chunk USING btree (clinic_id, source_id);


--
-- Name: kb_chunk_tsv_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX kb_chunk_tsv_idx ON agent.kb_chunk USING gin (tsv);


--
-- Name: kb_document_tags_gin; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX kb_document_tags_gin ON agent.kb_document USING gin (tags);


--
-- Name: memories_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX memories_age_idx ON agent.memories USING btree (clinic_id, created_at);


--
-- Name: memories_subject_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX memories_subject_idx ON agent.memories USING btree (clinic_id, account_id, subject_id, id);


--
-- Name: paused_reminders_agent_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX paused_reminders_agent_idx ON agent.paused_reminders USING btree (care_agent_id, due_at) WHERE (status = 'paused'::text);


--
-- Name: paused_reminders_owner_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX paused_reminders_owner_idx ON agent.paused_reminders USING btree (owner_user_id, due_at) WHERE (status = 'paused'::text);


--
-- Name: tasks_agent_status_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX tasks_agent_status_idx ON agent.tasks USING btree (care_agent_id, status);


--
-- Name: tasks_parent_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX tasks_parent_idx ON agent.tasks USING btree (parent_id) WHERE (parent_id IS NOT NULL);


--
-- Name: threads_recent_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX threads_recent_idx ON agent.threads USING btree (clinic_id, last_message_at DESC);


--
-- Name: usage_account_created_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX usage_account_created_idx ON agent.usage USING btree (clinic_id, account_id, created_at);


--
-- Name: usage_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX usage_age_idx ON agent.usage USING btree (clinic_id, created_at);


--
-- Name: usage_steps_clinic_age_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX usage_steps_clinic_age_idx ON agent.usage_steps USING btree (clinic_id, created_at);


--
-- Name: usage_steps_created_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX usage_steps_created_idx ON agent.usage_steps USING btree (created_at);


--
-- Name: usage_steps_turn_idx; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX usage_steps_turn_idx ON agent.usage_steps USING btree (clinic_id, turn_id, step_number);


--
-- Name: accounts account_purpose_guard; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER account_purpose_guard BEFORE UPDATE OF purpose ON agent.accounts FOR EACH ROW WHEN (((new.purpose = 'internal'::text) AND (old.purpose IS DISTINCT FROM new.purpose))) EXECUTE FUNCTION clinic.account_purpose_guard();


--
-- Name: accounts accounts_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER accounts_touch BEFORE UPDATE ON agent.accounts FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: actions_log actions_log_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER actions_log_touch BEFORE UPDATE ON agent.actions_log FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: agents agents_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER agents_touch BEFORE UPDATE ON agent.agents FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: care_agents care_agents_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER care_agents_touch BEFORE UPDATE ON agent.care_agents FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: care_memory care_memory_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER care_memory_touch BEFORE UPDATE ON agent.care_memory FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: conversation_control conversation_control_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER conversation_control_touch BEFORE UPDATE ON agent.conversation_control FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: handoff_requests handoff_requests_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER handoff_requests_touch BEFORE UPDATE ON agent.handoff_requests FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: jobs jobs_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER jobs_touch BEFORE UPDATE ON agent.jobs FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: kb_document kb_document_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER kb_document_touch BEFORE UPDATE ON agent.kb_document FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: mcp_servers mcp_servers_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER mcp_servers_touch BEFORE UPDATE ON agent.mcp_servers FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: paused_reminders paused_reminders_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER paused_reminders_touch BEFORE UPDATE ON agent.paused_reminders FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: skills skills_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER skills_touch BEFORE UPDATE ON agent.skills FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: tasks tasks_touch; Type: TRIGGER; Schema: agent; Owner: -
--

CREATE TRIGGER tasks_touch BEFORE UPDATE ON agent.tasks FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at();


--
-- Name: accounts accounts_clinic_id_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.accounts
    ADD CONSTRAINT accounts_clinic_id_agent_id_fkey FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents(clinic_id, id);


--
-- Name: accounts accounts_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.accounts
    ADD CONSTRAINT accounts_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: actions_log actions_log_clinic_id_care_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.actions_log
    ADD CONSTRAINT actions_log_clinic_id_care_agent_id_fkey FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: actions_log actions_log_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.actions_log
    ADD CONSTRAINT actions_log_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: agent_kb_document agent_kb_document_clinic_id_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_kb_document
    ADD CONSTRAINT agent_kb_document_clinic_id_agent_id_fkey FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: agent_kb_document agent_kb_document_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_kb_document
    ADD CONSTRAINT agent_kb_document_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: agent_kb_document agent_kb_document_clinic_id_source_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_kb_document
    ADD CONSTRAINT agent_kb_document_clinic_id_source_id_fkey FOREIGN KEY (clinic_id, source_id) REFERENCES agent.kb_document(clinic_id, id) ON DELETE CASCADE;


--
-- Name: agent_mcp_servers agent_mcp_servers_clinic_id_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_mcp_servers
    ADD CONSTRAINT agent_mcp_servers_clinic_id_agent_id_fkey FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: agent_mcp_servers agent_mcp_servers_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_mcp_servers
    ADD CONSTRAINT agent_mcp_servers_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: agent_mcp_servers agent_mcp_servers_clinic_id_server_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_mcp_servers
    ADD CONSTRAINT agent_mcp_servers_clinic_id_server_id_fkey FOREIGN KEY (clinic_id, server_id) REFERENCES agent.mcp_servers(clinic_id, id) ON DELETE CASCADE;


--
-- Name: agents agents_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agents
    ADD CONSTRAINT agents_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: care_agents care_agents_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_agents
    ADD CONSTRAINT care_agents_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: care_agents care_agents_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_agents
    ADD CONSTRAINT care_agents_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id) ON DELETE CASCADE;


--
-- Name: care_memory care_memory_clinic_id_care_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_memory
    ADD CONSTRAINT care_memory_clinic_id_care_agent_id_fkey FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: care_memory care_memory_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.care_memory
    ADD CONSTRAINT care_memory_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: channel_update_seen channel_update_seen_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.channel_update_seen
    ADD CONSTRAINT channel_update_seen_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: contacts contacts_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.contacts
    ADD CONSTRAINT contacts_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: conversation_control conversation_control_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.conversation_control
    ADD CONSTRAINT conversation_control_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: conversation_control conversation_control_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.conversation_control
    ADD CONSTRAINT conversation_control_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id) ON DELETE CASCADE;


--
-- Name: conversation_control conversation_control_clinic_id_staff_owner_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.conversation_control
    ADD CONSTRAINT conversation_control_clinic_id_staff_owner_fkey FOREIGN KEY (clinic_id, staff_owner) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: friend_requests friend_requests_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.friend_requests
    ADD CONSTRAINT friend_requests_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: handoff_requests handoff_requests_clinic_id_accepted_by_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.handoff_requests
    ADD CONSTRAINT handoff_requests_clinic_id_accepted_by_fkey FOREIGN KEY (clinic_id, accepted_by) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: handoff_requests handoff_requests_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.handoff_requests
    ADD CONSTRAINT handoff_requests_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: handoff_requests handoff_requests_clinic_id_patient_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.handoff_requests
    ADD CONSTRAINT handoff_requests_clinic_id_patient_id_fkey FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient(clinic_id, id) ON DELETE CASCADE;


--
-- Name: history history_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.history
    ADD CONSTRAINT history_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: image_descriptions image_descriptions_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.image_descriptions
    ADD CONSTRAINT image_descriptions_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: job_runs job_runs_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.job_runs
    ADD CONSTRAINT job_runs_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: job_runs job_runs_clinic_id_job_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.job_runs
    ADD CONSTRAINT job_runs_clinic_id_job_id_fkey FOREIGN KEY (clinic_id, job_id) REFERENCES agent.jobs(clinic_id, id) ON DELETE CASCADE;


--
-- Name: jobs jobs_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.jobs
    ADD CONSTRAINT jobs_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: kb_chunk kb_chunk_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.kb_chunk
    ADD CONSTRAINT kb_chunk_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: kb_chunk kb_chunk_clinic_id_source_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.kb_chunk
    ADD CONSTRAINT kb_chunk_clinic_id_source_id_fkey FOREIGN KEY (clinic_id, source_id) REFERENCES agent.kb_document(clinic_id, id) ON DELETE CASCADE;


--
-- Name: kb_document kb_document_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.kb_document
    ADD CONSTRAINT kb_document_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: mcp_servers mcp_servers_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.mcp_servers
    ADD CONSTRAINT mcp_servers_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: memories memories_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.memories
    ADD CONSTRAINT memories_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: paused_reminders paused_reminders_clinic_id_care_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.paused_reminders
    ADD CONSTRAINT paused_reminders_clinic_id_care_agent_id_fkey FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: paused_reminders paused_reminders_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.paused_reminders
    ADD CONSTRAINT paused_reminders_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: paused_reminders paused_reminders_clinic_id_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.paused_reminders
    ADD CONSTRAINT paused_reminders_clinic_id_owner_user_id_fkey FOREIGN KEY (clinic_id, owner_user_id) REFERENCES clinic.user_account(clinic_id, id);


--
-- Name: proactive_send_counters proactive_send_counters_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.proactive_send_counters
    ADD CONSTRAINT proactive_send_counters_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: runtime_settings runtime_settings_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.runtime_settings
    ADD CONSTRAINT runtime_settings_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: skills skills_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skills
    ADD CONSTRAINT skills_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: tasks tasks_clinic_id_care_agent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.tasks
    ADD CONSTRAINT tasks_clinic_id_care_agent_id_fkey FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents(clinic_id, id) ON DELETE CASCADE;


--
-- Name: tasks tasks_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.tasks
    ADD CONSTRAINT tasks_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: tasks tasks_clinic_id_parent_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.tasks
    ADD CONSTRAINT tasks_clinic_id_parent_id_fkey FOREIGN KEY (clinic_id, parent_id) REFERENCES agent.tasks(clinic_id, id) ON DELETE CASCADE;


--
-- Name: threads threads_clinic_id_account_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.threads
    ADD CONSTRAINT threads_clinic_id_account_id_fkey FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts(clinic_id, id) ON DELETE CASCADE;


--
-- Name: threads threads_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.threads
    ADD CONSTRAINT threads_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: usage usage_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage
    ADD CONSTRAINT usage_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: usage_steps usage_steps_clinic_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage_steps
    ADD CONSTRAINT usage_steps_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES clinic.clinic(id);


--
-- Name: usage_steps usage_steps_clinic_id_turn_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.usage_steps
    ADD CONSTRAINT usage_steps_clinic_id_turn_id_fkey FOREIGN KEY (clinic_id, turn_id) REFERENCES agent.usage(clinic_id, id) ON DELETE CASCADE;


--
-- Name: SCHEMA agent; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA agent TO be_app;
GRANT USAGE ON SCHEMA agent TO agent_worker;


--
-- Name: TABLE accounts; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.accounts TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.accounts TO agent_worker;


--
-- Name: TABLE actions_log; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.actions_log TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.actions_log TO agent_worker;


--
-- Name: SEQUENCE actions_log_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.actions_log_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.actions_log_id_seq TO agent_worker;


--
-- Name: TABLE agent_kb_document; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agent_kb_document TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agent_kb_document TO agent_worker;


--
-- Name: TABLE agent_mcp_servers; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agent_mcp_servers TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agent_mcp_servers TO agent_worker;


--
-- Name: TABLE agents; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agents TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.agents TO agent_worker;


--
-- Name: TABLE care_agents; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.care_agents TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.care_agents TO agent_worker;


--
-- Name: TABLE care_memory; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.care_memory TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.care_memory TO agent_worker;


--
-- Name: TABLE channel_update_seen; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.channel_update_seen TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.channel_update_seen TO agent_worker;


--
-- Name: TABLE contacts; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.contacts TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.contacts TO agent_worker;


--
-- Name: TABLE conversation_control; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.conversation_control TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.conversation_control TO agent_worker;


--
-- Name: TABLE friend_requests; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.friend_requests TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.friend_requests TO agent_worker;


--
-- Name: TABLE handoff_requests; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.handoff_requests TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.handoff_requests TO agent_worker;


--
-- Name: TABLE history; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.history TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.history TO agent_worker;


--
-- Name: SEQUENCE history_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.history_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.history_id_seq TO agent_worker;


--
-- Name: TABLE image_descriptions; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.image_descriptions TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.image_descriptions TO agent_worker;


--
-- Name: TABLE job_runs; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.job_runs TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.job_runs TO agent_worker;


--
-- Name: SEQUENCE job_runs_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.job_runs_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.job_runs_id_seq TO agent_worker;


--
-- Name: TABLE jobs; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.jobs TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.jobs TO agent_worker;


--
-- Name: TABLE kb_chunk; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.kb_chunk TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.kb_chunk TO agent_worker;


--
-- Name: SEQUENCE kb_chunk_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.kb_chunk_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.kb_chunk_id_seq TO agent_worker;


--
-- Name: TABLE kb_document; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.kb_document TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.kb_document TO agent_worker;


--
-- Name: TABLE mcp_servers; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.mcp_servers TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.mcp_servers TO agent_worker;


--
-- Name: TABLE memories; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.memories TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.memories TO agent_worker;


--
-- Name: SEQUENCE memories_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.memories_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.memories_id_seq TO agent_worker;


--
-- Name: TABLE paused_reminders; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.paused_reminders TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.paused_reminders TO agent_worker;


--
-- Name: TABLE proactive_send_counters; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.proactive_send_counters TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.proactive_send_counters TO agent_worker;


--
-- Name: TABLE runtime_settings; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.runtime_settings TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.runtime_settings TO agent_worker;


--
-- Name: TABLE skills; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.skills TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.skills TO agent_worker;


--
-- Name: TABLE tasks; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.tasks TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.tasks TO agent_worker;


--
-- Name: TABLE threads; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.threads TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.threads TO agent_worker;


--
-- Name: TABLE usage; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.usage TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.usage TO agent_worker;


--
-- Name: SEQUENCE usage_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.usage_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.usage_id_seq TO agent_worker;


--
-- Name: TABLE usage_steps; Type: ACL; Schema: agent; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.usage_steps TO be_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent.usage_steps TO agent_worker;


--
-- Name: SEQUENCE usage_steps_id_seq; Type: ACL; Schema: agent; Owner: -
--

GRANT USAGE ON SEQUENCE agent.usage_steps_id_seq TO be_app;
GRANT USAGE ON SEQUENCE agent.usage_steps_id_seq TO agent_worker;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: agent; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA agent GRANT USAGE ON SEQUENCES TO be_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA agent GRANT USAGE ON SEQUENCES TO agent_worker;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: agent; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA agent GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO be_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA agent GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO agent_worker;


--
-- PostgreSQL database dump complete
--

\unrestrict x0ftDF1TMVOoPbbcknlhifJF6xSEVd18fe8auNDJewxQEFociVteetXSTmAuFdc

