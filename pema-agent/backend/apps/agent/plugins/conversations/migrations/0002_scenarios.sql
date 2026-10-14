-- Scenarios: episodes cut from the kept conversations (what a customer asked, how the staff reacted), searched by
-- keyword (tsvector) and by meaning (a vector per episode, in the space of the embedding model that made it).
-- Runs in schema agent_rt (agent db migrate-plugins); every row is scoped by tenant and agent. The vector type
-- lives in schema public (pgvector); this file runs with search_path agent_rt.

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- the last message of each conversation already looked at for episodes
ALTER TABLE cv_conversation ADD COLUMN cut_upto bigint NOT NULL DEFAULT 0;

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
