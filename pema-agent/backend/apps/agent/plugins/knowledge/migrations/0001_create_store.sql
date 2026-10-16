-- The knowledge store: sources (one document each), their chunks with a keyword index, the services and
-- their other names, what happened to a source, the questions the store had no answer for, and the vectors.
-- Runs in schema agent_rt (agent db migrate-plugins); every row is scoped by tenant and agent. The vector type
-- lives in schema public (pgvector); this file runs with search_path agent_rt.

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE kb_source (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 300),
    doc_code text CHECK (doc_code IS NULL OR char_length(doc_code) BETWEEN 1 AND 120),
    kind text NOT NULL CHECK (kind IN ('file', 'text')),
    format text NOT NULL CHECK (format IN ('md', 'txt', 'docx', 'xlsx', 'pdf', 'text')),
    size integer NOT NULL CHECK (size >= 0),
    services text[] NOT NULL DEFAULT '{}',
    audience text NOT NULL CHECK (audience IN ('patient', 'staff')),
    processing text NOT NULL CHECK (processing IN ('queued', 'processing', 'ready', 'error')),
    progress jsonb NOT NULL DEFAULT '{"chunks": 0, "labelled": 0, "embedded": 0}',
    error text,
    lifecycle text NOT NULL CHECK (lifecycle IN ('active', 'draft', 'superseded', 'expired', 'adversarial')),
    version text,
    effective_from date,
    effective_to date,
    approved boolean NOT NULL DEFAULT true,
    approved_by text,
    approved_at timestamptz,
    chunk_count integer NOT NULL DEFAULT 0,
    note text NOT NULL DEFAULT '',
    markdown text NOT NULL DEFAULT '',
    content_hash text NOT NULL,
    supersedes text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, id)
);

CREATE INDEX kb_source_code ON kb_source (tenant_id, agent, doc_code);
CREATE INDEX kb_source_hash ON kb_source (tenant_id, agent, content_hash);

CREATE TABLE kb_chunk (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    source_id text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 1),
    path text NOT NULL,
    body text NOT NULL,
    chars integer NOT NULL,
    services text[] NOT NULL DEFAULT '{}',
    kind text NOT NULL DEFAULT 'info',
    terms tsvector NOT NULL,
    -- the text a vector is made of (plugins/knowledge/text.py embed_text_of) and its sha256
    embed_text text NOT NULL DEFAULT '',
    embed_hash text NOT NULL DEFAULT '',
    -- BM25 for the keyword search: the length of the chunk and how many times each word is in it, counted the
    -- same way as plugins/knowledge/text.py chunk_terms does, so a search does not unnest every tsvector
    terms_len integer NOT NULL DEFAULT 0,
    term_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, agent, id),
    FOREIGN KEY (tenant_id, agent, source_id) REFERENCES kb_source (tenant_id, agent, id) ON DELETE CASCADE
);

CREATE INDEX kb_chunk_terms ON kb_chunk USING gin (terms);
CREATE INDEX kb_chunk_source ON kb_chunk (tenant_id, agent, source_id, ordinal);
CREATE INDEX kb_chunk_embed ON kb_chunk (tenant_id, agent, embed_hash);

CREATE TABLE kb_service (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    code text NOT NULL CHECK (code ~ '^[A-Z0-9_]{1,40}$'),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    aliases text[] NOT NULL DEFAULT '{}',
    description text NOT NULL DEFAULT '',
    branches text[] NOT NULL DEFAULT '{}',
    enabled boolean NOT NULL DEFAULT true,
    PRIMARY KEY (tenant_id, agent, id),
    UNIQUE (tenant_id, agent, code)
);

CREATE TABLE kb_event (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    source_id text NOT NULL,
    at timestamptz NOT NULL DEFAULT now(),
    kind text NOT NULL,
    by_whom text NOT NULL,
    note text NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_id, agent, id)
);

CREATE INDEX kb_event_source ON kb_event (tenant_id, agent, source_id, at DESC);

CREATE TABLE kb_gap (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    id text NOT NULL,
    folded text NOT NULL,
    question text NOT NULL,
    count integer NOT NULL DEFAULT 1,
    channel text NOT NULL DEFAULT '',
    last_asked_at timestamptz NOT NULL DEFAULT now(),
    state text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'ignored', 'answered')),
    PRIMARY KEY (tenant_id, agent, id),
    UNIQUE (tenant_id, agent, folded)
);

-- A vector belongs to a text, not to a chunk row: chunks are deleted and inserted again whenever a source is
-- re-cut, and their text (so their vector) usually stays the same. `space` names the model, dimensions and document
-- prefix a vector was made with (sha256, 16 hex).
CREATE TABLE kb_embedding (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    space text NOT NULL CHECK (space ~ '^[0-9a-f]{16}$'),
    text_hash text NOT NULL CHECK (text_hash ~ '^[0-9a-f]{64}$'),
    vector public.vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, space, text_hash)
);
