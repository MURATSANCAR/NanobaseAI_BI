-- One identity vector per drawn figure. Kept so that clustering can be repeated (new
-- threshold, new rule) without reading the pages again: the crops do not change, only
-- what we conclude from them does.
-- (IF NOT EXISTS: a test host carried this table under an earlier number before the
-- numbering was aligned with main.)
SET search_path = ed, public;
CREATE TABLE IF NOT EXISTS figure_embedding (
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  mention_id    uuid NOT NULL REFERENCES character_mention(id) ON DELETE CASCADE,
  model         text NOT NULL,
  vector        real[] NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mention_id, model)
);
CREATE INDEX IF NOT EXISTS figure_embedding_gen ON figure_embedding(generation_id, model);
