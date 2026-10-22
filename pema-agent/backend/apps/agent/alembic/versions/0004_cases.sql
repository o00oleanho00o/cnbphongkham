-- Cases: goals the agent works on across many wake-ups (docs/DESIGN-case-loop.md, docs/PLAN-case-loop.md).
-- One row per case with its pointer, typed state and counts; one log row per thing the engine did, so what a
-- loop did and why can always be read back. The kinds of case come from plugins; the core knows none.
CREATE TABLE agent_rt.agent_case (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL,
    agent text NOT NULL,
    plugin text NOT NULL,
    kind text NOT NULL,
    key text NOT NULL,
    channel text NOT NULL,
    conversation_id text NOT NULL,
    user_id text NOT NULL,
    session_id text NOT NULL,
    goal text NOT NULL,
    status text NOT NULL,
    node text NOT NULL,
    state jsonb DEFAULT '{}'::jsonb NOT NULL,
    wait_for text,
    wake_at timestamp with time zone,
    deadline timestamp with time zone NOT NULL,
    turns integer DEFAULT 0 NOT NULL,
    proactive_sent integer DEFAULT 0 NOT NULL,
    end_reason text,
    version integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_at timestamp with time zone,
    CONSTRAINT agent_case_status CHECK ((status = ANY (ARRAY['open'::text, 'waiting'::text, 'needs_human'::text, 'done'::text, 'stopped'::text]))),
    CONSTRAINT agent_case_wait_for CHECK (((wait_for IS NULL) OR (wait_for = ANY (ARRAY['customer'::text, 'clock'::text, 'event'::text])))),
    CONSTRAINT agent_case_ended CHECK (((status = ANY (ARRAY['done'::text, 'stopped'::text])) = (end_reason IS NOT NULL))),
    CONSTRAINT agent_case_state CHECK ((jsonb_typeof(state) = 'object'::text)),
    CONSTRAINT agent_case_counts CHECK (((turns >= 0) AND (proactive_sent >= 0) AND (version >= 0))),
    CONSTRAINT agent_case_texts CHECK (((char_length(kind) <= 64) AND (char_length(key) <= 200) AND (char_length(goal) <= 500) AND (char_length(node) <= 64) AND ((end_reason IS NULL) OR (char_length(end_reason) <= 300))))
);

-- one live case per (kind, key): an event sent twice, or a scan run twice, never opens a second one
CREATE UNIQUE INDEX agent_case_live ON agent_rt.agent_case USING btree (tenant_id, agent, plugin, kind, key)
    WHERE (status = ANY (ARRAY['open'::text, 'waiting'::text, 'needs_human'::text]));
CREATE INDEX agent_case_due ON agent_rt.agent_case USING btree (tenant_id, agent, wake_at)
    WHERE (status = ANY (ARRAY['open'::text, 'waiting'::text]));
CREATE INDEX agent_case_chat ON agent_rt.agent_case USING btree (tenant_id, agent, channel, conversation_id)
    WHERE (status = 'waiting'::text);
CREATE INDEX agent_case_recent ON agent_rt.agent_case USING btree (tenant_id, agent, updated_at DESC);

CREATE TABLE agent_rt.agent_case_event (
    case_id bigint NOT NULL REFERENCES agent_rt.agent_case(id) ON DELETE CASCADE,
    seq integer NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    kind text NOT NULL,
    node text,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT agent_case_event_pkey PRIMARY KEY (case_id, seq),
    CONSTRAINT agent_case_event_kind CHECK ((kind = ANY (ARRAY['opened'::text, 'woken'::text, 'blocked'::text, 'sent'::text, 'decision'::text, 'stopped'::text, 'error'::text, 'lost'::text]))),
    CONSTRAINT agent_case_event_detail CHECK (((jsonb_typeof(detail) = 'object'::text) AND (char_length((detail)::text) <= 2000)))
);

-- what one person was sent by all cases in a day (the daily cap shared by every loop)
CREATE INDEX agent_case_event_sent ON agent_rt.agent_case_event USING btree (at) WHERE (kind = 'sent'::text);

-- the emergency switch of every case, and the cap on messages the agent starts per person per day
ALTER TABLE agent_rt.agent_settings
    ADD COLUMN cases_enabled boolean,
    ADD COLUMN proactive_per_person_per_day integer,
    ADD CONSTRAINT agent_settings_proactive_cap CHECK (((proactive_per_person_per_day IS NULL) OR ((proactive_per_person_per_day >= 1) AND (proactive_per_person_per_day <= 20))));

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_rt_app') THEN
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_case TO agent_rt_app;
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_case_event TO agent_rt_app;
  END IF;
END $$;
