-- The follow-up loop: one row per conversation the agent judged after it went quiet (state, when to write
-- again, whether to leave it alone), and the switch that turns the loop on per channel.
ALTER TABLE agent_rt.agent_settings
    ADD COLUMN follow_up_enabled boolean,
    ADD COLUMN follow_up_channels jsonb DEFAULT '[]'::jsonb NOT NULL,
    ADD CONSTRAINT agent_settings_follow_up_channels CHECK ((jsonb_typeof(follow_up_channels) = 'array'::text));

CREATE TABLE agent_rt.agent_follow_up (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    channel text NOT NULL,
    conversation_id text NOT NULL,
    user_id text NOT NULL,
    session_id text NOT NULL,
    state text NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    next_at timestamp with time zone,
    paused_until timestamp with time zone,
    stopped boolean DEFAULT false NOT NULL,
    unanswered integer DEFAULT 0 NOT NULL,
    last_sent_at timestamp with time zone,
    reviewed_through bigint DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_follow_up_pkey PRIMARY KEY (tenant_id, agent, channel, conversation_id),
    CONSTRAINT agent_follow_up_state CHECK ((state = ANY (ARRAY['done'::text, 'hesitant'::text, 'call_back'::text, 'soft_decline'::text, 'hard_decline'::text, 'negative'::text]))),
    CONSTRAINT agent_follow_up_reason CHECK ((char_length(reason) <= 500)),
    CONSTRAINT agent_follow_up_unanswered CHECK ((unanswered >= 0)),
    CONSTRAINT agent_follow_up_reviewed CHECK ((reviewed_through >= 0))
);

CREATE INDEX agent_follow_up_due_idx ON agent_rt.agent_follow_up USING btree (tenant_id, agent, next_at) WHERE (next_at IS NOT NULL);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_rt_app') THEN
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE agent_rt.agent_follow_up TO agent_rt_app;
  END IF;
END $$;
