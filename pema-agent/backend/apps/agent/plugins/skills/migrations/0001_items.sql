-- Skills, rules and persona (kind) with the scopes they are bound to, and the history of every change.
-- Runs in schema agent_rt (agent db migrate-plugins); every row is scoped by tenant and agent.

CREATE TABLE sk_item (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('skill', 'rules', 'persona')),
    name text NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
    description text NOT NULL CHECK (char_length(description) BETWEEN 1 AND 300),
    body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 20000),
    status text NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
    origin text NOT NULL CHECK (origin IN ('admin', 'plugin', 'agent')),
    scopes text[] NOT NULL DEFAULT '{}',
    meta jsonb NOT NULL DEFAULT '{}',
    usage jsonb NOT NULL DEFAULT '{}',
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, id),
    UNIQUE (tenant_id, agent, kind, name)
);

CREATE INDEX sk_item_status ON sk_item (tenant_id, agent, status);

CREATE TABLE sk_item_version (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    item_id text NOT NULL,
    version integer NOT NULL,
    snapshot jsonb NOT NULL,
    changed_by text NOT NULL DEFAULT '',
    reason text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, item_id, version),
    FOREIGN KEY (tenant_id, agent, item_id) REFERENCES sk_item (tenant_id, agent, id) ON DELETE CASCADE
);
