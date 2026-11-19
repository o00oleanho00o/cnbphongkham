-- The limits of a turn and of compaction an admin changes from the dashboard (docs/PLAN-case-loop.md 8), and the
-- context window of each model. NULL keeps the profile's value. The bounds are those of agent_settings.py.
ALTER TABLE agent_rt.agent_settings
    ADD COLUMN max_steps integer,
    ADD COLUMN max_output_tokens integer,
    ADD COLUMN max_turn_s double precision,
    ADD COLUMN max_turn_tokens integer,
    ADD COLUMN stop_after_repeats integer,
    ADD COLUMN error_streak_stop integer,
    ADD COLUMN compact_at double precision,
    ADD COLUMN keep_recent_ratio double precision,
    ADD COLUMN max_parallel_tools integer,
    ADD COLUMN max_tool_calls_per_step integer,
    ADD CONSTRAINT agent_settings_limits CHECK (
        (max_steps IS NULL OR max_steps BETWEEN 1 AND 50)
        AND (max_output_tokens IS NULL OR max_output_tokens BETWEEN 64 AND 32768)
        AND (max_turn_s IS NULL OR max_turn_s BETWEEN 10 AND 1800)
        AND (max_turn_tokens IS NULL OR max_turn_tokens BETWEEN 1000 AND 10000000)
        AND (stop_after_repeats IS NULL OR stop_after_repeats BETWEEN 2 AND 50)
        AND (error_streak_stop IS NULL OR error_streak_stop BETWEEN 2 AND 50)
        AND (compact_at IS NULL OR compact_at BETWEEN 0.3 AND 0.95)
        AND (keep_recent_ratio IS NULL OR keep_recent_ratio BETWEEN 0 AND 0.6)
        AND (max_parallel_tools IS NULL OR max_parallel_tools BETWEEN 1 AND 32)
        AND (max_tool_calls_per_step IS NULL OR max_tool_calls_per_step BETWEEN 1 AND 64)
    );

ALTER TABLE agent_rt.agent_model_entry
    ADD COLUMN window_tokens integer,
    ADD CONSTRAINT agent_model_entry_window CHECK (window_tokens IS NULL OR window_tokens BETWEEN 4000 AND 2000000);

ALTER TABLE agent_rt.agent_model_settings
    ADD COLUMN window_tokens integer,
    ADD CONSTRAINT agent_model_window CHECK (window_tokens IS NULL OR window_tokens BETWEEN 4000 AND 2000000);
