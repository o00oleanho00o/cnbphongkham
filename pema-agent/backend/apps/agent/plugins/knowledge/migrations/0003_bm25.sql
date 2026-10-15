-- BM25 for the keyword search. A search scores the chunks that match, and for each it needs the length of the chunk
-- and how many times each question word is in it. Both are kept beside the tsvector (the same words, counted the
-- same way as plugins/knowledge/text.py chunk_terms does), so a search does not unnest the tsvector of every chunk.
-- This file runs with search_path agent_rt.

ALTER TABLE kb_chunk ADD COLUMN terms_len integer NOT NULL DEFAULT 0;
ALTER TABLE kb_chunk ADD COLUMN term_counts jsonb NOT NULL DEFAULT '{}'::jsonb;

-- chunks stored before this file: a word's positions in the tsvector are its count
UPDATE kb_chunk
SET terms_len = (SELECT COALESCE(sum(array_length(u.positions, 1)), 0) FROM unnest(terms) AS u),
    term_counts = (SELECT COALESCE(jsonb_object_agg(u.lexeme, array_length(u.positions, 1)), '{}'::jsonb)
                   FROM unnest(terms) AS u);
