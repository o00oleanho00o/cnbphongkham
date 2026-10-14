-- Conversations the agent's channels hear, and their messages with who wrote each (customer, staff or the agent).
-- Runs in schema agent_rt (agent db migrate-plugins); every row is scoped by tenant and agent.

CREATE TABLE cv_conversation (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    channel text NOT NULL,
    external_id text NOT NULL,
    is_group boolean NOT NULL DEFAULT false,
    title text NOT NULL DEFAULT '',
    excluded boolean NOT NULL DEFAULT false,
    message_count integer NOT NULL DEFAULT 0,
    first_at timestamptz NOT NULL,
    last_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, agent, id),
    UNIQUE (tenant_id, agent, channel, external_id)
);

CREATE INDEX cv_conversation_last ON cv_conversation (tenant_id, agent, channel, last_at DESC);

CREATE TABLE cv_message (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    seq bigint GENERATED ALWAYS AS IDENTITY,
    conversation_id text NOT NULL,
    external_id text NOT NULL,
    sender_id text NOT NULL DEFAULT '',
    sender_name text NOT NULL DEFAULT '',
    role text NOT NULL CHECK (role IN ('customer', 'staff', 'agent')),
    origin text NOT NULL CHECK (origin IN ('inbound', 'own', 'agent')),
    at timestamptz NOT NULL,
    text text NOT NULL,
    answered boolean NOT NULL DEFAULT false,
    meta jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (tenant_id, agent, seq),
    UNIQUE (tenant_id, agent, conversation_id, external_id),
    FOREIGN KEY (tenant_id, agent, conversation_id) REFERENCES cv_conversation (tenant_id, agent, id) ON DELETE CASCADE
);

CREATE INDEX cv_message_time ON cv_message (tenant_id, agent, conversation_id, at, seq);
CREATE INDEX cv_message_at ON cv_message (tenant_id, agent, at);
