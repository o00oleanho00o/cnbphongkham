-- The decision a steering tool (case_done, case_wait_until) gave during a case's turn, with the turn it
-- belongs to: kept in the database so a restart or another process never loses it (docs/PLAN-case-loop.md C2).
-- An older turn's entry is simply ignored; the turn number only grows.
ALTER TABLE agent_rt.agent_case
    ADD COLUMN pending jsonb,
    ADD CONSTRAINT agent_case_pending CHECK (((pending IS NULL) OR ((jsonb_typeof(pending) = 'object'::text) AND (char_length((pending)::text) <= 2000))));
