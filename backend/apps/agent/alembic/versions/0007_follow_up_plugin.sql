-- Following up leaves the harness for the plugin follow_up, a case on the case engine (docs/PLAN-case-loop.md 7).

-- 1. An appointment still to come becomes a case of the plugin, waiting at its check node for the time it had.
--    Other rows are dropped: a new case opens only when the customer writes first, which is what "stopped" meant.
INSERT INTO agent_rt.agent_case (
    tenant_id, agent, plugin, kind, key, channel, conversation_id, user_id, session_id, goal, status, node,
    state, wait_for, wake_at, deadline
)
SELECT
    f.tenant_id, f.agent, 'follow_up', 'follow_up', f.channel || ':' || f.conversation_id, f.channel,
    f.conversation_id, f.user_id, f.session_id,
    'Khách im lặng được nhắn lại một lần đúng lúc nếu còn quan tâm, không thì để yên', 'waiting', 'check',
    jsonb_strip_nulls(jsonb_build_object(
        'channel', f.channel, 'conversation_id', f.conversation_id, 'user_id', f.user_id,
        'replied_at', f.updated_at, 'judged_at', f.updated_at, 'state', f.state, 'reason', left(f.reason, 300),
        'next_at', f.next_at, 'paused_until', f.paused_until, 'last_sent_at', f.last_sent_at,
        'unanswered', f.unanswered
    )),
    'clock', f.next_at, GREATEST(now(), f.next_at) + interval '74 days'
FROM agent_rt.agent_follow_up f
WHERE f.next_at IS NOT NULL AND NOT f.stopped
ON CONFLICT DO NOTHING;

-- 2. The switch and the channels an admin chose become the plugin's: enabled, with its setting "channels".
INSERT INTO agent_rt.agent_plugin (tenant_id, agent, name, enabled, config)
SELECT
    s.tenant_id, s.agent, 'follow_up', true,
    jsonb_build_object('channels', COALESCE(
        (SELECT string_agg(c.value, ',') FROM jsonb_array_elements_text(s.follow_up_channels) AS c(value)), ''
    ))
FROM agent_rt.agent_settings s
WHERE s.follow_up_enabled
ON CONFLICT (tenant_id, agent, name) DO UPDATE
    SET enabled = true, config = agent_rt.agent_plugin.config || EXCLUDED.config, updated_at = now();

-- 3. The harness keeps nothing of it.
DROP TABLE agent_rt.agent_follow_up;
ALTER TABLE agent_rt.agent_settings
    DROP CONSTRAINT agent_settings_follow_up_channels,
    DROP COLUMN follow_up_enabled,
    DROP COLUMN follow_up_channels;
