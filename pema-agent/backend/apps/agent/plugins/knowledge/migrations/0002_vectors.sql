-- Vectors for the knowledge store. A vector belongs to a text, not to a chunk row: chunks are deleted and
-- inserted again whenever a source is re-cut, and their text (so their vector) usually stays the same.
-- `space` names the model, dimensions and document prefix a vector was made with (sha256, 16 hex).
-- The vector type lives in schema public (pgvector); this file runs with search_path agent_rt.

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

ALTER TABLE kb_chunk ADD COLUMN embed_text text NOT NULL DEFAULT '';
ALTER TABLE kb_chunk ADD COLUMN embed_hash text NOT NULL DEFAULT '';

-- chunks stored before this file: the same text as plugins/knowledge/text.py embed_text_of() builds
UPDATE kb_chunk c
SET embed_text = s.title || E'\n' || c.path || E'\n\n' || c.body
FROM kb_source s
WHERE s.tenant_id = c.tenant_id AND s.agent = c.agent AND s.id = c.source_id;

UPDATE kb_chunk SET embed_hash = encode(sha256(convert_to(embed_text, 'UTF8')), 'hex');

ALTER TABLE kb_chunk DROP COLUMN embedded;

CREATE INDEX kb_chunk_embed ON kb_chunk (tenant_id, agent, embed_hash);

CREATE TABLE kb_embedding (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    space text NOT NULL CHECK (space ~ '^[0-9a-f]{16}$'),
    text_hash text NOT NULL CHECK (text_hash ~ '^[0-9a-f]{64}$'),
    vector public.vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, space, text_hash)
);
