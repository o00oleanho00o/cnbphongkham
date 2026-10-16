-- Schema agent_rt of the agent app: sessions, messages, the turn trace, notes, model and plugin settings.
-- Plugin tables (cv_, kb_, sk_) come from each plugin's own SQL files (agent db migrate-plugins).
-- Generated once from the old revisions 0001-0012 (pg_dump -s); edit it only together with a new revision.

CREATE SCHEMA IF NOT EXISTS agent_rt;

CREATE TABLE agent_rt.agent_conversation (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    channel text NOT NULL,
    conversation_id text NOT NULL,
    epoch integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_conversation_epoch CHECK ((epoch >= 0)),
    CONSTRAINT agent_conversation_id_size CHECK (((char_length(conversation_id) >= 1) AND (char_length(conversation_id) <= 500)))
);

CREATE TABLE agent_rt.agent_ingress (
    id bigint NOT NULL,
    tenant_id text NOT NULL,
    agent text NOT NULL,
    channel text NOT NULL,
    external_id text NOT NULL,
    conversation_id text NOT NULL,
    user_id text NOT NULL,
    session_id text NOT NULL,
    text text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    error_kind text,
    reply jsonb,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    delivery text,
    delivery_attempts integer DEFAULT 0 NOT NULL,
    delivered_parts integer DEFAULT 0 NOT NULL,
    delivery_error text,
    delivery_at timestamp with time zone,
    delivery_after timestamp with time zone,
    CONSTRAINT agent_ingress_attempts CHECK ((attempts >= 0)),
    CONSTRAINT agent_ingress_delivery CHECK (((delivery IS NULL) OR (delivery = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'failed'::text, 'skipped'::text])))),
    CONSTRAINT agent_ingress_delivery_error_size CHECK (((delivery_error IS NULL) OR (char_length(delivery_error) <= 1000))),
    CONSTRAINT agent_ingress_external_id_size CHECK (((char_length(external_id) >= 1) AND (char_length(external_id) <= 200))),
    CONSTRAINT agent_ingress_reply_when_done CHECK (((status = 'done'::text) = (reply IS NOT NULL))),
    CONSTRAINT agent_ingress_status CHECK ((status = ANY (ARRAY['queued'::text, 'processing'::text, 'done'::text, 'failed'::text, 'dead'::text]))),
    CONSTRAINT agent_ingress_text_size CHECK (((char_length(text) >= 1) AND (char_length(text) <= 20000)))
);

ALTER TABLE agent_rt.agent_ingress ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME agent_rt.agent_ingress_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE agent_rt.agent_memory (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    target text NOT NULL,
    user_id text DEFAULT ''::text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    version integer NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_memory_content_size CHECK ((char_length(content) <= 20000)),
    CONSTRAINT agent_memory_target CHECK ((target = ANY (ARRAY['agent'::text, 'user'::text]))),
    CONSTRAINT agent_memory_user_only_for_user CHECK (((target = 'agent'::text) = (user_id = ''::text))),
    CONSTRAINT agent_memory_version CHECK ((version >= 1))
);

CREATE TABLE agent_rt.agent_message (
    tenant_id text NOT NULL,
    session_id text NOT NULL,
    seq integer NOT NULL,
    uid uuid NOT NULL,
    message jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_message_seq CHECK ((seq >= 1))
);

CREATE TABLE agent_rt.agent_model_entry (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    label text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    base_url text,
    reasoning text,
    dialect text,
    api_key_enc text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_model_entry_base_url CHECK (((base_url IS NULL) OR ((base_url ~ '^https?://'::text) AND (char_length(base_url) <= 500)))),
    CONSTRAINT agent_model_entry_dialect CHECK (((dialect IS NULL) OR (dialect = ANY (ARRAY['deepseek'::text, 'openai'::text])))),
    CONSTRAINT agent_model_entry_id CHECK ((id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT agent_model_entry_label CHECK (((char_length(label) >= 1) AND (char_length(label) <= 100))),
    CONSTRAINT agent_model_entry_model CHECK (((char_length(model) >= 1) AND (char_length(model) <= 200))),
    CONSTRAINT agent_model_entry_provider CHECK ((provider = ANY (ARRAY['openai-compatible'::text, 'anthropic'::text]))),
    CONSTRAINT agent_model_entry_reasoning CHECK (((reasoning IS NULL) OR (reasoning = ANY (ARRAY['off'::text, 'low'::text, 'medium'::text, 'high'::text]))))
);

CREATE TABLE agent_rt.agent_model_settings (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    provider text,
    model text,
    base_url text,
    reasoning text,
    dialect text,
    api_key_enc text,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    entry_id text,
    CONSTRAINT agent_model_base_url CHECK (((base_url IS NULL) OR ((base_url ~ '^https?://'::text) AND (char_length(base_url) <= 500)))),
    CONSTRAINT agent_model_dialect CHECK (((dialect IS NULL) OR (dialect = ANY (ARRAY['deepseek'::text, 'openai'::text])))),
    CONSTRAINT agent_model_name_size CHECK (((model IS NULL) OR ((char_length(model) >= 1) AND (char_length(model) <= 200)))),
    CONSTRAINT agent_model_provider CHECK (((provider IS NULL) OR (provider = ANY (ARRAY['openai-compatible'::text, 'anthropic'::text])))),
    CONSTRAINT agent_model_reasoning CHECK (((reasoning IS NULL) OR (reasoning = ANY (ARRAY['off'::text, 'low'::text, 'medium'::text, 'high'::text])))),
    CONSTRAINT agent_model_version CHECK ((version >= 1))
);

CREATE TABLE agent_rt.agent_plugin (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    name text NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    secrets_enc text,
    install jsonb,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_plugin_config_object CHECK ((jsonb_typeof(config) = 'object'::text)),
    CONSTRAINT agent_plugin_config_size CHECK ((pg_column_size(config) <= 65536)),
    CONSTRAINT agent_plugin_error_size CHECK (((last_error IS NULL) OR (char_length(last_error) <= 4000))),
    CONSTRAINT agent_plugin_name CHECK ((name ~ '^[a-z0-9][a-z0-9_-]{0,63}$'::text))
);

CREATE TABLE agent_rt.agent_plugin_migration (
    plugin text NOT NULL,
    version integer NOT NULL,
    name text NOT NULL,
    checksum text NOT NULL,
    table_prefix text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_plugin_migration_prefix CHECK ((table_prefix ~ '^[a-z][a-z0-9]*_$'::text)),
    CONSTRAINT agent_plugin_migration_version CHECK ((version > 0))
);

CREATE TABLE agent_rt.agent_plugin_record (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    plugin text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_plugin_record_key CHECK (((char_length(key) >= 1) AND (char_length(key) <= 300))),
    CONSTRAINT agent_plugin_record_plugin CHECK ((plugin ~ '^[a-z0-9][a-z0-9_-]{0,63}$'::text)),
    CONSTRAINT agent_plugin_record_size CHECK ((pg_column_size(value) <= 262144))
);

CREATE TABLE agent_rt.agent_session (
    tenant_id text NOT NULL,
    session_id text NOT NULL,
    agent text NOT NULL,
    channel text,
    user_id text,
    message_count integer DEFAULT 0 NOT NULL,
    prompt_text text,
    prompt_fingerprint text,
    summary text,
    first_kept integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_session_compaction_pair CHECK (((summary IS NULL) = (first_kept IS NULL))),
    CONSTRAINT agent_session_id_size CHECK (((char_length(session_id) >= 1) AND (char_length(session_id) <= 200))),
    CONSTRAINT agent_session_message_count CHECK ((message_count >= 0)),
    CONSTRAINT agent_session_prompt_pair CHECK (((prompt_text IS NULL) = (prompt_fingerprint IS NULL)))
);

CREATE TABLE agent_rt.agent_turn (
    turn_id uuid NOT NULL,
    tenant_id text NOT NULL,
    session_id text NOT NULL,
    agent text NOT NULL,
    model text NOT NULL,
    channel text,
    user_id text,
    started_at timestamp with time zone NOT NULL,
    duration_ms integer NOT NULL,
    stop text NOT NULL,
    steps integer NOT NULL,
    error_kind text,
    compactions integer NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    cache_read_tokens integer NOT NULL,
    cache_write_tokens integer NOT NULL,
    reasoning_tokens integer NOT NULL,
    CONSTRAINT agent_turn_error_kind CHECK (((stop = 'error'::text) = (error_kind IS NOT NULL))),
    CONSTRAINT agent_turn_stop CHECK ((stop = ANY (ARRAY['completed'::text, 'max_steps'::text, 'deadline'::text, 'budget'::text, 'loop'::text, 'error'::text])))
);

CREATE TABLE agent_rt.agent_turn_event (
    turn_id uuid NOT NULL,
    seq integer NOT NULL,
    kind text NOT NULL,
    step integer NOT NULL,
    name text DEFAULT ''::text NOT NULL,
    duration_ms integer NOT NULL,
    is_error boolean NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT agent_turn_event_kind CHECK ((kind = ANY (ARRAY['model_call'::text, 'tool_call'::text, 'compaction'::text, 'memory_flush'::text, 'repair'::text, 'model_retry'::text, 'guard'::text, 'inbox'::text])))
);

ALTER TABLE ONLY agent_rt.agent_conversation
    ADD CONSTRAINT agent_conversation_pkey PRIMARY KEY (tenant_id, agent, channel, conversation_id);

ALTER TABLE ONLY agent_rt.agent_ingress
    ADD CONSTRAINT agent_ingress_once UNIQUE (tenant_id, agent, channel, external_id);

ALTER TABLE ONLY agent_rt.agent_ingress
    ADD CONSTRAINT agent_ingress_pkey PRIMARY KEY (id);

ALTER TABLE ONLY agent_rt.agent_memory
    ADD CONSTRAINT agent_memory_pkey PRIMARY KEY (tenant_id, agent, target, user_id);

ALTER TABLE ONLY agent_rt.agent_message
    ADD CONSTRAINT agent_message_pkey PRIMARY KEY (tenant_id, session_id, seq);

ALTER TABLE ONLY agent_rt.agent_message
    ADD CONSTRAINT agent_message_uid UNIQUE (uid);

ALTER TABLE ONLY agent_rt.agent_model_entry
    ADD CONSTRAINT agent_model_entry_pkey PRIMARY KEY (tenant_id, agent, id);

ALTER TABLE ONLY agent_rt.agent_model_settings
    ADD CONSTRAINT agent_model_settings_pkey PRIMARY KEY (tenant_id, agent);

ALTER TABLE ONLY agent_rt.agent_plugin_migration
    ADD CONSTRAINT agent_plugin_migration_pkey PRIMARY KEY (plugin, version);

ALTER TABLE ONLY agent_rt.agent_plugin
    ADD CONSTRAINT agent_plugin_pkey PRIMARY KEY (tenant_id, agent, name);

ALTER TABLE ONLY agent_rt.agent_plugin_record
    ADD CONSTRAINT agent_plugin_record_pkey PRIMARY KEY (tenant_id, agent, plugin, key);

ALTER TABLE ONLY agent_rt.agent_session
    ADD CONSTRAINT agent_session_pkey PRIMARY KEY (tenant_id, session_id);

ALTER TABLE ONLY agent_rt.agent_turn_event
    ADD CONSTRAINT agent_turn_event_pkey PRIMARY KEY (turn_id, seq);

ALTER TABLE ONLY agent_rt.agent_turn
    ADD CONSTRAINT agent_turn_pkey PRIMARY KEY (turn_id);

CREATE INDEX agent_ingress_delivery_open ON agent_rt.agent_ingress USING btree (agent, session_id, id) WHERE (delivery = ANY (ARRAY['pending'::text, 'sending'::text]));

CREATE INDEX agent_ingress_open_idx ON agent_rt.agent_ingress USING btree (status, received_at) WHERE (status = ANY (ARRAY['queued'::text, 'processing'::text]));

CREATE INDEX agent_ingress_session_queue_idx ON agent_rt.agent_ingress USING btree (tenant_id, session_id, id) WHERE (status = 'queued'::text);

CREATE INDEX agent_session_recent_idx ON agent_rt.agent_session USING btree (tenant_id, agent, updated_at DESC);

CREATE INDEX agent_turn_session_idx ON agent_rt.agent_turn USING btree (tenant_id, session_id, started_at DESC);

ALTER TABLE ONLY agent_rt.agent_message
    ADD CONSTRAINT agent_message_tenant_id_session_id_fkey FOREIGN KEY (tenant_id, session_id) REFERENCES agent_rt.agent_session(tenant_id, session_id) ON DELETE CASCADE;

ALTER TABLE ONLY agent_rt.agent_turn_event
    ADD CONSTRAINT agent_turn_event_turn_id_fkey FOREIGN KEY (turn_id) REFERENCES agent_rt.agent_turn(turn_id) ON DELETE CASCADE;

-- The runtime role gets its rights here when it exists already; agent db bootstrap-role grants the same later.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_rt_app') THEN
    GRANT USAGE ON SCHEMA agent_rt TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_conversation TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_ingress TO agent_rt_app;
    GRANT SELECT,USAGE ON SEQUENCE agent_rt.agent_ingress_id_seq TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_memory TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_message TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_model_entry TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_model_settings TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_plugin TO agent_rt_app;
    GRANT SELECT ON TABLE agent_rt.agent_plugin_migration TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_plugin_record TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_session TO agent_rt_app;
    GRANT SELECT,INSERT ON TABLE agent_rt.agent_turn TO agent_rt_app;
    GRANT SELECT,INSERT ON TABLE agent_rt.agent_turn_event TO agent_rt_app;
  END IF;
END $$;
