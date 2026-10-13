-- The skills the agent wrote before this plugin existed (core table agent_skill) become items of kind skill,
-- bound to the whole agent, with a first history entry each. Names the plugin has already are left alone.

INSERT INTO sk_item (tenant_id, agent, id, kind, name, description, body, status, origin, updated_by,
                     created_at, updated_at)
SELECT s.tenant_id, s.agent, 'itm-' || substr(md5(s.tenant_id || '/' || s.agent || '/' || s.name), 1, 12),
       'skill', s.name, left(s.description, 300), s.body, 'active', 'agent', 'import', s.created_at,
       s.updated_at
FROM agent_skill s
ON CONFLICT (tenant_id, agent, kind, name) DO NOTHING;

INSERT INTO sk_item_version (tenant_id, agent, item_id, version, snapshot, changed_by, reason)
SELECT i.tenant_id, i.agent, i.id, i.version,
       jsonb_build_object('kind', i.kind, 'name', i.name, 'description', i.description, 'body', i.body,
                          'status', i.status, 'scopes', to_jsonb(i.scopes), 'meta', i.meta),
       'import', 'imported from agent_skill'
FROM sk_item i
WHERE i.updated_by = 'import'
ON CONFLICT DO NOTHING;
