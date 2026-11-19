-- What an admin changed about the agent on the dashboard (or ``agent settings``): one row per (tenant, agent).
-- NULL (and an empty map) means "the profile decides"; the tools map holds only the tools an admin switched on
-- or off by hand.
CREATE TABLE agent_rt.agent_settings (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    timezone text,
    failure_reply text,
    variables jsonb DEFAULT '{}'::jsonb NOT NULL,
    persona text,
    rules text,
    memory_enabled boolean,
    memory_agent_chars integer,
    memory_user_chars integer,
    tools jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by text,
    CONSTRAINT agent_settings_pkey PRIMARY KEY (tenant_id, agent),
    CONSTRAINT agent_settings_timezone CHECK (((timezone IS NULL) OR ((char_length(timezone) >= 1) AND (char_length(timezone) <= 64)))),
    CONSTRAINT agent_settings_failure_reply CHECK (((failure_reply IS NULL) OR (char_length(failure_reply) <= 1000))),
    CONSTRAINT agent_settings_persona CHECK (((persona IS NULL) OR (char_length(persona) <= 20000))),
    CONSTRAINT agent_settings_rules CHECK (((rules IS NULL) OR (char_length(rules) <= 20000))),
    CONSTRAINT agent_settings_memory_agent CHECK (((memory_agent_chars IS NULL) OR ((memory_agent_chars >= 100) AND (memory_agent_chars <= 20000)))),
    CONSTRAINT agent_settings_memory_user CHECK (((memory_user_chars IS NULL) OR ((memory_user_chars >= 100) AND (memory_user_chars <= 20000)))),
    CONSTRAINT agent_settings_variables CHECK ((jsonb_typeof(variables) = 'object'::text)),
    CONSTRAINT agent_settings_tools CHECK ((jsonb_typeof(tools) = 'object'::text)),
    CONSTRAINT agent_settings_version CHECK ((version >= 1))
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_rt_app') THEN
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_settings TO agent_rt_app;
  END IF;
END $$;
