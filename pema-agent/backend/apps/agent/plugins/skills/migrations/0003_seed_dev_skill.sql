-- The one skill the dev agent shipped as a file (agents/dev/skills/write-a-plan/SKILL.md) now lives in the
-- database like every other skill, bound to the whole agent. A name the plugin already has is left alone.

INSERT INTO sk_item (tenant_id, agent, id, kind, name, description, body, status, origin, updated_by)
VALUES ('default', 'dev', 'itm-seed-write-a-plan', 'skill', 'write-a-plan',
        'Turn a multi-step request into a short numbered plan before doing it.',
        E'1. Restate the goal in one sentence.\n'
        '2. List the steps in order, one line each; mark the steps that need a tool.\n'
        '3. Name anything you still need from the user and ask for it first.\n'
        '4. Do the steps; after each one, say in a few words what changed.',
        'active', 'admin', 'seed')
ON CONFLICT (tenant_id, agent, kind, name) DO NOTHING;

INSERT INTO sk_item_version (tenant_id, agent, item_id, version, snapshot, changed_by, reason)
SELECT i.tenant_id, i.agent, i.id, i.version,
       jsonb_build_object('kind', i.kind, 'name', i.name, 'description', i.description, 'body', i.body,
                          'status', i.status, 'scopes', to_jsonb(i.scopes), 'meta', i.meta),
       'seed', 'moved from agents/dev/skills'
FROM sk_item i
WHERE i.id = 'itm-seed-write-a-plan'
ON CONFLICT DO NOTHING;
