-- The core's own skill table is gone: its skills were imported by 0002 (this file runs after it, on every
-- database), and the agent now writes skills as items of this plugin.

DROP TABLE IF EXISTS agent_skill;
