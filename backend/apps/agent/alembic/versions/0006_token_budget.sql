-- The token budget checked before every turn (docs/PLAN-case-loop.md, section 3 item 1): what one session and
-- the whole agent may spend in one local day, counted from agent_turn. NULL keeps the service's default.
ALTER TABLE agent_rt.agent_settings
    ADD COLUMN tokens_per_session_per_day bigint,
    ADD COLUMN tokens_per_day bigint,
    ADD CONSTRAINT agent_settings_tokens_per_session CHECK (((tokens_per_session_per_day IS NULL) OR ((tokens_per_session_per_day >= 10000) AND (tokens_per_session_per_day <= 100000000)))),
    ADD CONSTRAINT agent_settings_tokens_per_day CHECK (((tokens_per_day IS NULL) OR ((tokens_per_day >= 100000) AND (tokens_per_day <= 2000000000))));

-- The day's sum of the whole agent, read before every turn.
CREATE INDEX agent_turn_agent_started_idx ON agent_rt.agent_turn USING btree (tenant_id, agent, started_at);
