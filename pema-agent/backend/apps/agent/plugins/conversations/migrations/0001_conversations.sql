-- Conversations the agent's channels hear, their messages with who wrote each (customer, staff or the agent), and
-- scenarios: episodes cut from the kept conversations (what a customer asked, how the staff reacted), searched by
-- keyword (tsvector) and by meaning (a vector per episode, in the space of the embedding model that made it).
-- Runs in schema agent_rt (agent db migrate-plugins); every row is scoped by tenant and agent. The vector type
-- lives in schema public (pgvector); this file runs with search_path agent_rt.

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

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
    -- the last message already looked at for episodes
    cut_upto bigint NOT NULL DEFAULT 0,
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

CREATE TABLE cv_episode (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    channel text NOT NULL,
    plugin text NOT NULL DEFAULT '',
    conversation_id text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    first_seq bigint NOT NULL,
    last_seq bigint NOT NULL,
    ask text NOT NULL,
    transcript jsonb NOT NULL,
    fingerprint text NOT NULL,
    terms tsvector NOT NULL,
    repeats integer NOT NULL DEFAULT 1 CHECK (repeats >= 1),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, id)
);

CREATE INDEX cv_episode_terms ON cv_episode USING gin (terms);
CREATE INDEX cv_episode_fingerprint ON cv_episode (tenant_id, agent, channel, fingerprint);
CREATE INDEX cv_episode_listing ON cv_episode (tenant_id, agent, channel, updated_at DESC);

CREATE TABLE cv_episode_vector (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    space text NOT NULL CHECK (space ~ '^[0-9a-f]{16}$'),
    episode_id text NOT NULL,
    vector public.vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, space, episode_id),
    FOREIGN KEY (tenant_id, agent, episode_id) REFERENCES cv_episode (tenant_id, agent, id) ON DELETE CASCADE
);
